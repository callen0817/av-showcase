import sys
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import logging
import traceback
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("av_backend.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

for handler in logging.root.handlers:
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.info("AV Showcase Backend v2.0 Starting Up (AV Spatial Bundle v1.1)...")

from ingestion import IngestionManager
import walkthrough_synth as ws

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

def reset_progress():
    global progress_state
    progress_state = {"status": "processing", "progress": 0, "message": "Starting processing..."}

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
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b'{}'
        
        try:
            payload = json.loads(post_data.decode('utf-8')) if post_data else {}
        except json.JSONDecodeError:
            self._send_response(400, {"error": "Invalid JSON"})
            return

        endpoint = self.path
        
        if endpoint == '/api/status':
            self._send_response(200, progress_state)
            
        elif endpoint == '/api/detect':
            target_path = payload.get('path')
            if not target_path:
                self._send_response(400, {"error": "Missing 'path'"})
                return
            result = ws.detect_input(target_path)
            self._send_response(200, result)

        elif endpoint == '/api/set_transform':
            project_dir = payload.get('project_dir')
            scan_id = payload.get('scan_id')
            transform = payload.get('transform')
            if not project_dir or not scan_id or not transform or len(transform) != 16:
                self._send_response(400, {"error": "Missing project_dir, scan_id, or valid 16-element transform"})
                return
            try:
                mgr = IngestionManager(project_dir, "")
                ok, res = mgr.set_scan_transform(scan_id, transform)
                if ok:
                    self._send_response(200, {"status": "success", "scan": res})
                else:
                    self._send_response(400, {"error": res})
            except Exception as e:
                logging.error(f"set_transform failed: {e}")
                self._send_response(500, {"error": str(e)})

        elif endpoint == '/api/ingest':
            logging.info("=== INCOMING INGEST REQUEST ===")
            logging.info(f"Keys present: {list(payload.keys())}")
            
            project_dir = payload.get('project_dir')
            project_name = payload.get('project_name', 'Unnamed Project')
            e57_path = payload.get('e57_path')
            panos_path = payload.get('panos_path')
            csv_path = payload.get('csv_path')
            slam_path = payload.get('slam_path')
            source_path = payload.get('source_path')
            scan_date = payload.get('scan_date') or "2026-01-01"
            scan_label = payload.get('scan_label')
            import_mode = payload.get('import_mode', 'linked')
            auto_align = bool(payload.get('auto_align', False))
            station_spacing = float(payload.get('station_spacing', ws.DEFAULT_SPACING))
            up_axis = payload.get('up_axis', 'z')
            pano_width = int(payload.get('pano_width', 2048))
            floor_threshold = payload.get('floor_threshold', 0.25)
            floor_heights = payload.get('floor_heights', '')
            scantype = payload.get('type') or payload.get('scantype')
            
            logging.info("--- INGESTION REQUEST PARSED ---")
            logging.info(f"  scantype: '{scantype}'")
            logging.info(f"  project_dir: {project_dir}")
            logging.info(f"  source_path: {source_path or e57_path}")
            logging.info(f"  scan_date: {scan_date}, label: {scan_label}")
            logging.info(f"  auto_align: {auto_align}, spacing: {station_spacing}")
            logging.info("-------------------------------")

            if not project_dir or not scantype:
                self._send_response(400, {"error": "Missing project_dir or type"})
                return

            # Auto-detect mode if requested
            if scantype == 'Auto-Detect':
                detect_target = source_path or e57_path or panos_path
                detected = ws.detect_input(detect_target)
                if not detected.get("type"):
                    self._send_response(400, {"error": f"Auto-detection failed: {detected.get('error')}"})
                    return
                scantype = detected["type"]
                if "bundle" in detected or "zip" in detected:
                    source_path = detected.get("bundle") or detected.get("zip")
                elif "cloud" in detected:
                    source_path = detected["cloud"]
                elif "e57" in detected:
                    e57_path = detected["e57"]
                logging.info(f"Auto-Detect resolved to '{scantype}', target: {source_path or e57_path}")

            if scantype == 'SLAM':
                if not slam_path:
                    self._send_response(400, {"error": "Missing AV_Structure.exe path."})
                    return
                mgr = IngestionManager(project_dir, project_name)
                success, msg = mgr.launch_av_structure(slam_path)
                if success:
                    self._send_response(200, {"status": "success", "message": "SLAM processing bypassed to native AV Structure application."})
                else:
                    self._send_response(500, {"error": msg})
                return

            reset_progress()

            def run_worker(target_fn, desc):
                def worker():
                    try:
                        update_progress(5, f"Initializing {desc}...")
                        target_fn()
                        update_progress(100, "Walkthrough generated successfully!", status="success")
                    except Exception as e:
                        logging.error(f"Ingestion crashed: {str(e)}")
                        logging.error(traceback.format_exc())
                        update_progress(0, f"Ingestion Failed: {str(e)}", status="failed")
                t = threading.Thread(target=worker)
                t.daemon = True
                t.start()

            if scantype == 'AV Spatial Bundle':
                bundle_target = source_path or e57_path
                if not bundle_target:
                    self._send_response(400, {"error": "Missing bundle JSON / zip file path"})
                    return
                def do_bundle():
                    mgr = IngestionManager(project_dir, project_name)
                    mgr.import_spatial_bundle(bundle_target, scan_date=scan_date, scan_label=scan_label,
                                              import_mode=import_mode, progress_cb=update_progress)
                run_worker(do_bundle, "AV Spatial Bundle Importer")
                self._send_response(200, {"status": "started", "project_dir": project_dir, "type": scantype})

            elif scantype == 'Raw Point Cloud':
                cloud_target = source_path or e57_path
                if not cloud_target:
                    self._send_response(400, {"error": "Missing point cloud file path (.ply, .las, .laz, .pcd, .xyz, .obj, .e57)"})
                    return
                def do_cloud():
                    mgr = IngestionManager(project_dir, project_name, floor_threshold=floor_threshold, floor_heights=floor_heights)
                    mgr.process_point_cloud(cloud_target, scan_date, scan_label=scan_label, import_mode=import_mode,
                                            auto_align=auto_align, station_spacing=station_spacing, up_axis=up_axis,
                                            pano_width=pano_width, progress_cb=update_progress)
                run_worker(do_cloud, "Universal Point Cloud Synthesizer")
                self._send_response(200, {"status": "started", "project_dir": project_dir, "type": scantype})

            elif scantype == 'Matterport MatterPak':
                pak_target = source_path or panos_path or e57_path
                if not pak_target:
                    self._send_response(400, {"error": "Missing MatterPak zip or folder path"})
                    return
                def do_pak():
                    mgr = IngestionManager(project_dir, project_name, floor_threshold=floor_threshold, floor_heights=floor_heights)
                    mgr.process_matterpak(pak_target, scan_date, scan_label=scan_label, import_mode=import_mode,
                                          auto_align=auto_align, station_spacing=station_spacing, pano_width=pano_width,
                                          progress_cb=update_progress)
                run_worker(do_pak, "Matterport MatterPak Importer")
                self._send_response(200, {"status": "started", "project_dir": project_dir, "type": scantype})

            elif scantype == 'Structured E57':
                if not e57_path or not scan_date:
                    self._send_response(400, {"error": "Missing e57_path or scan_date"})
                    return
                validate_file_type(e57_path, "e57")
                def do_e57():
                    mgr = IngestionManager(project_dir, project_name, floor_threshold=floor_threshold, floor_heights=floor_heights)
                    mgr.process_structured_e57(e57_path, scan_date, scan_label=scan_label, import_mode=import_mode,
                                               description="Structured E57 Ingest", auto_align=auto_align, progress_cb=update_progress)
                run_worker(do_e57, "Structured E57 Engine")
                self._send_response(200, {"status": "started", "project_dir": project_dir, "type": scantype})

            elif scantype == 'E57 + Panos Folder':
                if not e57_path or not panos_path or not scan_date:
                    self._send_response(400, {"error": "Missing e57_path, panos_path, or scan_date"})
                    return
                validate_file_type(e57_path, "e57")
                def do_panos():
                    mgr = IngestionManager(project_dir, project_name, floor_threshold=floor_threshold, floor_heights=floor_heights)
                    mgr.process_e57_plus_panos(e57_path, panos_path, scan_date, scan_label=scan_label, import_mode=import_mode,
                                               auto_align=auto_align, progress_cb=update_progress)
                run_worker(do_panos, "E57 + Panos Engine")
                self._send_response(200, {"status": "started", "project_dir": project_dir, "type": scantype})

            elif scantype == 'E57 + Panos + CSV':
                if not e57_path or not panos_path or not csv_path or not scan_date:
                    self._send_response(400, {"error": "Missing e57_path, panos_path, csv_path, or scan_date"})
                    return
                validate_file_type(e57_path, "e57")
                validate_file_type(csv_path, "csv")
                def do_csv():
                    mgr = IngestionManager(project_dir, project_name, floor_threshold=floor_threshold, floor_heights=floor_heights)
                    mgr.process_e57_plus_panos(e57_path, panos_path, scan_date, scan_label=scan_label, csv_pose_file=csv_path,
                                               import_mode=import_mode, auto_align=auto_align, progress_cb=update_progress)
                run_worker(do_csv, "E57 + Panos + CSV Engine")
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
        pass

def run_server(port=8000):
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, RestRequestHandler)
    print(f"AV Showcase Python backend listening on port {port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

if __name__ == '__main__':
    run_server()
