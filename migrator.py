import os
import time
import hashlib
import json
from db_manager import DBManager
from dropbox_client import DropboxClient
from gdrive_client import GDriveClient

_current_action_start = 0
_current_action = None

def write_progress(action, file_path, transferred, total):
    global _current_action, _current_action_start
    if _current_action != action:
        _current_action = action
        _current_action_start = time.time()
        
    try:
        with open('progress.json', 'w') as f:
            json.dump({
                'action': action,
                'file': file_path,
                'transferred': transferred,
                'total': total,
                'start_time': _current_action_start,
                'updated_at': time.time()
            }, f)
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

    def process_queue(self):
        """Processes the migration queue one file at a time."""
        print("Starting migration queue processing...")
        while True:
            file_record = self.db.get_pending_file()
            if not file_record:
                print("No pending files in the queue. Migration complete!")
                try:
                    if os.path.exists('progress.json'):
                        os.remove('progress.json')
                except:
                    pass
                break

            dropbox_path = file_record['dropbox_path']
            size = file_record['size']
            print(f"\nProcessing: {dropbox_path}")
            local_path = self._get_local_tmp_path(dropbox_path)
            
            # Step 1: Download
            # If the file is marked as downloaded but missing locally (e.g. crash), redownload it
            if file_record['status'] == 'PENDING' or not os.path.exists(local_path):
                print(f"  Downloading from Dropbox...")
                write_progress('DOWNLOADING', dropbox_path, 0, size)
                success = self.dropbox.download_file(dropbox_path, local_path, write_progress)
                if not success:
                    self.db.update_status(dropbox_path, 'ERROR', error_message="Download failed")
                    continue
                self.db.update_status(dropbox_path, 'DOWNLOADED')
            
            # Step 2: Upload
            print(f"  Uploading to Google Drive...")
            base_gdrive_folder = "000 Backup Dropbox"
            gdrive_path = os.path.join(base_gdrive_folder, dropbox_path.lstrip('/'))
            write_progress('UPLOADING', dropbox_path, 0, size)
            
            upload_result = self.gdrive.upload_file(local_path, gdrive_path, write_progress)
            
            if upload_result and 'id' in upload_result:
                uploaded_size = int(upload_result.get('size', 0))
                expected_size = file_record['size']
                gdrive_md5 = upload_result.get('md5Checksum')
                
                # Local MD5 calculation
                hash_md5 = hashlib.md5()
                with open(local_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                local_md5 = hash_md5.hexdigest()
                
                if uploaded_size == expected_size and gdrive_md5 == local_md5:
                    print(f"  Upload successful and verified! (ID: {upload_result['id']}, MD5 matched)")
                    self.db.update_status(dropbox_path, 'COMPLETED', gdrive_id=upload_result['id'])
                    if os.path.exists(local_path):
                        os.remove(local_path)
                else:
                    msg = f"Verification failed! Size: {expected_size}->{uploaded_size}, MD5: {local_md5}->{gdrive_md5}"
                    print(f"  {msg}")
                    self.db.update_status(dropbox_path, 'ERROR', error_message=msg)
            else:
                self.db.update_status(dropbox_path, 'ERROR', error_message="Upload failed or returned empty result")
