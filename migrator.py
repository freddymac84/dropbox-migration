import os
import time
import hashlib
import json
import threading
import concurrent.futures
import io
from db_manager import DBManager
from dropbox_client import DropboxClient
from gdrive_client import GDriveClient

_progress_state = {
    'active_downloads': {},
    'active_uploads': {},
    'session_downloaded': 0,
    'session_uploaded': 0
}

_progress_lock = threading.Lock()

def write_progress(action, file_path, transferred, total):
    key = 'active_downloads' if action == 'DOWNLOADING' else 'active_uploads'
    
    with _progress_lock:
        file_map = _progress_state[key]
        
        current_transferred = file_map.get(file_path, {}).get('transferred', 0)
        
        if transferred < current_transferred:
            delta = transferred
        else:
            delta = transferred - current_transferred
            
        if action == 'DOWNLOADING':
            _progress_state['session_downloaded'] += delta
        else:
            _progress_state['session_uploaded'] += delta
            
        file_map[file_path] = {
            'transferred': transferred,
            'total': total,
            'updated_at': time.time()
        }
        
        # Cleanup stale files (> 60s old)
        now = time.time()
        to_del = [p for p, data in file_map.items() if now - data['updated_at'] > 60]
        for p in to_del:
            del file_map[p]
            
        try:
            with open('progress.json', 'w') as f:
                json.dump(_progress_state, f)
        except:
            pass

def remove_progress(action, file_path):
    key = 'active_downloads' if action == 'DOWNLOADING' else 'active_uploads'
    with _progress_lock:
        if file_path in _progress_state[key]:
            del _progress_state[key][file_path]
            try:
                with open('progress.json', 'w') as f:
                    json.dump(_progress_state, f)
            except:
                pass

class Migrator:
    def __init__(self, dropbox_token=None, dropbox_app_key=None, dropbox_app_secret=None, gdrive_credentials_file='credentials.json', tmp_dir='./tmp_migration'):
        self.db = DBManager()
        self.dropbox = DropboxClient(token=dropbox_token, app_key=dropbox_app_key, app_secret=dropbox_app_secret)
        self.gdrive = GDriveClient(gdrive_credentials_file)
        self.tmp_dir = tmp_dir
        os.makedirs(self.tmp_dir, exist_ok=True)

    def scan_dropbox_folder(self, folder_path=""):
        """Scans Dropbox and adds files to the database for tracking."""
        print(f"Scanning Dropbox folder: '{folder_path}'...")
        files = self.dropbox.list_folder_recursive(folder_path)
        added_count = 0
        for f in files:
            if self.db.add_file(f['path'], f['size']):
                added_count += 1
        print(f"Scan complete. Added {added_count} new files to the queue out of {len(files)} total found.")

    def _get_local_tmp_path(self, dropbox_path):
        safe_name = dropbox_path.replace('/', '_').strip('_')
        return os.path.join(self.tmp_dir, safe_name)

    def _small_file_worker(self):
        print("[SmallWorker] Thread started.")
        while True:
            file_record = self.db.get_small_file_to_migrate()
            if not file_record:
                # No small files pending
                break

            dropbox_path = file_record['dropbox_path']
            size = file_record['size']
            
            print(f"[SmallWorker] Streaming from Dropbox: {dropbox_path}")
            write_progress('DOWNLOADING', dropbox_path, 0, size)
            stream = self.dropbox.download_file_to_stream(dropbox_path, write_progress)
            
            if not stream:
                self.db.update_status(dropbox_path, 'ERROR', error_message="Memory download failed")
                remove_progress('DOWNLOADING', dropbox_path)
                continue

            print(f"[SmallWorker] Uploading to Google Drive: {dropbox_path}")
            base_gdrive_folder = "000 Backup Dropbox"
            gdrive_path = os.path.join(base_gdrive_folder, dropbox_path.lstrip('/'))
            
            # Since it's in RAM, we can compute MD5 immediately
            hash_md5 = hashlib.md5(stream.getvalue()).hexdigest()
            
            write_progress('UPLOADING', dropbox_path, 0, size)
            upload_result = self.gdrive.upload_file(stream, gdrive_path, write_progress, is_stream=True)
            remove_progress('DOWNLOADING', dropbox_path)
            remove_progress('UPLOADING', dropbox_path)
            
            if upload_result and 'id' in upload_result:
                uploaded_size = int(upload_result.get('size', 0))
                expected_size = size
                gdrive_md5 = upload_result.get('md5Checksum')
                
                if uploaded_size == expected_size and gdrive_md5 == hash_md5:
                    print(f"[SmallWorker] Upload successful and verified! (ID: {upload_result['id']})")
                    self.db.update_status(dropbox_path, 'COMPLETED', gdrive_id=upload_result['id'])
                else:
                    msg = f"Verification failed! Size: {expected_size}->{uploaded_size}, MD5: {hash_md5}->{gdrive_md5}"
                    print(f"[SmallWorker] {msg}")
                    self.db.update_status(dropbox_path, 'ERROR', error_message=msg)
            else:
                self.db.update_status(dropbox_path, 'ERROR', error_message="Upload failed or returned empty result")

    def _large_downloader_worker(self):
        print("[LargeDownloader] Thread started.")
        while True:
            downloaded_size = self.db.get_downloaded_size()
            max_size_bytes = 10 * 1024 * 1024 * 1024 # 10 GB limit for large files cache
            if downloaded_size >= max_size_bytes:
                time.sleep(2)
                continue

            file_record = self.db.get_large_file_to_download()
            if not file_record:
                break

            dropbox_path = file_record['dropbox_path']
            size = file_record['size']
            local_path = self._get_local_tmp_path(dropbox_path)
            
            print(f"[LargeDownloader] Downloading: {dropbox_path}")
            write_progress('DOWNLOADING', dropbox_path, 0, size)
            success = self.dropbox.download_file(dropbox_path, local_path, write_progress)
            remove_progress('DOWNLOADING', dropbox_path)
            if not success:
                self.db.update_status(dropbox_path, 'ERROR', error_message="Download failed")
                continue
            
            self.db.update_status(dropbox_path, 'DOWNLOADED')

    def _large_uploader_worker(self):
        print("[LargeUploader] Thread started.")
        while True:
            file_record = self.db.get_large_file_to_upload()
            if not file_record:
                if not self.db.get_large_file_to_download():
                    break
                time.sleep(2)
                continue

            dropbox_path = file_record['dropbox_path']
            size = file_record['size']
            local_path = self._get_local_tmp_path(dropbox_path)
            
            if not os.path.exists(local_path):
                print(f"[LargeUploader] File {local_path} missing! Reverting status to PENDING.")
                self.db.update_status(dropbox_path, 'PENDING')
                continue

            print(f"[LargeUploader] Uploading to Google Drive: {dropbox_path}")
            base_gdrive_folder = "000 Backup Dropbox"
            gdrive_path = os.path.join(base_gdrive_folder, dropbox_path.lstrip('/'))
            write_progress('UPLOADING', dropbox_path, 0, size)
            
            upload_result = self.gdrive.upload_file(local_path, gdrive_path, write_progress)
            remove_progress('UPLOADING', dropbox_path)
            
            if upload_result and 'id' in upload_result:
                uploaded_size = int(upload_result.get('size', 0))
                expected_size = size
                gdrive_md5 = upload_result.get('md5Checksum')
                
                hash_md5 = hashlib.md5()
                with open(local_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                local_md5 = hash_md5.hexdigest()
                
                if uploaded_size == expected_size and gdrive_md5 == local_md5:
                    print(f"[LargeUploader] Upload successful and verified! (ID: {upload_result['id']})")
                    self.db.update_status(dropbox_path, 'COMPLETED', gdrive_id=upload_result['id'])
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
                else:
                    msg = f"Verification failed! Size: {expected_size}->{uploaded_size}, MD5: {local_md5}->{gdrive_md5}"
                    print(f"[LargeUploader] {msg}")
                    self.db.update_status(dropbox_path, 'ERROR', error_message=msg)
            else:
                self.db.update_status(dropbox_path, 'ERROR', error_message="Upload failed or returned empty result")

    def process_queue(self):
        """Processes the migration queue using size-based routing and multiple workers."""
        print("Starting hybrid migration queue processing...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=14) as executor:
            futures = []
            
            # Start 10 small file workers
            for _ in range(10):
                futures.append(executor.submit(self._small_file_worker))
                
            # Start 2 large file downloaders
            for _ in range(2):
                futures.append(executor.submit(self._large_downloader_worker))
                
            # Start 2 large file uploaders
            for _ in range(2):
                futures.append(executor.submit(self._large_uploader_worker))
                
            # Wait for all workers to finish
            concurrent.futures.wait(futures)
        
        print("Migration complete!")
        try:
            if os.path.exists('progress.json'):
                os.remove('progress.json')
        except:
            pass
