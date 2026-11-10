import sys
sys.path.insert(0, r"c:\Users\ChristopherAllen\OneDrive - Reisource\Desktop\AV_Walkthrough\backend")
from ingestion import IngestionManager

proj_dir = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon"
mgr = IngestionManager(proj_dir, "", floor_threshold=0.25, floor_heights="1, mezz")
ok, data = mgr.recluster_project()
print(f"Recluster status: {ok}")
if ok:
    sc = data['scans'][0]
    print("Floors generated:", len(sc['floors']))
    for f in sc['floors']:
        print(f"  Floor {f['id']}: name={f.get('name')}, min_z={f['min_z']:.2f}, max_z={f['max_z']:.2f}")
    
    panos = sc['panos']
    print(f"Total panos: {len(panos)}")
    f1_panos = [p for p in panos if p['floor_id'] == 1]
    f2_panos = [p for p in panos if p['floor_id'] == 2]
    print(f"Floor 1 panos: {len(f1_panos)}, Floor 2 panos: {len(f2_panos)}")
    
    cross_floor = []
    for p in panos:
        for nid in p['neighbors']:
            np = next(x for x in panos if x['id'] == nid)
            if np['floor_id'] != p['floor_id']:
                cross_floor.append((p['id'], p['floor_id'], nid, np['floor_id']))
    print(f"Cross-floor stair links: {len(cross_floor)}")
    for link in cross_floor[:6]:
        print(f"  {link[0]} (F{link[1]}) <---> {link[2]} (F{link[3]})")
