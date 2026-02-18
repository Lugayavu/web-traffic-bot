"""
Flask web dashboard for Web Traffic Bot.

Provides a browser UI to configure and run the bot without touching the CLI.
Logs are streamed live to the browser via Server-Sent Events (SSE).
"""

import logging
import queue
import threading

from flask import Flask, Response, jsonify, render_template, request

from bot.config_handler import ConfigHandler
from bot.traffic_bot import TrafficBot

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder="templates", static_folder="static")

# ---------------------------------------------------------------------------
# Global bot state
# ---------------------------------------------------------------------------

_bot_thread: threading.Thread | None = None
_bot_lock = threading.Lock()
_log_queue: queue.Queue = queue.Queue(maxsize=500)

# Current config (persisted in memory between page loads)
_current_config: dict = {
    "target_url": "",
    "sessions_count": 10,
    "session_duration": 45,
    "duration_seconds": 600,
    "proxies": [],
    "headless": True,
    "chromium_path": "",
}


# ---------------------------------------------------------------------------
# Log handler that feeds the SSE queue
# ---------------------------------------------------------------------------

class _QueueHandler(logging.Handler):
    """Push log records into the SSE queue."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _log_queue.put_nowait(self.format(record))
        except queue.Full:
            pass


def _attach_queue_handler() -> None:
    """Attach the queue handler to the root logger (once)."""
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, _QueueHandler):
            return  # already attached
    handler = _QueueHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                          datefmt="%H:%M:%S")
    )
    root.addHandler(handler)


_attach_queue_handler()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", config=_current_config)


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(_current_config)


@app.route("/api/config", methods=["POST"])
def save_config():
    global _current_config
    data = request.get_json(force=True)

    # Sanitise / coerce types
    _current_config["target_url"] = str(data.get("target_url", "")).strip()
    _current_config["sessions_count"] = int(data.get("sessions_count", 10))
    _current_config["session_duration"] = int(data.get("session_duration", 45))
    _current_config["duration_seconds"] = int(data.get("duration_seconds", 600))
    _current_config["headless"] = bool(data.get("headless", True))
    _current_config["chromium_path"] = str(data.get("chromium_path", "")).strip()

    raw_proxies = data.get("proxies", [])
    if isinstance(raw_proxies, str):
        # Accept newline- or comma-separated string from the textarea
        raw_proxies = [p.strip() for p in raw_proxies.replace(",", "\n").splitlines()]
    _current_config["proxies"] = [p for p in raw_proxies if p]

    return jsonify({"status": "ok", "config": _current_config})


@app.route("/api/status", methods=["GET"])
def bot_status():
    running = _bot_thread is not None and _bot_thread.is_alive()
    return jsonify({"running": running})


@app.route("/api/start", methods=["POST"])
def start_bot():
    global _bot_thread

    with _bot_lock:
        if _bot_thread is not None and _bot_thread.is_alive():
            return jsonify({"status": "error", "message": "Bot is already running"}), 409

        if not _current_config.get("target_url"):
            return jsonify({"status": "error", "message": "target_url is required"}), 400

        # Drain old log messages
        while not _log_queue.empty():
            try:
                _log_queue.get_nowait()
            except queue.Empty:
                break

        config = ConfigHandler()
        config.config.update(_current_config)

        def _run():
            try:
                bot = TrafficBot(config)
                bot.run()
            except Exception as exc:
                logging.getLogger(__name__).error(f"Bot crashed: {exc}")

        _bot_thread = threading.Thread(target=_run, daemon=True, name="bot-worker")
        _bot_thread.start()

    return jsonify({"status": "ok", "message": "Bot started"})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    """
    There is no clean way to kill a thread in Python.
    We signal the bot by setting a flag that TrafficBot checks.
    For now we just report the status; a hard stop requires the user
    to restart the server process.
    """
    running = _bot_thread is not None and _bot_thread.is_alive()
    if not running:
        return jsonify({"status": "ok", "message": "Bot is not running"})
    # Best-effort: set a stop flag that TrafficBot will pick up
    from bot import traffic_bot as _tb
    _tb._STOP_REQUESTED = True
    return jsonify({"status": "ok", "message": "Stop signal sent — bot will finish the current session then exit"})


@app.route("/api/logs")
def stream_logs():
    """Server-Sent Events endpoint — streams log lines to the browser."""

    def _generate():
        yield "data: --- Log stream started ---\n\n"
        while True:
            try:
                line = _log_queue.get(timeout=20)
                # Escape newlines inside the log line so SSE stays valid
                safe = line.replace("\n", " ").replace("\r", "")
                yield f"data: {safe}\n\n"
            except queue.Empty:
                # Keep-alive ping
                yield ": ping\n\n"

    return Response(_generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Entry point (used by `web-traffic-bot --dashboard`)
# ---------------------------------------------------------------------------

def run_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    print(f"\n  Web Traffic Bot Dashboard → http://{host}:{port}\n")
    app.run(host=host, port=port, debug=debug, threaded=True)
