import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

SCOPES = ['https://www.googleapis.com/auth/drive']

class GDriveClient:
    def __init__(self, credentials_file='credentials.json', token_file='token.json'):
        self.creds = None
        if os.path.exists(token_file):
            self.creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not os.path.exists(credentials_file):
                    raise FileNotFoundError(f"Missing {credentials_file}. Download it from Google Cloud Console.")
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                self.creds = flow.run_local_server(port=0)
            with open(token_file, 'w') as token:
                token.write(self.creds.to_json())

        import threading
        self.local = threading.local()
        self.folder_cache = {} # Cache folder IDs to avoid redundant API calls

    def get_service(self):
        if not hasattr(self.local, 'service'):
            self.local.service = build('drive', 'v3', credentials=self.creds)
        return self.local.service

    def _get_or_create_folder(self, folder_name, parent_id=None):
        # Escape single quotes in folder name to avoid query errors
        safe_folder_name = folder_name.replace("'", "\\'")
        cache_key = f"{parent_id}_{folder_name}"
        if cache_key in self.folder_cache:
            return self.folder_cache[cache_key]

        query = f"name='{safe_folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        else:
            query += " and 'root' in parents"

        results = self.get_service().files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])

        if items:
            folder_id = items[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]
            folder = self.get_service().files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
            
        self.folder_cache[cache_key] = folder_id
        return folder_id

    def ensure_path_exists(self, path):
        """Creates the directory structure in GDrive and returns the final folder ID."""
        if path == '/' or path == '' or path == '.':
            return None # root
            
        folders = [f for f in path.split('/') if f]
        parent_id = None
        for folder in folders:
            parent_id = self._get_or_create_folder(folder, parent_id)
        return parent_id

    def upload_file(self, local_path_or_stream, gdrive_path, progress_callback=None, is_stream=False, mimetype='application/octet-stream'):
        """Uploads a file from disk or from an in-memory stream, creating necessary folders."""
        dir_name = os.path.dirname(gdrive_path)
        file_name = os.path.basename(gdrive_path)
        
        parent_id = self.ensure_path_exists(dir_name)
        
        file_metadata = {'name': file_name}
        if parent_id:
            file_metadata['parents'] = [parent_id]
            
        # Use chunked upload for large files (50MB chunks for max throughput)
        chunk_size_bytes = 50 * 1024 * 1024
        if is_stream:
            media = MediaIoBaseUpload(local_path_or_stream, mimetype=mimetype, resumable=True, chunksize=chunk_size_bytes)
        else:
            media = MediaFileUpload(local_path_or_stream, resumable=True, chunksize=chunk_size_bytes)
        
        try:
            request = self.get_service().files().create(body=file_metadata, media_body=media, fields='id, size, md5Checksum')
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status and progress_callback:
                    progress_callback('UPLOADING', gdrive_path, status.resumable_progress, status.total_size)
            return response
        except Exception as e:
            print(f"Error uploading {gdrive_path}: {e}")
            return None
