"""PyInstaller entry point for the standalone owscout desktop app.

Build a single distributable .exe (no Python install needed on the target
machine) with:

    .venv\\Scripts\\pip install pyinstaller
    .venv\\Scripts\\pyinstaller --onefile --windowed --name owscout owscout_app.py

The result is dist\\owscout.exe. The capture extras (dxcam/opencv/numpy/keyboard)
must be installed in the build environment so PyInstaller bundles them.
"""

from owscout.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
