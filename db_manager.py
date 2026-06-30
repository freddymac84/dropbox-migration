import sqlite3
import datetime
import os
import threading

class DBManager:
    def __init__(self, db_path='migration_state.db'):
        self.db_path = db_path
        # Allow multiple threads to share the same connection
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._create_tables()

    def _create_tables(self):
        with self.lock:
            with self.conn:
                self.conn.execute('''
                    CREATE TABLE IF NOT EXISTS files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        dropbox_path TEXT UNIQUE NOT NULL,
                        gdrive_id TEXT,
                        size INTEGER,
                        status TEXT DEFAULT 'PENDING',
                        error_message TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                self.conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON files(status)')

    def add_file(self, dropbox_path, size):
        with self.lock:
            with self.conn:
                try:
                    self.conn.execute('''
                        INSERT INTO files (dropbox_path, size, status)
                        VALUES (?, ?, 'PENDING')
                    ''', (dropbox_path, size))
                    return True
                except sqlite3.IntegrityError:
                    # File already exists
                    return False

    def get_small_file_to_migrate(self, threshold=52428800):
        with self.lock:
            with self.conn:
                cur = self.conn.cursor()
                cur.execute('''
                    SELECT * FROM files
                    WHERE status = 'PENDING' AND size < ?
                    ORDER BY id ASC
                    LIMIT 1
                ''', (threshold,))
                row = cur.fetchone()
                if row:
                    self.conn.execute("UPDATE files SET status = 'PROCESSING' WHERE id = ?", (row['id'],))
                return row

    def get_large_file_to_download(self, threshold=52428800):
        with self.lock:
            with self.conn:
                cur = self.conn.cursor()
                cur.execute('''
                    SELECT * FROM files
                    WHERE status = 'PENDING' AND size >= ?
                    ORDER BY id ASC
                    LIMIT 1
                ''', (threshold,))
                row = cur.fetchone()
                if row:
                    self.conn.execute("UPDATE files SET status = 'DOWNLOADING' WHERE id = ?", (row['id'],))
                return row
            
    def get_large_file_to_upload(self):
        with self.lock:
            with self.conn:
                cur = self.conn.cursor()
                cur.execute('''
                    SELECT * FROM files
                    WHERE status = 'DOWNLOADED'
                    ORDER BY id ASC
                    LIMIT 1
                ''')
                row = cur.fetchone()
                if row:
                    self.conn.execute("UPDATE files SET status = 'UPLOADING' WHERE id = ?", (row['id'],))
                return row
            
    def get_downloaded_count(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) as count FROM files WHERE status = 'DOWNLOADED'")
            row = cur.fetchone()
            return row['count'] if row else 0

    def get_downloaded_size(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT SUM(size) as total_size FROM files WHERE status = 'DOWNLOADED'")
            row = cur.fetchone()
            return row['total_size'] if row and row['total_size'] else 0

    def get_file_by_path(self, dropbox_path):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute('SELECT * FROM files WHERE dropbox_path = ?', (dropbox_path,))
            return cur.fetchone()

    def update_status(self, dropbox_path, status, gdrive_id=None, error_message=None):
        query = "UPDATE files SET status = ?, updated_at = CURRENT_TIMESTAMP"
        params = [status]
        
        if gdrive_id is not None:
            query += ", gdrive_id = ?"
            params.append(gdrive_id)
            
        if error_message is not None:
            query += ", error_message = ?"
            params.append(error_message)
        else:
            query += ", error_message = NULL" # Clear errors if successful
            
        query += " WHERE dropbox_path = ?"
        params.append(dropbox_path)
        
        with self.lock:
            with self.conn:
                self.conn.execute(query, tuple(params))
            
    def get_stats(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute('SELECT status, COUNT(*) as count FROM files GROUP BY status')
            stats = {row['status']: row['count'] for row in cur.fetchall()}
            return stats
        
    def reset_stuck_states(self):
        with self.lock:
            with self.conn:
                self.conn.execute("UPDATE files SET status = 'PENDING' WHERE status IN ('PROCESSING', 'DOWNLOADING')")
                self.conn.execute("UPDATE files SET status = 'DOWNLOADED' WHERE status = 'UPLOADING'")
                
    def reset_errors(self):
        with self.lock:
            with self.conn:
                self.conn.execute("UPDATE files SET status = 'PENDING', error_message = NULL WHERE status = 'ERROR'")
            
    def close(self):
        with self.lock:
            self.conn.close()
