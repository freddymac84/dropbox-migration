from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = 'migration_state.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/stats")
def get_stats():
    if not os.path.exists(DB_PATH):
        return {"status": "Waiting for database to be created..."}
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get counts
        cur.execute('SELECT status, COUNT(*) as count FROM files GROUP BY status')
        counts_raw = cur.fetchall()
        counts = {row['status']: row['count'] for row in counts_raw}
        
        # Get total size migrated
        cur.execute("SELECT SUM(size) as total_size FROM files WHERE status = 'COMPLETED'")
        size_row = cur.fetchone()
        total_size = size_row['total_size'] if size_row['total_size'] else 0
        
        # Get last 20 files
        cur.execute('''
            SELECT dropbox_path, size, status, error_message, updated_at 
            FROM files 
            ORDER BY updated_at DESC 
            LIMIT 20
        ''')
        recent_files = [dict(row) for row in cur.fetchall()]
        
        current_progress = None
        try:
            if os.path.exists('progress.json'):
                with open('progress.json', 'r') as f:
                    import json, time
                    current_progress = json.load(f)
                    
                if current_progress:
                    transferred = current_progress.get('transferred', 0)
                    total = current_progress.get('total', 1)
                    start_time = current_progress.get('start_time', 0)
                    updated_at = current_progress.get('updated_at', 0)
                    
                    elapsed = updated_at - start_time
                    speed_bps = transferred / elapsed if elapsed > 0 else 0
                    
                    current_progress['percent'] = (transferred / total) * 100 if total > 0 else 0
                    current_progress['speed_bps'] = speed_bps
                    
                    # If not updated for 15 seconds, it's likely finished or frozen
                    import time as time_module
                    if time_module.time() - updated_at > 15:
                        current_progress = None
        except Exception:
            pass
            
        conn.close()
        
        return {
            "counts": counts,
            "total_migrated_bytes": total_size,
            "recent_files": recent_files,
            "current_progress": current_progress
        }
    except Exception as e:
        return {"status": f"Database error: {e}"}

from pydantic import BaseModel

class RetryRequest(BaseModel):
    dropbox_path: str

@app.get("/api/files/detail")
def get_files_detail(status: str, page: int = 1, limit: int = 50):
    if not os.path.exists(DB_PATH):
        return {"items": [], "total_pages": 0}
        
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        offset = (page - 1) * limit
        
        cur.execute("SELECT COUNT(*) as total FROM files WHERE status = ?", (status,))
        total_items = cur.fetchone()['total']
        total_pages = (total_items + limit - 1) // limit
        
        cur.execute('''
            SELECT dropbox_path, size, status, error_message, updated_at 
            FROM files 
            WHERE status = ?
            ORDER BY updated_at DESC 
            LIMIT ? OFFSET ?
        ''', (status, limit, offset))
        
        files = [dict(row) for row in cur.fetchall()]
        conn.close()
        
        return {
            "items": files,
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        }
    except Exception as e:
        return {"status": f"Database error: {e}"}

@app.post("/api/files/retry")
def retry_file(req: RetryRequest):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE files SET status = 'PENDING', error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE dropbox_path = ?", (req.dropbox_path,))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Mount static files
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("Starting Web UI at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
