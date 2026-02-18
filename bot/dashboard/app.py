"""
Flask web dashboard for Web Traffic Bot.

Provides a browser UI to configure and run the bot without touching the CLI.
Logs are streamed live to the browser via Server-Sent Events (SSE).
"""

import logging
import queue
import threading
from typing import Optional

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

_bot_thread: Optional[threading.Thread] = None
_bot_instance = None   # live TrafficBot reference for real-time stats
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
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    # Set level so DEBUG messages from bot modules reach the dashboard
    handler.setLevel(logging.DEBUG)
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)


_attach_queue_handler()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    # Pre-join proxies into a newline-separated string for the textarea
    proxies_str = "\n".join(_current_config.get("proxies") or [])
    return render_template("index.html", config=_current_config, proxies_str=proxies_str)


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(_current_config)


@app.route("/api/config", methods=["POST"])
def save_config():
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


@app.route("/api/stats", methods=["GET"])
def bot_stats():
    """Return live session counters from the running bot."""
    if _bot_instance is not None:
        return jsonify({
            "completed": _bot_instance.sessions_completed,
            "failed":    _bot_instance.sessions_failed,
            "total":     _bot_instance.config.sessions_count,
        })
    return jsonify({"completed": 0, "failed": 0, "total": 0})


@app.route("/api/start", methods=["POST"])
def start_bot():
    global _bot_thread

    with _bot_lock:
        if _bot_thread is not None and _bot_thread.is_alive():
            return jsonify({"status": "error", "message": "Bot is already running"}), 409

        if not _current_config.get("target_url"):
            return jsonify({"status": "error", "message": "target_url is required"}), 400

        # Drain old log messages (thread-safe: keep trying until empty)
        while True:
            try:
                _log_queue.get_nowait()
            except queue.Empty:
                break

        config = ConfigHandler()
        config.config.update(_current_config)

        def _run():
            global _bot_instance
            try:
                bot = TrafficBot(config)
                _bot_instance = bot
                bot.run()
            except Exception as exc:
                logging.getLogger(__name__).error(f"Bot crashed: {exc}")
            finally:
                _bot_instance = None

        _bot_thread = threading.Thread(target=_run, daemon=True, name="bot-worker")
        _bot_thread.start()

    return jsonify({"status": "ok", "message": "Bot started"})


@app.route("/api/stop", methods=["POST"])
def stop_bot():
    """
    Request a graceful stop.  TrafficBot checks the flag between sessions.
    A hard stop requires restarting the server process.
    """
    running = _bot_thread is not None and _bot_thread.is_alive()
    if not running:
        return jsonify({"status": "ok", "message": "Bot is not running"})

    from bot.traffic_bot import request_stop
    request_stop()
    return jsonify({
        "status": "ok",
        "message": "Stop signal sent — bot will exit after the current session",
    })


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
                # Keep-alive ping so the browser doesn't close the connection
                yield ": ping\n\n"

    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Entry point (used by `web-traffic-bot --dashboard`)
# ---------------------------------------------------------------------------

def run_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False) -> None:
    print(f"\n  Web Traffic Bot Dashboard → http://localhost:{port}\n")
    app.run(host=host, port=port, debug=debug, threaded=True)
