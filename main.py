import os
import sys
from dotenv import load_dotenv
from migrator import Migrator

def main():
    load_dotenv()
    print("=== Dropbox to Google Drive Migration Tool ===")
    
    dropbox_token = os.environ.get('DROPBOX_TOKEN')
    dropbox_app_key = os.environ.get('DROPBOX_APP_KEY')
    dropbox_app_secret = os.environ.get('DROPBOX_APP_SECRET')
    
    if not dropbox_token and not (dropbox_app_key and dropbox_app_secret):
        print("ERROR: Insert DROPBOX_APP_KEY and DROPBOX_APP_SECRET in the .env file")
        sys.exit(1)
        
    if not os.path.exists('credentials.json'):
        print("ERROR: 'credentials.json' not found.")
        print("Please download it from Google Cloud Console (APIs & Services -> Credentials).")
        print("It should be an OAuth 2.0 Client ID for a Desktop Application.")
        sys.exit(1)

    try:
        migrator = Migrator(
            dropbox_token=dropbox_token,
            dropbox_app_key=dropbox_app_key,
            dropbox_app_secret=dropbox_app_secret,
            gdrive_credentials_file='credentials.json'
        )
        
        stats = migrator.db.get_stats()
        print(f"\nCurrent Status: {stats}")
        
        # Check if the user wants to skip scanning (useful for restarts)
        if stats:
            skip = input("The database already contains files. Skip scanning and resume migration? (y/n, default y): ").strip().lower()
            if skip != 'n':
                folder_to_scan = None
            else:
                folder_to_scan = input("Enter the Dropbox folder path to scan (e.g., '/Test_Migration', leave empty for root): ").strip()
                
            if stats.get('ERROR', 0) > 0:
                retry_err = input(f"There are {stats['ERROR']} Error files. Retry them automatically first? (y/n, default y): ").strip().lower()
                if retry_err != 'n':
                    migrator.db.reset_errors()
                    stats = migrator.db.get_stats()
                    print(f"\nUpdated Status: {stats}")
        else:
            folder_to_scan = input("Enter the Dropbox folder path to scan (e.g., '/Test_Migration', leave empty for root): ").strip()
            
        if folder_to_scan is not None:
            migrator.scan_dropbox_folder(folder_to_scan)
            stats = migrator.db.get_stats()
            print(f"\nCurrent Status after scan: {stats}")
        
        confirm = input("Do you want to start the migration process now? (y/n): ")
        if confirm.lower() == 'y':
            migrator.process_queue()
        else:
            print("Migration paused. Run again to continue.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
