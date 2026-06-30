# Dropbox to Google Drive Migrator

A resilient tool written in Python to migrate massive amounts of data (TB) from Dropbox to Google Drive.
Designed for computers with limited disk space, it calculates a digital fingerprint (MD5) to ensure file integrity and features a real-time Web Dashboard.

## Features
- **Low Disk Footprint**: Temporarily downloads files and deletes them immediately after successful upload.
- **100% Data Integrity**: Cryptographic verification (MD5 Checksum) between the local file and Google Drive.
- **Resumability & Rate Limiting**: Stop and resume whenever you want. Includes exponential backoff for API limits.
- **Live Dashboard**: Modern Web Interface with pagination, error control, and real-time streaming progress bars.
- **OAuth Offline Flow**: No token expiration (supports uninterrupted migrations lasting weeks).

## Setup and Installation

1. **Clone and prepare the environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install dropbox google-api-python-client google-auth-httplib2 google-auth-oauthlib fastapi uvicorn python-dotenv
   ```

2. **Configure Google APIs**:
   - Go to Google Cloud Console and create a project.
   - Enable the *Google Drive API*.
   - Create Desktop Credentials (OAuth 2.0 Client ID) and download the JSON file.
   - Rename the file to `credentials.json` and place it in the project root.

3. **Configure Dropbox APIs**:
   - Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps).
   - Create a Scoped Access app and grant `files.content.read` and `files.metadata.read` permissions. (Remember to click Submit!).
   - Note down the **App Key** and **App Secret**.
   - Create a `.env` file in the project root and insert:
     ```env
     DROPBOX_APP_KEY="your_app_key"
     DROPBOX_APP_SECRET="your_app_secret"
     ```

## Starting the Migration

For the best experience, open two terminal windows:

**Terminal 1 (Web Dashboard):**
```bash
source venv/bin/activate
python web_server.py
```
Open `http://localhost:8000` in your browser to see the live statistics.

**Terminal 2 (Core Engine):**
```bash
source venv/bin/activate
python main.py
```
On the very first run, you will be provided a link to authorize Dropbox (paste the auth code back into the terminal). A browser window will also open to authorize Google Drive.

From this point on, follow the on-screen instructions. In case of an interruption (Ctrl+C), restarting the script will allow you to skip scanning and immediately resume the queue.

## Notes
All migrated files are placed into a master folder named `000 Backup Dropbox` within your Google Drive, faithfully replicating the original directory tree.
