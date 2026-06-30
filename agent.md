# Agent Memory & Context Window
> **Instructions for Gemini / Future LLM Agents**
> If you are an AI reading this file, you have been instantiated to continue working on the "Dropbox to GDrive Migration" repository. Treat this document as your primary source of contextual truth.

## Meta-Rules for Agents (CRITICAL)
1. **Self-Updating Documentation Loop**: Every time you implement a new feature or change the architecture, you **MUST** update:
   - `agent.md` (if your working methods or core constraints change).
   - `README.md` (to document the new feature for users).
   - `PRD.md` (to keep the high-level architecture design in sync).
2. **Feature Documentation**: For complex features, create a dedicated markdown file in a `docs/features/` folder and link it from the `PRD.md` to avoid bloating the main document.
3. **Language Consistency**: All code comments, documentation, UI text, and terminal outputs MUST be written in English.

## Repository Purpose
A Python tool to migrate large volumes of data from Dropbox to Google Drive with high resiliency, using a SQLite DB queue (`migration_state.db`) and a real-time FastAPI dashboard.

## System Architecture & Patterns

1. **Storage Constraint Strategy**:
   The user has ~135GB of disk space and 1.5TB of data to migrate.
   **CRITICAL PATTERN**: Files are downloaded to `tmp_migration/`. Once `gdrive_client.upload_file` succeeds and checksums are validated, the local file MUST be deleted immediately. Do not modify this pipeline to store files in batch.

2. **Database & Resumability**:
   `DBManager` handles the queue. Files start as `PENDING`, transition to `DOWNLOADED` (briefly), then `COMPLETED` or `ERROR`.
   On startup (`main.py`), the system checks for `ERROR` files and prompts the user to reset them to `PENDING` via `db.reset_errors()`.

3. **API Handling**:
   - **Dropbox**: We use OAuth2 Offline Flow (`dropbox_client.py`) with `app_key` and `app_secret` from `.env`. The refresh token is saved in `dropbox_token.json`. We DO NOT use short-lived manual tokens anymore.
   - **Error Handling**: `dropbox_client.py` uses a `@with_retry` decorator. Transient errors trigger Exponential Backoff. However, structural API Errors (e.g., `ApiError` indicating a Cloud-only Google Doc hosted in Dropbox) are immediately raised and marked as `ERROR` in the DB to avoid infinite retry loops.

4. **Web UI Architecture**:
   - Run via `web_server.py` (FastAPI).
   - The frontend (`static/index.html`) is a Vanilla JS Single Page Application.
   - It fetches global stats every 2 seconds (`/api/stats`).
   - Detailed views (Errors/Completed) are **paginated** (`/api/files/detail`) to handle 150k+ rows without freezing the browser.
   - A realtime progress bar reads from `progress.json` to show active chunk streaming.

## Do's and Don'ts for the Agent
- **DO NOT** rewrite the UI using heavy frontend frameworks (React/Vue). Keep it Vanilla JS + Tailwind.
- **DO NOT** remove the MD5 Checksum validation logic in `migrator.py`.
- **DO** use paginated SQL queries when adding new features to the Dashboard.
- **DO** verify that new Dropbox/GDrive API calls are wrapped in exception handlers with backoff.
- **DO** ask the user to restart the background python processes if you edit their code.
