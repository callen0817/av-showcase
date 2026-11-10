import sys
import os
import json
import argparse
import math

def compare_vectors(v1, v2, tol=1e-4):
    if len(v1) != len(v2):
        return False
    return all(math.isclose(a, b, abs_tol=tol) for a, b in zip(v1, v2))

def run_regression_test(golden_path, test_path):
    print(f"Loading golden reference from: {golden_path}")
    with open(golden_path, 'r', encoding='utf-8') as f:
        golden_data = json.load(f)

    print(f"Loading test project from: {test_path}")
    with open(test_path, 'r', encoding='utf-8') as f:
        test_data = json.load(f)

    # 1. Compare scan date counts
    golden_scans = {s['scan_date']: s for s in golden_data.get('scans', [])}
    test_scans = {s['scan_date']: s for s in test_data.get('scans', [])}

    for date, g_scan in golden_scans.items():
        if date not in test_scans:
            raise AssertionError(f"Mismatched scan dates: date '{date}' is missing in test project.")
        
        t_scan = test_scans[date]
        
        # 2. Compare panoramas count
        g_panos = g_scan.get('panos', [])
        t_panos = t_scan.get('panos', [])
        if len(g_panos) != len(t_panos):
            raise AssertionError(f"Panoramas count mismatch for date {date}: expected {len(g_panos)}, got {len(t_panos)}")
            
        # 3. Compare floors count
        g_floors = g_scan.get('floors', [])
        t_floors = t_scan.get('floors', [])
        if len(g_floors) != len(t_floors):
            raise AssertionError(f"Floors count mismatch for date {date}: expected {len(g_floors)}, got {len(t_floors)}")

        # 4. Compare individual nodes positions & rotation
        for i in range(len(g_panos)):
            gp = g_panos[i]
            tp = t_panos[i]
            
            if gp['id'] != tp['id']:
                raise AssertionError(f"Pano ID mismatch at index {i}: expected '{gp['id']}', got '{tp['id']}'")
                
            if not compare_vectors(gp['position'], tp['position']):
                raise AssertionError(f"Pano {gp['id']} position mismatch: expected {gp['position']}, got {tp['position']}")

            if not compare_vectors(gp['rotation'], tp['rotation']):
                raise AssertionError(f"Pano {gp['id']} rotation mismatch: expected {gp['rotation']}, got {tp['rotation']}")

            # 5. Compare navigation connectivity
            gp_neighbors = sorted(gp.get('neighbors', []))
            tp_neighbors = sorted(tp.get('neighbors', []))
            if gp_neighbors != tp_neighbors:
                raise AssertionError(f"Pano {gp['id']} neighbors mismatch: expected {gp_neighbors}, got {tp_neighbors}")

    print("\n" + "="*40)
    print("REGRESSION TEST RESULT: PASSED")
    print("="*40 + "\n")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AV Walkthrough Database Regression Test")
    parser.add_argument("--test-project", required=True, help="Path to project.avproj or project.json to test")
    parser.add_argument("--golden", default=os.path.join(os.path.dirname(__file__), "golden_reference.json"), help="Path to golden reference database")
    
    args = parser.parse_args()
    
    try:
        run_regression_test(args.golden, args.test_project)
        sys.exit(0)
    except AssertionError as ae:
        print("\n" + "!"*40)
        print(f"REGRESSION TEST FAILED:\n{ae}")
        print("!"*40 + "\n")
        sys.exit(1)
