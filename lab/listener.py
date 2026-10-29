"""TCP listeners that read until the client closes, then close.

A blocked flow times out. A reachable flow connects. Reading everything the client
sends lets bulk tests (64 KB) succeed only when large packets actually get through.
"""
import os
import signal
import socket
import sys
import threading

PORTS = [int(p) for p in os.environ.get("LISTEN_PORTS", "80,445,8080").split(",") if p.strip()]


def drain(conn: socket.socket) -> None:
    conn.settimeout(10)
    try:
        while conn.recv(65536):
            pass
    except OSError:
        pass
    finally:
        conn.close()


def serve(port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(64)
    while True:
        try:
            conn, _ = s.accept()
            threading.Thread(target=drain, args=(conn,), daemon=True).start()
        except OSError:
            continue


for p in PORTS:
    threading.Thread(target=serve, args=(p,), daemon=True).start()

signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
print(f"listener ready on {PORTS}", flush=True)
signal.pause()
