import sys
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import logging
import traceback

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("av_backend.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Force flush on logging
for handler in logging.root.handlers:
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.info("AV Walkthrough Backend v31.1 Starting Up (Architecture Lockdown)...")

from ingestion import IngestionManager

# Global state to track background ingestion progress
progress_state = {
    "status": "idle",
    "progress": 0,
    "message": ""
}

def update_progress(progress, message, status="processing"):
    global progress_state
    logging.info(f"Progress update: {progress}% - {message}")
    progress_state["progress"] = progress
    progress_state["message"] = message
    progress_state["status"] = status

def validate_file_type(filepath, expected_type):
    if not filepath: return
    ext = filepath.lower().split('.')[-1]
    if expected_type == "e57" and ext != "e57":
        raise ValueError(f"Selected type requires an E57 file, but got '.{ext}' ({os.path.basename(filepath)})")
    if expected_type == "xyz" and ext != "xyz":
        raise ValueError(f"Selected type requires an XYZ file, but got '.{ext}' ({os.path.basename(filepath)})")
    if expected_type == "las" and ext not in ["las", "laz"]:
        raise ValueError(f"Selected type requires a LAS or LAZ file, but got '.{ext}' ({os.path.basename(filepath)})")


class RestRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global progress_state
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_response(400, {"error": "Invalid JSON"})
            return

        endpoint = self.path
        
        if endpoint == '/api/status':
            self._send_response(200, progress_state)
        elif endpoint == '/api/ingest':
            logging.info("=== INCOMING INGEST REQUEST ===")
            logging.info(f"Keys present: {list(payload.keys())}")
            
            project_dir = payload.get('project_dir')
            project_name = payload.get('project_name', 'Unnamed Project')
            e57_path = payload.get('e57_path')
            panos_path = payload.get('panos_path')
            csv_path = payload.get('csv_path')
            slam_path = payload.get('slam_path')
            scan_date = payload.get('scan_date')
            import_mode = payload.get('import_mode', 'linked')
            floor_threshold = payload.get('floor_threshold', 0.25)
            floor_heights = payload.get('floor_heights', '')
            # Support both 'type' and 'scantype' for robustness
            scantype = payload.get('type') or payload.get('scantype')
            
            logging.info("--- INGESTION REQUEST PARSED ---")
            logging.info(f"  scantype: '{scantype}'")
            logging.info(f"  project_dir: {project_dir}")
            logging.info(f"  e57_path: {e57_path}")
            logging.info(f"  panos_path: {panos_path}")
            logging.info(f"  scan_date: {scan_date}")
            logging.info(f"  import_mode: {import_mode}")
            logging.info("-------------------------------")

            
            if not project_dir or not scantype:
                self._send_response(400, {"error": "Missing project_dir or type"})
                return
                
            if scantype == 'SLAM':
                if not slam_path:
                    self._send_response(400, {"error": "Missing AV_Structure.exe path."})
                    return
                # Launch AV Structure natively from user path
                mgr = IngestionManager(project_dir, project_name)
                success, msg = mgr.launch_av_structure(slam_path)
                if success:
                    self._send_response(200, {"status": "success", "message": "SLAM processing bypassed to native AV Structure application."})
                else:
                    self._send_response(500, {"error": msg})
                return
                
            if scantype == 'Structured E57':
                if not e57_path or not scan_date:
                    self._send_response(400, {"error": "Missing e57_path or scan_date"})
                    return
                validate_file_type(e57_path, "e57")
                
                progress_state = {"status": "processing", "progress": 0, "message": "Starting Structured E57 Ingestion..."}
                
                def run_ingest():
                    global progress_state
                    update_progress(5, "Initializing Structured E57 engine...")
                    try:
                        mgr = IngestionManager(project_dir, project_name, floor_threshold=floor_threshold, floor_heights=floor_heights)
                        mgr.process_structured_e57(e57_path, scan_date, import_mode=import_mode, description="Structured E57 Ingest", progress_cb=update_progress)
                        update_progress(100, "Walkthrough generated successfully!", status="success")
                    except Exception as e:
                        logging.error(f"Ingestion crashed: {str(e)}")
                        logging.error(traceback.format_exc())
                        update_progress(0, f"Ingestion Failed: {str(e)}", status="failed")
                
                t = threading.Thread(target=run_ingest)
                t.start()
                self._send_response(200, {"status": "started", "project_dir": project_dir, "type": scantype})

            elif scantype == 'E57 + Panos Folder':
                if not e57_path or not panos_path or not scan_date:
                    self._send_response(400, {"error": "Missing e57_path, panos_path, or scan_date"})
                    return
                validate_file_type(e57_path, "e57")
                
                progress_state = {"status": "processing", "progress": 0, "message": "Starting E57 + Panos Ingestion..."}
                
                def run_ingest():
                    global progress_state
                    update_progress(5, "Initializing E57 + Panos engine...")
                    try:
                        mgr = IngestionManager(project_dir, project_name, floor_threshold=floor_threshold, floor_heights=floor_heights)
                        mgr.process_e57_plus_panos(e57_path, panos_path, scan_date, import_mode=import_mode, progress_cb=update_progress)
                        update_progress(100, "Walkthrough generated successfully!", status="success")
                    except Exception as e:
                        logging.error(f"Ingestion crashed: {str(e)}")
                        logging.error(traceback.format_exc())
                        update_progress(0, f"Ingestion Failed: {str(e)}", status="failed")
                
                t = threading.Thread(target=run_ingest)
                t.start()
                self._send_response(200, {"status": "started", "project_dir": project_dir, "type": scantype})

            elif scantype == 'E57 + Panos + CSV':
                if not e57_path or not panos_path or not csv_path or not scan_date:
                    self._send_response(400, {"error": "Missing e57_path, panos_path, csv_path, or scan_date"})
                    return
                validate_file_type(e57_path, "e57")
                validate_file_type(csv_path, "csv")
                
                progress_state = {"status": "processing", "progress": 0, "message": "Starting E57 + Panos + CSV Ingestion..."}
                
                def run_ingest():
                    global progress_state
                    update_progress(5, "Initializing E57 + Panos + CSV engine...")
                    try:
                        mgr = IngestionManager(project_dir, project_name, floor_threshold=floor_threshold, floor_heights=floor_heights)
                        mgr.process_e57_plus_panos(e57_path, panos_path, scan_date, csv_pose_file=csv_path, import_mode=import_mode, progress_cb=update_progress)
                        update_progress(100, "Walkthrough generated successfully!", status="success")
                    except Exception as e:
                        logging.error(f"Ingestion crashed: {str(e)}")
                        logging.error(traceback.format_exc())
                        update_progress(0, f"Ingestion Failed: {str(e)}", status="failed")
                
                t = threading.Thread(target=run_ingest)
                t.start()
                self._send_response(200, {"status": "started", "project_dir": project_dir, "type": scantype})
            else:
                self._send_response(400, {"error": f"Unsupported scan type: {scantype}"})
                
        elif endpoint == '/api/align':
            mgr = IngestionManager("", "")
            success, msg = mgr.launch_av_snap()
            if success:
                self._send_response(200, {"status": "success", "message": "Launched AV Snap."})
            else:
                self._send_response(500, {"error": msg})
        elif endpoint == '/api/recluster':
            project_dir = payload.get('project_dir')
            floor_threshold = payload.get('floor_threshold', 0.25)
            floor_heights = payload.get('floor_heights', '')
            if not project_dir:
                self._send_response(400, {"error": "Missing project_dir"})
                return
            try:
                mgr = IngestionManager(project_dir, "", floor_threshold=floor_threshold, floor_heights=floor_heights)
                ok, result = mgr.recluster_project()
                if ok:
                    self._send_response(200, {"status": "success", "data": result})
                else:
                    self._send_response(400, {"error": result})
            except Exception as e:
                logging.error(f"Recluster failed: {e}")
                self._send_response(500, {"error": str(e)})
        else:
            self._send_response(404, {"error": "Endpoint not found"})

    def _send_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress logging to keep stdin/stdout clean for IPC if needed
        pass

def run_server(port=8000):
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, RestRequestHandler)
    print(f"AV Walkthrough Python backend listening on port {port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

if __name__ == '__main__':
    run_server()
