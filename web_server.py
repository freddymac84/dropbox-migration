from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import time
from collections import deque

app = FastAPI()

speed_history = deque(maxlen=20) # Store (timestamp, total_migrated_bytes)
last_total_migrated = -1

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
        total_migrated_bytes = size_row['total_size'] if size_row['total_size'] else 0
        
        # Get total overall size
        cur.execute("SELECT SUM(size) as total_size FROM files")
        total_size_row = cur.fetchone()
        total_bytes = total_size_row['total_size'] if total_size_row['total_size'] else 0

        # Calculate global speed and ETA
        global speed_history, last_total_migrated
        current_time = time.time()
        
        if total_migrated_bytes != last_total_migrated:
            speed_history.append((current_time, total_migrated_bytes))
            last_total_migrated = total_migrated_bytes
            
        global_speed_bps = 0
        eta_seconds = 0
        if len(speed_history) > 1:
            first_time, first_bytes = speed_history[0]
            last_time, last_bytes = speed_history[-1]
            elapsed = last_time - first_time
            if elapsed > 0:
                global_speed_bps = (last_bytes - first_bytes) / elapsed
                
        if global_speed_bps > 0 and total_bytes > total_migrated_bytes:
            eta_seconds = (total_bytes - total_migrated_bytes) / global_speed_bps
            
        # Get last 20 files
        cur.execute('''
            SELECT dropbox_path, size, status, error_message, updated_at 
            FROM files 
            ORDER BY updated_at DESC 
            LIMIT 20
        ''')
        recent_files = [dict(row) for row in cur.fetchall()]
        
        current_download = None
        current_upload = None
        try:
            if os.path.exists('progress.json'):
                with open('progress.json', 'r') as f:
                    import json
                    prog_state = json.load(f)
                    
                now = time.time()
                
                def parse_prog(p):
                    if not p: return None
                    if now - p.get('updated_at', 0) > 15: return None
                    
                    transferred = p.get('transferred', 0)
                    total = p.get('total', 1)
                    start_time = p.get('start_time', 0)
                    updated_at = p.get('updated_at', 0)
                    
                    elapsed = updated_at - start_time
                    speed_bps = transferred / elapsed if elapsed > 0 else 0
                    
                    p['percent'] = (transferred / total) * 100 if total > 0 else 0
                    p['speed_bps'] = speed_bps
                    return p
                    
                if 'download' in prog_state or 'upload' in prog_state:
                    current_download = parse_prog(prog_state.get('download'))
                    current_upload = parse_prog(prog_state.get('upload'))
                else:
                    # fallback for old schema
                    if prog_state.get('action') == 'DOWNLOADING':
                        current_download = parse_prog(prog_state)
                    elif prog_state.get('action') == 'UPLOADING':
                        current_upload = parse_prog(prog_state)
        except Exception:
            pass
            
        conn.close()
        
        return {
            "stats": counts,
            "total_bytes": total_bytes,
            "total_migrated_bytes": total_migrated_bytes,
            "global_speed_bps": global_speed_bps,
            "eta_seconds": eta_seconds,
            "recent_files": recent_files,
            "current_download": current_download,
            "current_upload": current_upload
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
