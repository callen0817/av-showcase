import sys
import os
import pye57

def dump_node(node, path="root", depth=0):
    indent = "  " * depth
    node_type = type(node).__name__
    try:
        elem_name = node.elementName()
    except AttributeError:
        elem_name = "?"
        
    print(f"{indent}- {elem_name} [{node_type}] at {path}")

    # Check for child count and recurse
    if hasattr(node, "childCount"):
        try:
            for i in range(node.childCount()):
                child = node.get(i)
                child_name = f"child_{i}"
                try:
                    child_name = child.elementName()
                except:
                    pass
                dump_node(child, path=f"{path}/{child_name}", depth=depth + 1)
        except Exception as e:
            print(f"{indent}  [Error listing children: {e}]")
    elif hasattr(node, "keys"):
        # Map element
        try:
            for k in node.keys():
                child = node[k]
                dump_node(child, path=f"{path}/{k}", depth=depth + 1)
        except Exception as e:
            print(f"{indent}  [Error listing keys: {e}]")

def diagnose_e57(filepath):
    print("==================================================")
    print(f"DIAGNOSING E57 FILE: {filepath}")
    print("==================================================")
    
    if not os.path.exists(filepath):
        print(f"Error: File not found at {filepath}")
        return

    try:
        e57 = pye57.E57(filepath)
    except Exception as e:
        print(f"Failed to open E57 file: {e}")
        return

    root = e57.root
    
    # 1. Structure overview
    print("\n1. Root level keys:")
    try:
        for i in range(root.childCount()):
            child = root.get(i)
            print(f"  - {child.elementName()} [{type(child).__name__}]")
    except Exception as e:
        print(f"  Error reading root children: {e}")

    # 2. Check data3D
    print("\n2. data3D section:")
    if "data3D" in root:
        data3d = root["data3D"]
        child_count = data3d.childCount()
        print(f"  - data3D childCount: {child_count}")
        # Inspect first scan pose if exists
        if child_count > 0:
            first_scan = data3d[0]
            print(f"  - First scanElementName: {first_scan.elementName()} [{type(first_scan).__name__}]")
            if "pose" in first_scan:
                print("    - Has 'pose' node")
                pose = first_scan["pose"]
                if "translation" in pose:
                    t = pose["translation"]
                    print(f"      - translation keys: {list(t.keys()) if hasattr(t, 'keys') else 'not a map'}")
                    if hasattr(t, "keys"):
                        print(f"        x={t['x'].value()}, y={t['y'].value()}, z={t['z'].value()}")
                if "rotation" in pose:
                    r = pose["rotation"]
                    print(f"      - rotation keys: {list(r.keys()) if hasattr(r, 'keys') else 'not a map'}")
                    if hasattr(r, "keys"):
                        print(f"        w={r['w'].value()}, x={r['x'].value()}, y={r['y'].value()}, z={r['z'].value()}")
            else:
                print("    - Does NOT have 'pose' node")
    else:
        print("  - data3D node is ABSENT")

    # 3. Check images2D
    print("\n3. images2D section:")
    if "images2D" in root:
        images2d = root["images2D"]
        child_count = images2d.childCount()
        print(f"  - images2D childCount: {child_count}")
        if child_count > 0:
            first_image = images2d[0]
            print(f"  - First image elementName: {first_image.elementName()} [{type(first_image).__name__}]")
            # Dump the first image node structure
            print("  - Structure of first image entry:")
            dump_node(first_image, path="root/images2D/0", depth=2)
    else:
        print("  - images2D node is ABSENT")

    print("\n4. Full E57 node tree dump:")
    dump_node(root)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python diagnose_e57.py <path_to_e57>")
        sys.exit(1)
        
    diagnose_e57(sys.argv[1])
