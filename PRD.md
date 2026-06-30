# Product Requirements Document (PRD)
## Dropbox to Google Drive Migration Tool

### 1. Project Purpose
The goal is to safely, verifiably, and continuously migrate 1.5 TB of data from a paid Dropbox account to a Google Drive space, preserving the original folder structure.
The system operates on a local machine with limited disk space (max 135GB free), which is why a "Stream-and-Delete" approach was chosen (download a file, upload it, delete it locally).

### 2. System Architecture
The system consists of two separate processes sharing a SQLite database (`migration_state.db`):
- **Migration Engine (`main.py`)**: Python CLI script that orchestrates the download and upload of files. Uses a **Hybrid Concurrent Architecture** with thread pools for parallel processing.
- **Web Dashboard (`web_server.py`)**: FastAPI web server for real-time monitoring of the queue and errors.

### 3. Data Flow and Core Business Rules

#### A. File Scanning and Status
1. On startup, the system maps the entire Dropbox file tree and inserts it into the SQLite database with `PENDING` status.
2. Upon restart, the system offers to **skip scanning** (if the DB already has files) to save time.
3. If there are files in `ERROR` status from previous cycles, the system asks the user if they want to reset them to `PENDING` to process them first.

#### B. Limited Disk Space & Hybrid Transfer Management
To bypass the 135GB disk space constraint and maximize throughput, the system employs a dual-strategy:
1. **Zero-Copy RAM Streaming (< 50MB)**: 10 parallel small-file workers download data from Dropbox directly into RAM (`io.BytesIO`) and stream it instantly to Google Drive. The disk is completely bypassed, eliminating local I/O bottlenecks.
2. **Chunked Disk Transfer (>= 50MB)**: Large files are routed to 2 dedicated Downloader and 2 Uploader threads. They are temporarily written to the local `tmp_migration/` folder. Once uploaded to Google Drive and validated, the local file **MUST be deleted** immediately.
3. **Database Concurrency**: The SQLite DB utilizes transactional row locking (`with self.conn`) when fetching `PENDING` files to ensure multiple threads never overlap on the same file.

#### C. Integrity Check (Digital Fingerprint)
1. For each downloaded file, an **MD5 Checksum** is calculated locally.
2. During upload, the MD5 is sent to Google Drive (`md5Checksum`).
3. If the MD5 or file size on Google Drive differs from the local file, the upload is considered failed and the file transitions to `ERROR` status.

#### D. Authentication and Resilience
1. **Google Drive**: Uses OAuth2.0 with `credentials.json` and a persistent token generated on the first run.
2. **Dropbox**: Uses OAuth2.0 Offline Flow (`APP_KEY` and `APP_SECRET`) to generate a Refresh Token. This ensures access never expires (standard tokens only last 4 hours).
3. **Network Error Handling**: If the Dropbox API times out or hits a Rate Limit (HTTP 429), the client waits and retries using Exponential Backoff.
4. **Unsupported File Handling**: "Cloud-Only" files (e.g., Google Docs created in Dropbox) throw a specific `ApiError`. The system instantly recognizes this, skips the file, and marks it as `ERROR` without blocking the queue with infinite retries.

### 4. UI/UX Requirements (Dashboard)
- The web interface (Vanilla JS/HTML/Tailwind) displays real-time counters by querying the server every 2 seconds.
- Uses a **Single Page Application** (SPA) architecture to display Completed and Error files.
- The display of 146,000 files is **paginated in blocks of 50** via backend API to prevent browser crashes.
- The Error page shows the exact reason for failure provided by the API (`error_summary`) and offers a "**Retry**" button to dynamically put the file back in the queue via API.
- A **Top Level Overall Progress** bar that estimates the global ETA and tracks total data transferred against the entire repository size.
- **Active Operations** rows that track the real-time chunked transfer speeds for both the ongoing Download and Upload independently.

## Features Documentation
*(Future complex features should be documented in `docs/features/` and linked here).*
- [UX Dashboard Improvements](docs/features/ux_dashboard_improvements.md)
