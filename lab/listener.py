"""Accept-and-close TCP listeners so that 'reachable' and 'blocked' are distinguishable.

A blocked flow times out. A reachable flow connects. Without a listener a reachable
host would answer with a TCP reset, which a test could misread.
"""
import os
import signal
import socket
import sys
import threading

PORTS = [int(p) for p in os.environ.get("LISTEN_PORTS", "80,445,8080").split(",") if p.strip()]


def serve(port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(64)
    while True:
        try:
            conn, _ = s.accept()
            conn.close()
        except OSError:
            continue


for p in PORTS:
    threading.Thread(target=serve, args=(p,), daemon=True).start()

signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
print(f"listener ready on {PORTS}", flush=True)
signal.pause()
