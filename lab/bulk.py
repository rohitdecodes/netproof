"""Bulk transfer test: connect, send N bytes, half-close, wait for the server to close.

Usage: python3 /opt/np/bulk.py <ip> <port> <bytes> <timeout_seconds>
Exit 0 only if every byte was accepted and the server closed cleanly.
"""
import socket
import sys

ip, port, nbytes, timeout = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
try:
    s = socket.create_connection((ip, port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(b"x" * nbytes)
    s.shutdown(socket.SHUT_WR)
    while s.recv(4096):
        pass
    s.close()
except OSError as e:
    print(f"bulk transfer failed: {e}", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
