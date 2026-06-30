import dropbox
import os
import time
import json
from dropbox.exceptions import RateLimitError, ApiError, AuthError

def with_retry(max_retries=5):
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except RateLimitError as e:
                    wait_time = e.retry_after
                    print(f"  [API Limit] Dropbox ha richiesto una pausa. Attendo {wait_time} secondi...")
                    time.sleep(wait_time)
                except (ApiError, AuthError) as e:
                    error_detail = str(e)
                    if hasattr(e, 'error_summary'):
                        error_detail = e.error_summary
                    elif hasattr(e, 'user_message_text') and e.user_message_text:
                        error_detail = e.user_message_text
                    
                    print(f"  [API Error] Dropbox rifiuta la richiesta. Motivo esatto: {error_detail}")
                    raise e
                except Exception as e:
                    print(f"  [Network Error] Errore di rete: {e}. Nuovo tentativo tra {2**retries} secondi...")
                    time.sleep(2**retries)
                    retries += 1
            print("  [Network Error] Numero massimo di tentativi superato.")
            raise Exception("Max retries exceeded for Dropbox API")
        return wrapper
    return decorator

class DropboxClient:
    def __init__(self, token=None, app_key=None, app_secret=None):
        if token and not (app_key and app_secret):
            # Fallback legacy token 
            self.dbx = dropbox.Dropbox(token)
        elif app_key and app_secret:
            self.dbx = self._authenticate_oauth(app_key, app_secret)
        else:
            raise ValueError("Must provide app_key and app_secret in .env")

        try:
            account = self.dbx.users_get_current_account()
            print(f"Connected to Dropbox as {account.name.display_name}")
        except Exception as e:
            print(f"Error connecting to Dropbox: {e}")
            raise e

    def _authenticate_oauth(self, app_key, app_secret):
        token_file = 'dropbox_token.json'
        
        if os.path.exists(token_file):
            with open(token_file, 'r') as f:
                creds = json.load(f)
            return dropbox.Dropbox(
                oauth2_refresh_token=creds.get('refresh_token'),
                app_key=app_key,
                app_secret=app_secret
            )

        auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(app_key, app_secret, token_access_type='offline')
        authorize_url = auth_flow.start()
        print("\n=== AUTENTICAZIONE DROPBOX RICHIESTA ===")
        print("1. Vai a questo indirizzo dal browser:")
        print("   " + authorize_url)
        print("2. Clicca su 'Consenti' e poi su 'Copia il codice di accesso'.")
        auth_code = input("3. Incolla il codice di accesso qui e premi Invio: ").strip()

        try:
            oauth_result = auth_flow.finish(auth_code)
            with open(token_file, 'w') as f:
                json.dump({'refresh_token': oauth_result.refresh_token}, f)
            return dropbox.Dropbox(
                oauth2_refresh_token=oauth_result.refresh_token,
                app_key=app_key,
                app_secret=app_secret
            )
        except Exception as e:
            print('Errore durante auth: %s' % (e,))
            raise e

    @with_retry()
    def _files_list_folder(self, path):
        return self.dbx.files_list_folder(path, recursive=True)

    @with_retry()
    def _files_list_folder_continue(self, cursor):
        return self.dbx.files_list_folder_continue(cursor)

    def list_folder_recursive(self, path=""):
        """Lists all files in a Dropbox folder recursively."""
        files = []
        try:
            result = self._files_list_folder(path)
            self._process_entries(result.entries, files)
            
            while result.has_more:
                result = self._files_list_folder_continue(result.cursor)
                self._process_entries(result.entries, files)
        except Exception as e:
            print(f"Error listing folder {path}: {e}")
            
        return files

    def _process_entries(self, entries, files_list):
        for entry in entries:
            if isinstance(entry, dropbox.files.FileMetadata):
                files_list.append({
                    'path': entry.path_display,
                    'size': entry.size,
                    'id': entry.id
                })

    @with_retry()
    def _files_download_to_file(self, local_path, dropbox_path, progress_callback):
        metadata, response = self.dbx.files_download(dropbox_path)
        total_size = metadata.size
        downloaded = 0
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=10*1024*1024): # 10 MB chunks
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback('DOWNLOADING', dropbox_path, downloaded, total_size)

    def download_file(self, dropbox_path, local_path, progress_callback=None):
        """Downloads a file from Dropbox to local disk."""
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        try:
            self._files_download_to_file(local_path, dropbox_path, progress_callback)
            return True
        except Exception as e:
            print(f"Error downloading {dropbox_path}: {e}")
            return False

    @with_retry()
    def _files_download_to_stream(self, dropbox_path, progress_callback):
        import io
        metadata, response = self.dbx.files_download(dropbox_path)
        total_size = metadata.size
        downloaded = 0
        stream = io.BytesIO()
        for chunk in response.iter_content(chunk_size=10*1024*1024):
            if chunk:
                stream.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback('DOWNLOADING', dropbox_path, downloaded, total_size)
        stream.seek(0)
        return stream

    def download_file_to_stream(self, dropbox_path, progress_callback=None):
        """Downloads a file from Dropbox directly into an in-memory BytesIO stream."""
        try:
            return self._files_download_to_stream(dropbox_path, progress_callback)
        except Exception as e:
            print(f"Error downloading stream {dropbox_path}: {e}")
            return None
