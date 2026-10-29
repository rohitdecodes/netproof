"""Read-only tools the agent can call, plus the JSON schemas sent to the model."""
from __future__ import annotations

from typing import Callable, Dict, List

from .intent import Flow
from .schemas import FAULT_CLASS_CHOICES
from .topology import Topology

MAX_OUTPUT_CHARS = 3500


def _fn(name: str, description: str, properties: dict, required: List[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required,
                           "additionalProperties": False},
        },
    }


def tool_schemas(topo: Topology) -> List[dict]:
    devices = sorted(topo.nodes)
    dev = {"type": "string", "enum": devices}
    target = {"type": "string", "description": "device name or IPv4 address"}
    plan_props = {
        "device": dev,
        "commands": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
        "rationale": {"type": "string"},
        "expected_effect": {"type": "string"},
        "rollback": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "blast_radius": {"type": "string"},
    }
    return [
        _fn("ping", "Ping a target from a device (3 packets). Optional size sends larger packets with "
            "the don't-fragment bit set, to test path MTU.",
            {"src": dev, "dst": target,
             "size": {"type": "integer", "description": "payload bytes, 56 to 1472 (optional)"}},
            ["src", "dst"]),
        _fn("traceroute", "Trace the route from a device to a target.", {"src": dev, "dst": target},
            ["src", "dst"]),
        _fn("show_routes", "Show the routing table of a device.", {"device": dev}, ["device"]),
        _fn("show_addresses", "Show interfaces with link state and MTU, and IPv4 addresses of a device.",
            {"device": dev}, ["device"]),
        _fn("show_firewall", "Show iptables filter rules with packet counters on a device.",
            {"device": dev}, ["device"]),
        _fn("show_neighbors", "Show the ARP/neighbor table of a device.", {"device": dev}, ["device"]),
        _fn("test_flow", "Test reachability from a device to a target. tcp = connect only; "
            "tcp-bulk = connect and send 64 KB (detects MTU problems); icmp = one ping.",
            {"src": dev, "dst": target, "proto": {"type": "string", "enum": ["tcp", "tcp-bulk", "icmp"]},
             "port": {"type": "integer", "description": "required for tcp and tcp-bulk"}},
            ["src", "dst", "proto"]),
        _fn("note_hypothesis", "Record a hypothesis and the evidence for and against it.",
            {"hypothesis": {"type": "string"}, "evidence_for": {"type": "string"},
             "evidence_against": {"type": "string"},
             "status": {"type": "string", "enum": ["open", "confirmed", "rejected"]}},
            ["hypothesis", "status"]),
        _fn("submit_plan",
            "Submit the root cause and ONE change plan for a single device. The plan is checked by a "
            "policy gate, applied, and verified against the whole network; failures are rolled back.",
            {"root_cause": {"type": "object", "properties": {
                "device": dev,
                "fault_class": {"type": "string", "enum": FAULT_CLASS_CHOICES},
                "summary": {"type": "string"}},
                "required": ["device", "fault_class", "summary"], "additionalProperties": False},
             "plan": {"type": "object", "properties": plan_props,
                      "required": ["device", "commands", "rationale", "expected_effect", "rollback"],
                      "additionalProperties": False}},
            ["root_cause", "plan"]),
    ]


def wrap(device: str, cmd: str, text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + "\n[output truncated]"
    return f"<device_output device=\"{device}\" command=\"{cmd}\">\n{text}\n</device_output>"


class ToolBox:
    """Dispatches read-only tool calls to the lab. Never runs model-provided strings."""

    def __init__(self, lab, topo: Topology):
        self.lab = lab
        self.topo = topo
        self.hypotheses: List[dict] = []
        self._handlers: Dict[str, Callable[[dict], str]] = {
            "ping": self._ping,
            "traceroute": self._traceroute,
            "show_routes": lambda a: self._run(a["device"], ["ip", "route", "show"]),
            "show_addresses": self._addresses,
            "show_firewall": self._firewall,
            "show_neighbors": lambda a: self._run(a["device"], ["ip", "neigh", "show"]),
            "test_flow": self._test_flow,
            "note_hypothesis": self._note,
        }

    def names(self) -> List[str]:
        return list(self._handlers)

    def dispatch(self, name: str, args: dict) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return f"ERROR: unknown tool {name!r}"
        try:
            for key in ("device", "src"):
                if key in args and args[key] not in self.topo.nodes:
                    return f"ERROR: unknown device {args[key]!r}"
            return handler(args)
        except KeyError as e:
            return f"ERROR: missing argument {e}"
        except ValueError as e:
            return f"ERROR: {e}"

    def _run(self, device: str, argv: List[str]) -> str:
        r = self.lab.exec(device, argv, timeout=15)
        return wrap(device, " ".join(argv), r.text() or f"(no output, exit {r.code})")

    def _ping(self, a: dict) -> str:
        ip = self.topo.resolve(a["dst"])
        argv = ["ping", "-c", "3", "-i", "0.2", "-W", "1"]
        if a.get("size") is not None:
            size = int(a["size"])
            if not 56 <= size <= 1472:
                return "ERROR: size must be between 56 and 1472"
            argv += ["-s", str(size), "-M", "do"]
        return self._run(a["src"], argv + [ip])

    def _traceroute(self, a: dict) -> str:
        ip = self.topo.resolve(a["dst"])
        return self._run(a["src"], ["traceroute", "-n", "-w", "1", "-q", "1", "-m", "6", ip])

    def _addresses(self, a: dict) -> str:
        d = a["device"]
        links = self.lab.exec(d, ["ip", "-o", "link", "show"]).text()
        addrs = self.lab.exec(d, ["ip", "-br", "-4", "addr", "show"]).text()
        return wrap(d, "ip -o link; ip -br -4 addr", links + "\n\n" + addrs)

    def _firewall(self, a: dict) -> str:
        d = a["device"]
        rules = self.lab.exec(d, ["iptables", "-S"]).text()
        counters = self.lab.exec(d, ["iptables", "-L", "FORWARD", "-n", "-v", "--line-numbers"]).text()
        return wrap(d, "iptables -S; iptables -L FORWARD -n -v --line-numbers", rules + "\n\n" + counters)

    def _test_flow(self, a: dict) -> str:
        proto = a["proto"]
        if proto in ("tcp", "tcp-bulk") and not a.get("port"):
            return f"ERROR: port is required for {proto}"
        flow = Flow("adhoc", a["src"], a["dst"], proto, a.get("port"), "allow")
        if a["dst"] not in self.topo.nodes:
            self.topo.resolve(a["dst"])  # validates the address
        reachable = self.lab.run_flow(flow)
        return f"{flow.describe()}: {'REACHABLE' if reachable else 'NOT REACHABLE'}"

    def _note(self, a: dict) -> str:
        self.hypotheses.append(dict(a))
        return f"Hypothesis recorded ({len(self.hypotheses)} so far)."
