"""
Snake game server: a tiny web app to test deployments on Red Hat OpenShift.

- Python standard library only (no pip install needed).
- Listens on 0.0.0.0:$PORT (default 8080, the OpenShift convention).
- Works with the random, non-root user OpenShift runs containers with.

Endpoints:
  GET  /             -> the game (static/index.html)
  GET  /healthz      -> liveness probe   ({"status": "ok"})
  GET  /readyz       -> readiness probe  ({"status": "ready"})
  GET  /api/info     -> pod name, version, uptime (see which pod answered)
  GET  /api/score    -> best score kept by this pod
  POST /api/score    -> {"score": 12} submits a score
"""

import json
import os
import signal
import socket
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# OpenShift sets HOSTNAME to the pod name (e.g. snake-6d8f9c7b5-x2k4p).
POD_NAME = os.environ.get("HOSTNAME", socket.gethostname())
STARTED_AT = time.time()

# In-memory best score: each pod has its own, and it resets on restart.
# Useful to *see* that several replicas exist. Not a real database.
best_score = 0
best_score_lock = threading.Lock()


class SnakeHandler(SimpleHTTPRequestHandler):
    server_version = "SnakeServer/" + APP_VERSION

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    # ---------- helpers ----------

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Log to stdout so `oc logs` shows requests. Probes are skipped
        # to keep the logs readable.
        if self.path in ("/healthz", "/readyz"):
            return
        sys.stdout.write(
            f"{self.address_string()} [{self.log_date_time_string()}] "
            f"{format % args}\n"
        )
        sys.stdout.flush()

    # ---------- routes ----------

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/healthz":
            return self.send_json({"status": "ok"})

        if path == "/readyz":
            return self.send_json({"status": "ready"})

        if path == "/api/info":
            return self.send_json({
                "app": "snake",
                "version": APP_VERSION,
                "pod": POD_NAME,
                "uptime_seconds": int(time.time() - STARTED_AT),
                "python": sys.version.split()[0],
            })

        if path == "/api/score":
            with best_score_lock:
                return self.send_json({"best": best_score, "pod": POD_NAME})

        # Everything else: static files (index.html, ...).
        return super().do_GET()

    def do_POST(self):
        global best_score

        if self.path.split("?", 1)[0] != "/api/score":
            return self.send_json({"error": "not found"}, status=404)

        try:
            length = min(int(self.headers.get("Content-Length", 0)), 1024)
            data = json.loads(self.rfile.read(length) or b"{}")
            score = int(data.get("score", 0))
            if score < 0 or score > 100000:
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError):
            return self.send_json({"error": "invalid score"}, status=400)

        with best_score_lock:
            is_record = score > best_score
            if is_record:
                best_score = score
            current_best = best_score

        return self.send_json({
            "best": current_best,
            "record": is_record,
            "pod": POD_NAME,
        })


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), SnakeHandler)
    server.daemon_threads = True

    # OpenShift sends SIGTERM when a pod stops (scale down, new deploy).
    # Shut down cleanly instead of waiting to be killed.
    def stop(signum, _frame):
        print(f"Received signal {signum}, shutting down...", flush=True)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    print(
        f"Snake server v{APP_VERSION} listening on port {PORT} (pod: {POD_NAME})",
        flush=True,
    )
    server.serve_forever()
    server.server_close()
    print("Server stopped.", flush=True)


if __name__ == "__main__":
    main()
