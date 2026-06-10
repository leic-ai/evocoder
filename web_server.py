"""EvoCoder WebSocket API Server

Bridges the GUI frontend with the EvoCoder Python backend.
Provides real-time streaming of agent thinking, tool calls, and responses.

Protocol:
  Client -> Server: JSON messages
    {"type": "chat", "message": "user input"}
    {"type": "stats"}
    {"type": "tools"}
    {"type": "evolve"}
    {"type": "memory"}
    {"type": "clear"}
    {"type": "stop"}

  Server -> Client: JSON messages
    {"type": "thinking", "step": N}
    {"type": "tool_call", "tool": "name", "args": {...}, "step": N}
    {"type": "tool_result", "tool": "name", "result": "...", "success": true, "step": N}
    {"type": "content", "text": "partial response"}
    {"type": "done", "result": "full response", "elapsed": 1.23}
    {"type": "error", "message": "error description"}
    {"type": "stats_response", "data": {...}}
    {"type": "tools_response", "data": [...]}
    {"type": "evolve_response", "data": {...}}
    {"type": "memory_response", "data": {...}}
    {"type": "stopped"}
"""

import os
import sys
import json
import time
import asyncio
import threading
import traceback
import mimetypes
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

# Fix UnicodeEncodeError on Windows (agent prints emoji)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to path
APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT))

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip install websockets")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv()

from agent import EvoCoder


class EvoServer:
    """WebSocket server wrapping EvoCoder agent."""

    def __init__(self, api_key: str = None, model: str = None,
                 workspace: str = ".evocoder", host: str = "127.0.0.1",
                 port: str = 8765, static_dir: str = None, http_port: int = 8080):
        self.host = host
        self.port = port
        self.static_dir = static_dir
        self.http_port = http_port
        self._http_server = None
        self.agent = None
        self._api_key = api_key or os.getenv("MIMO_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        self._model = model
        self._base_url = "https://api.xiaomimimo.com/v1"
        self._workspace = workspace
        self._active_task = None
        self._clients = set()
        # Lock to serialize agent access (prevents method corruption)
        self._agent_lock = threading.Lock()

    def _init_agent(self):
        """Lazy-init the EvoCoder agent."""
        if self.agent is None:
            if not self._api_key:
                raise ValueError("No API key. Set DEEPSEEK_API_KEY in .env")
            self.agent = EvoCoder(
                api_key=self._api_key,
                base_url=self._base_url,
                model=self._model,
                workspace=self._workspace,
            )

    async def _send(self, ws, msg: dict):
        """Send JSON message to client."""
        try:
            await ws.send(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    async def _handle_chat(self, ws, message: str):
        """Handle a chat message with streaming updates."""
        self._init_agent()
        start_time = time.time()

        # Thread-safe queue for agent -> async communication
        msg_queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def emit_event(msg_dict):
            """Thread-safe event emitter called by agent."""
            try:
                loop.call_soon_threadsafe(lambda m=msg_dict: msg_queue.put_nowait(m))
            except Exception:
                pass  # loop may be closed

        try:
            # Start agent in thread executor (serialized by lock)
            agent_task = asyncio.ensure_future(
                loop.run_in_executor(None, self._run_agent, message, emit_event)
            )

            # Drain queue and forward to client until agent completes
            while not agent_task.done() or not msg_queue.empty():
                try:
                    msg = await asyncio.wait_for(msg_queue.get(), timeout=0.2)
                    await self._send(ws, msg)
                except asyncio.TimeoutError:
                    continue

            # Get agent result (re-raises exceptions)
            result = agent_task.result()
            elapsed = time.time() - start_time
            await self._send(ws, {
                "type": "done",
                "result": result,
                "elapsed": round(elapsed, 2),
            })

        except asyncio.CancelledError:
            await self._send(ws, {"type": "stopped"})
        except Exception as e:
            await self._send(ws, {
                "type": "error",
                "message": f"{type(e).__name__}: {str(e)}",
            })

    def _run_agent(self, message: str, emit_event) -> str:
        """Run agent in a thread with event callbacks.

        Uses run_stream() for clean event-based streaming — no monkey-patching.
        """
        from agent_events import EventType

        with self._agent_lock:
            self._init_agent()
            final_result = ""

            for event in self.agent.run_stream(message):
                etype = event.type

                if etype == EventType.THINKING:
                    emit_event({"type": "thinking", "step": event.step})

                elif etype == EventType.CONTENT_TOKEN:
                    emit_event({
                        "type": "content_token",
                        "token": event.data.get("token", ""),
                        "step": event.step,
                    })

                elif etype == EventType.CONTENT:
                    emit_event({
                        "type": "content",
                        "text": event.data.get("text", ""),
                        "step": event.step,
                    })

                elif etype == EventType.TOOL_CALL:
                    args = event.data.get("args", {})
                    # 代码字段保留完整，其他截断
                    FULL_KEYS = {"content", "new_string", "old_string", "code"}
                    safe_args = {}
                    for k, v in args.items():
                        s = str(v)
                        safe_args[k] = s if k in FULL_KEYS else s[:200]
                    emit_event({
                        "type": "tool_call",
                        "tool": event.data.get("name", "?"),
                        "args": safe_args,
                        "step": event.step,
                    })

                elif etype == EventType.TOOL_RESULT:
                    emit_event({
                        "type": "tool_result",
                        "tool": event.data.get("name", "?"),
                        "result": event.data.get("result", "")[:500],
                        "success": not event.data.get("is_error", False),
                        "step": event.step,
                    })

                elif etype == EventType.PITFALL_WARNING:
                    emit_event({
                        "type": "pitfall",
                        "error_type": event.data.get("error_type", "?"),
                        "hint": event.data.get("hint", ""),
                        "step": event.step,
                    })

                elif etype == EventType.EVOLUTION:
                    emit_event({
                        "type": "evolution",
                        "category": event.data.get("category", "?"),
                        "action": event.data.get("action", ""),
                        "step": event.step,
                    })

                elif etype == EventType.ERROR:
                    emit_event({
                        "type": "error",
                        "message": event.data.get("message", "Unknown error"),
                        "step": event.step,
                    })

                elif etype == EventType.SUMMARY:
                    final_result = event.data.get("result", "")
                    emit_event({
                        "type": "summary",
                        "result": final_result,
                        "success": event.data.get("success", False),
                        "total_time": event.data.get("total_time", 0),
                        "tokens_out": event.data.get("tokens_out", 0),
                        "step": event.step,
                    })

            return final_result

    async def _handle_stats(self, ws):
        """Return agent statistics."""
        self._init_agent()
        stats = self.agent.get_stats()
        serializable = json.loads(json.dumps(stats, default=str))
        await self._send(ws, {"type": "stats_response", "data": serializable})

    async def _handle_tools(self, ws):
        """Return tool list."""
        self._init_agent()
        tools = self.agent.registry.list_tools()
        await self._send(ws, {"type": "tools_response", "data": tools})

    async def _handle_evolve(self, ws):
        """Return evolution status."""
        self._init_agent()
        status = self.agent.get_evolution_status()
        await self._send(ws, {"type": "evolve_response", "data": status})

    async def _handle_memory(self, ws):
        """Return memory stats."""
        self._init_agent()
        summary = self.agent.memory.summary()
        long_term = self.agent.long_term.summary()
        await self._send(ws, {
            "type": "memory_response",
            "data": {"memory": summary, "long_term": long_term},
        })

    async def _handle_clear(self, ws):
        """Clear conversation session."""
        if self.agent:
            self.agent.memory.clear_conversation()
            self.agent.memory.clear_working()
        await self._send(ws, {"type": "cleared"})

    async def _handler(self, ws):
        """Main WebSocket connection handler."""
        self._clients.add(ws)
        remote = ws.remote_address
        print(f"[WS] Client connected: {remote}")

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send(ws, {"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "chat":
                    message = msg.get("message", "").strip()
                    if not message:
                        await self._send(ws, {"type": "error", "message": "Empty message"})
                        continue
                    if self._active_task and not self._active_task.done():
                        self._active_task.cancel()
                    self._active_task = asyncio.create_task(
                        self._handle_chat(ws, message)
                    )

                elif msg_type == "stop":
                    if self._active_task and not self._active_task.done():
                        self._active_task.cancel()
                        await self._send(ws, {"type": "stopped"})

                elif msg_type == "stats":
                    await self._handle_stats(ws)

                elif msg_type == "tools":
                    await self._handle_tools(ws)

                elif msg_type == "evolve":
                    await self._handle_evolve(ws)

                elif msg_type == "memory":
                    await self._handle_memory(ws)

                elif msg_type == "clear":
                    await self._handle_clear(ws)

                elif msg_type == "config":
                    # Update API configuration
                    new_key = msg.get("api_key", "")
                    new_url = msg.get("base_url", "")
                    new_model = msg.get("model", "")
                    if new_key:
                        self._api_key = new_key
                    if new_url:
                        self._base_url = new_url
                    if new_model:
                        self._model = new_model
                    # Reset agent so it re-inits with new config
                    self.agent = None
                    await self._send(ws, {"type": "config_updated", "data": {
                        "base_url": self._base_url, "model": self._model,
                    }})

                elif msg_type == "ping":
                    await self._send(ws, {"type": "pong"})

                elif msg_type == "list_files":
                    await self._handle_list_files(ws, msg.get("path", "."))

                elif msg_type == "read_file":
                    await self._handle_read_file(ws, msg.get("path", ""))

                elif msg_type == "run_code":
                    await self._handle_run_code(ws, msg.get("code", ""), msg.get("lang", ""), msg.get("file", ""))

                else:
                    await self._send(ws, {
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })

        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            print(f"[WS] Error: {e}")
            traceback.print_exc()
        finally:
            self._clients.discard(ws)
            print(f"[WS] Client disconnected: {remote}")

    async def _handle_list_files(self, ws, path: str):
        """List files in a directory for the file browser panel.

        Skips hidden files and __pycache__. Returns a list of file entries
        with name, path, is_dir, and size fields.

        Args:
            ws: WebSocket connection.
            path: Directory path to list ("." for current working directory).
        """
        import os
        target = Path(path).resolve() if path != "." else Path.cwd()
        if not target.is_dir():
            await self._send(ws, {"type": "error", "message": f"Not a directory: {path}"})
            return
        files = []
        try:
            for entry in sorted(target.iterdir()):
                if entry.name.startswith(".") or entry.name == "__pycache__":
                    continue
                files.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": entry.is_dir(),
                    "size": entry.stat().st_size if entry.is_file() else 0,
                })
        except PermissionError:
            pass
        await self._send(ws, {"type": "file_list", "files": files})

    async def _handle_read_file(self, ws, path: str):
        """Read a file and send its content to the frontend.

        Large files are truncated to 50K chars. Content is sent as UTF-8
        with replacement characters for invalid bytes.

        Args:
            ws: WebSocket connection.
            path: File path to read.
        """
        if not path:
            await self._send(ws, {"type": "error", "message": "No path provided"})
            return
        fp = Path(path).resolve()
        if not fp.is_file():
            await self._send(ws, {"type": "error", "message": f"File not found: {path}"})
            return
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
            # 截断大文件
            if len(content) > 50000:
                content = content[:50000] + "\n... (truncated, file too large)"
            await self._send(ws, {"type": "file_content", "path": str(fp), "content": content})
        except Exception as e:
            await self._send(ws, {"type": "error", "message": str(e)})

    async def _handle_run_code(self, ws, code: str, lang: str, file: str):
        """Execute code from the GUI and return stdout/stderr/exit_code.

        Supports Python, JavaScript (Node.js), and Bash. Code is written to
        a temp file, executed with a 30s timeout, and the temp file is cleaned up.

        Args:
            ws: WebSocket connection.
            code: Source code string to execute.
            lang: Language identifier ("python", "javascript", "bash").
            file: Original filename (used to infer language if lang is empty).
        """
        import subprocess, sys, tempfile
        if not code:
            await self._send(ws, {"type": "error", "message": "No code to run"})
            return

        # 根据语言选择运行方式
        ext_map = {"python": ".py", "javascript": ".js", "bash": ".sh", "sh": ".sh"}
        ext = ext_map.get(lang, Path(file).suffix if file else ".py")

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as f:
                f.write(code)
                tmp_path = f.name

            if ext == ".py":
                cmd = [sys.executable, tmp_path]
            elif ext == ".js":
                cmd = ["node", tmp_path]
            elif ext in (".sh",):
                cmd = ["bash", tmp_path]
            else:
                cmd = [sys.executable, tmp_path]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace"
            )
            await self._send(ws, {
                "type": "run_result",
                "stdout": result.stdout[:10000],
                "stderr": result.stderr[:5000],
                "exit_code": result.returncode,
            })
        except subprocess.TimeoutExpired:
            await self._send(ws, {"type": "run_result", "stdout": "", "stderr": "Timeout (30s)", "exit_code": -1})
        except FileNotFoundError as e:
            await self._send(ws, {"type": "run_result", "stdout": "", "stderr": f"Runtime not found: {e}", "exit_code": -1})
        except Exception as e:
            await self._send(ws, {"type": "run_result", "stdout": "", "stderr": str(e), "exit_code": -1})
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    async def run(self):
        """Start the WebSocket server."""
        print(f"[EVO] Starting WebSocket server on ws://{self.host}:{self.port}")
        print(f"[EVO] API Key: {'*' * 8 if self._api_key else 'NOT SET'}")
        print(f"[EVO] Model: {self._model or 'default'}")
        print(f"[EVO] Workspace: {self._workspace}")

        # Start HTTP static file server if configured
        if self.static_dir:
            self._start_static_server()

        async with websockets.serve(
            self._handler,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10,
            max_size=10 * 1024 * 1024,
        ):
            print(f"[EVO] Server ready at ws://{self.host}:{self.port}")
            await asyncio.Future()  # run forever

    def _start_static_server(self):
        """Start HTTP server to serve frontend dist in a daemon thread."""
        static_path = Path(self.static_dir).resolve()
        if not static_path.is_dir():
            print(f"[EVO] WARNING: Static dir not found: {static_path}")
            return

        class StaticHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(static_path), **kwargs)

            def log_message(self, format, *args):
                pass

            def end_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache")
                super().end_headers()

        self._http_server = HTTPServer((self.host, self.http_port), StaticHandler)
        thread = threading.Thread(target=self._http_server.serve_forever, daemon=True)
        thread.start()
        print(f"[EVO] Static UI serving at http://{self.host}:{self.http_port}")
        print(f"[EVO]   from: {static_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="EvoCoder WebSocket Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    parser.add_argument("--api-key", help="DeepSeek API key")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--workspace", default=".evocoder", help="Workspace dir")
    parser.add_argument("--static-dir", default=None, help="Static files directory for frontend UI")
    parser.add_argument("--http-port", type=int, default=8080, help="HTTP port for static files")
    args = parser.parse_args()

    # Auto-detect static dir: look for gui/ directory
    static_dir = args.static_dir
    if static_dir is None:
        gui_dir = Path(__file__).resolve().parent / "gui"
        if gui_dir.is_dir():
            static_dir = str(gui_dir)

    server = EvoServer(
        api_key=args.api_key,
        model=args.model,
        workspace=args.workspace,
        host=args.host,
        port=args.port,
        static_dir=static_dir,
        http_port=args.http_port,
    )
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
