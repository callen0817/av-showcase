libs = ['PIL', 'cv2', 'scipy', 'numpy', 'matplotlib']
for lib in libs:
    try:
        __import__(lib)
        print(f"{lib}: available")
    except ImportError:
        print(f"{lib}: NOT available")
