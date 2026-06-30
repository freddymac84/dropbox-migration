import sqlite3
import datetime
import os

class DBManager:
    def __init__(self, db_path='migration_state.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
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

    def get_pending_file(self):
        # We process one file at a time or in small batches
        cur = self.conn.cursor()
        cur.execute('''
            SELECT * FROM files
            WHERE status IN ('PENDING', 'DOWNLOADED') 
            ORDER BY id ASC
            LIMIT 1
        ''')
        return cur.fetchone()

    def get_file_by_path(self, dropbox_path):
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
        
        with self.conn:
            self.conn.execute(query, tuple(params))
            
    def get_stats(self):
        cur = self.conn.cursor()
        cur.execute('SELECT status, COUNT(*) as count FROM files GROUP BY status')
        stats = {row['status']: row['count'] for row in cur.fetchall()}
        return stats
        
    def reset_errors(self):
        with self.conn:
            self.conn.execute("UPDATE files SET status = 'PENDING', error_message = NULL WHERE status = 'ERROR'")
            
    def close(self):
        self.conn.close()
