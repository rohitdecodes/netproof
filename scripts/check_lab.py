"""Step 5 check: provision every node to its baseline and print the intent table.

Usage:  python scripts/check_lab.py
"""
import sys
import time

sys.path.insert(0, ".")
from netproof.intent import evaluate, format_table, is_healthy, load_intent  # noqa: E402
from netproof.lab import DockerLab  # noqa: E402
from netproof.topology import load_topology  # noqa: E402

topo = load_topology()
lab = DockerLab(topo)
t = time.monotonic()
lab.provision_all()
print(f"provisioned {len(topo.nodes)} nodes in {time.monotonic() - t:.1f}s")
for node in topo.nodes:
    print(f"  {node:<11} interfaces: {lab.iface_map(node)}")
res = evaluate(lab, load_intent())
print()
print(format_table(res))
healthy = is_healthy(res)
print("\nHEALTHY" if healthy else "\nNOT HEALTHY")
sys.exit(0 if healthy else 1)
