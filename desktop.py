"""EVOcoder Desktop App

Launches the EvoCoder agent in a native desktop window.
No npm/build step required — the frontend is a self-contained HTML file.

Usage:
    python desktop.py
    python desktop.py --model deepseek-v4-pro
"""

import os
import sys
import time
import socket
import subprocess
import threading
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT))

from dotenv import load_dotenv
load_dotenv()

GUI_DIR = APP_ROOT / "gui"
HTML_FILE = GUI_DIR / "index.html"


def kill_port(port: int):
    """Kill process on port (Windows)."""
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            )
            killed = False
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    if pid.isdigit() and int(pid) > 0:
                        subprocess.run(
                            ["taskkill", "/F", "/PID", pid],
                            capture_output=True, timeout=5,
                        )
                        killed = True
            if killed:
                time.sleep(1)
            else:
                return True
        except Exception:
            time.sleep(1)
    return False


def wait_for_port(port: int, timeout: int = 15) -> bool:
    """Wait until a port accepts connections."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def start_ws_server(api_key: str, model: str, port: int) -> subprocess.Popen:
    """Start WebSocket server as subprocess."""
    cmd = [sys.executable, str(APP_ROOT / "web_server.py"), "--port", str(port)]
    if api_key:
        cmd.extend(["--api-key", api_key])
    if model:
        cmd.extend(["--model", model])

    # Hide console window on Windows
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    proc = subprocess.Popen(
        cmd, cwd=str(APP_ROOT),
        startupinfo=startupinfo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if wait_for_port(port, timeout=15):
        return proc
    else:
        proc.terminate()
        raise RuntimeError(f"WebSocket server failed to start on port {port}")


def serve_html(html_path: str, port: int):
    """Serve a single HTML file via HTTP in a thread."""
    import http.server
    import functools

    directory = str(Path(html_path).parent)

    class SingleFileHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, format, *args):
            pass  # Suppress HTTP logs

    server = http.server.HTTPServer(("127.0.0.1", port), SingleFileHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    return server


def cleanup_processes(ws_proc, httpd, ws_port, web_port):
    """Clean up all child processes and ports."""
    print("Shutting down...")

    # Shutdown HTTP server
    if httpd:
        try:
            httpd.shutdown()
        except Exception:
            pass

    # Terminate WebSocket server
    if ws_proc:
        try:
            ws_proc.terminate()
            ws_proc.wait(timeout=3)
        except Exception:
            try:
                ws_proc.kill()
            except Exception:
                pass

    # Force kill anything on our ports
    time.sleep(0.5)
    kill_port(ws_port)
    kill_port(web_port)
    print("Done.")


def main():
    import argparse
    import signal

    parser = argparse.ArgumentParser(description="EVOcoder Desktop")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket port")
    parser.add_argument("--web-port", type=int, default=5174, help="HTTP port")
    parser.add_argument("--api-key", help="DeepSeek API key")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--width", type=int, default=1280, help="Window width")
    parser.add_argument("--height", type=int, default=800, help="Window height")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("MIMO_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("ERROR: No API key. Set MIMO_API_KEY or DEEPSEEK_API_KEY in .env or use --api-key")
        sys.exit(1)

    if not HTML_FILE.exists():
        print(f"ERROR: Frontend not found at {HTML_FILE}")
        sys.exit(1)

    # State for cleanup
    ws_proc = None
    httpd = None

    # Register signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        cleanup_processes(ws_proc, httpd, args.ws_port, args.web_port)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 50)
    print("  EVOcoder Desktop")
    print("=" * 50)

    # Step 1: Clean ports
    print("[1/4] Cleaning ports...")
    kill_port(args.ws_port)
    kill_port(args.web_port)

    # Step 2: Start WebSocket server
    print(f"[2/4] Starting WebSocket on :{args.ws_port}...")
    try:
        ws_proc = start_ws_server(api_key, args.model, args.ws_port)
        print(f"  OK (PID {ws_proc.pid})")
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    # Step 3: Start HTTP server for frontend
    print(f"[3/4] Starting HTTP on :{args.web_port}...")
    try:
        httpd = serve_html(str(HTML_FILE), args.web_port)
        print("  OK")
    except Exception as e:
        print(f"  FAIL: {e}")
        cleanup_processes(ws_proc, None, args.ws_port, args.web_port)
        sys.exit(1)

    # Step 4: Open native window
    print("[4/4] Opening window...")
    print("=" * 50)

    try:
        import webview
    except ImportError:
        print("ERROR: pywebview not installed. Run: pip install pywebview")
        cleanup_processes(ws_proc, httpd, args.ws_port, args.web_port)
        sys.exit(1)

    window = webview.create_window(
        title="EVOcoder",
        url=f"http://127.0.0.1:{args.web_port}/index.html",
        width=args.width,
        height=args.height,
        min_size=(900, 600),
        background_color="#ffffff",
        text_select=True,
    )

    def on_loaded():
        """Bring window to front after load."""
        try:
            time.sleep(0.5)
            if sys.platform == "win32":
                import ctypes
                hwnd = ctypes.windll.user32.FindWindowW(None, "EVOcoder")
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    window.events.loaded += on_loaded

    try:
        webview.start(gui="edgechromium", debug=False)
    except Exception as e:
        print(f"Window error: {e}")
        try:
            webview.start(debug=False)
        except Exception as e2:
            print(f"Fallback error: {e2}")
    finally:
        cleanup_processes(ws_proc, httpd, args.ws_port, args.web_port)


if __name__ == "__main__":
    main()
