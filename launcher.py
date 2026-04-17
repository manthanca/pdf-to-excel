#!/usr/bin/env python3
"""
MRACA Smart Contract Note Converter — Windows Launcher
Starts the Streamlit server and opens the app in the default browser.
"""

import os
import sys
import subprocess
import threading
import webbrowser
import time


def get_base_dir() -> str:
    """Return the directory that contains the bundled app files."""
    if getattr(sys, "frozen", False):
        # Running inside a PyInstaller bundle
        return sys._MEIPASS
    # Running as a plain Python script
    return os.path.dirname(os.path.abspath(__file__))


def get_python() -> str:
    """Return the Python executable to use."""
    if getattr(sys, "frozen", False):
        # When frozen, use the exe's own Python (bundled by PyInstaller)
        return sys.executable
    return sys.executable


def open_browser(port: int = 8501, delay: float = 4.0):
    """Wait briefly, then open the app in the browser."""
    time.sleep(delay)
    webbrowser.open(f"http://localhost:{port}")


def main():
    base_dir = get_base_dir()
    app_script = os.path.join(base_dir, "app_final.py")
    port = 8501

    print("=" * 55)
    print("  MRACA Smart Contract Note Converter")
    print("  Starting server — please wait…")
    print(f"  URL: http://localhost:{port}")
    print("=" * 55)

    # Open browser in background after server is ready
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    # Launch Streamlit
    cmd = [
        get_python(), "-m", "streamlit", "run", app_script,
        "--server.port", str(port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]

    try:
        proc = subprocess.run(cmd, cwd=os.getcwd())
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
