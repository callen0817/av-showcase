Created At: 2026-07-02T03:41:50Z
Completed At: 2026-07-02T03:41:50Z
File Path: `file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py`
Total Lines: 527
Total Bytes: 21545
Showing lines 1 to 527
The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.
1: import os
2: import json
3: import shutil
4: import math
5: from pathlib import Path
6: import traceback
7: import struct
8: import numpy as np
9: import logging
10: 
11: try:
12:     from sklearn.neighbors import NearestNeighbors
13:     import pye57
14: except ImportError:
15:     pass
16: 
17: def dump_e57_tree(node, path="root", depth=0):
18:     """Recursively log the structure of an E57 tree for diagnostics."""
19:     try:
20:         logging.info(f"{'  '*depth}{path}: {type(node).__name__}")
21:         if hasattr(node, "childCount"):
22:             for i in range(node.childCount()):
23:                 try:
24:                     child = node.get(i)
25:                     dump_e57_tree(child, f"{path}/{i}", depth+1)
26:                 except: continue
27:         elif hasattr(node, "keys"):
28:             for key in node.keys():
29:                 try:
30:                     child = node[key]
31:                     dump_e57_tree(child, f"{path}/{key}", depth+1)
32:                 except: continue
33:     except Exception as e:
34:         logging.error(f"Error dumping tree at {path}: {e}")
35: 
36: def find_nodes_by_name(node, target_names, found=None, path="root"):
37:     """Recursively search for nodes by name (case-insensitive)."""
38:     if found is None: found = []
39:     target_names = [t.lower() for t in target_names]
40:     try:
41:         if hasattr(node, "keys"):
42:             for key in node.keys():
43:                 child = node[key]
44:                 if key.lower() in target_names:
45:        
<truncated 20544 bytes>
:         num_files = len(files)
482:         
483:         for i, f in enumerate(files):
484:             if progress_cb: progress_cb(20 + int(70 * i / num_files), f"Indexing {f.name}...")
485:             target_name = f"pano_{i:03d}.jpg"
486:             shutil.copy(f, scan_dir / "panos" / target_name)
487:             
488:             # Simulated grid for unstructured panos (3m spacing)
489:             cols = max(1, int(math.sqrt(num_files)))
490:             x = (i % cols) * 3.0
491:             y = (i // cols) * 3.0
492:             
493:             panos.append({
494:                 "id": f"pano_{i:03d}",
495:                 "image_path": f"panos/{target_name}",
496:                 "position": [x, y, 0.0],
497:                 "rotation": [0, 0, 0, 1],
498:                 "floor_id": 1,
499:                 "neighbors": []
500:             })
501: 
502:         # Generate links based on proximity
503:         panos = self._generate_navigation_graph(panos)
504:         
505:         scan_data = {
506:             "scan_date": scan_date,
507:             "description": "Matterpak/Panos Ingestion",
508:             "panos": panos,
509:             "floors": [{"id": 1, "min_z": -1.0, "max_z": 1.0}]
510:         }
511:         
512:         with open(scan_dir / "scan.json", "w") as f:
513:             json.dump(scan_data, f, indent=2)
514: 
515:             
516:         # Update project level JSON
517:         with open(self.project_json_path, "r") as f:
518:             proj = json.load(f)
519:         
520:         if not any(s['scan_date'] == scan_date for s in proj['scans']):
521:             proj['scans'].append({"scan_date": scan_date, "description": "Matterpak Import"})
522:             proj['scans'].sort(key=lambda x: x['scan_date'], reverse=True)
523:             with open(self.project_json_path, "w") as f:
524:                 json.dump(proj, f, indent=2)
525:                 
526:         return scan_data
527: 
The above content shows the entire, complete file contents of the requested file.
