"""Test doubles: a tiny fake lab and a scripted fake model. No Docker, no network."""
from __future__ import annotations

import copy
import json
from typing import List

from netproof.lab import ExecResult

GOOD_ROUTE = "ip route replace 10.10.3.0/24 via 10.10.9.2"
OPEN_GUEST = "iptables -I FORWARD 1 -s 10.10.2.0/24 -d 10.10.3.0/24 -j ACCEPT"
ADD_JUNK = "iptables -I FORWARD 1 -s 10.10.9.9 -j DROP"
DEL_JUNK = "iptables -D FORWARD -s 10.10.9.9 -j DROP"
STATE_KEYS = ("route_ok", "guest_open", "junk")


class FakeLab:
    """Models one fault: r-edge lost its route to the server subnet.

    state.route_ok  -> staff and guest can reach servers (as intent allows)
    state.guest_open -> guest is (wrongly) allowed into servers and staff
    """

    def __init__(self, route_ok: bool = False):
        self.state = {"route_ok": route_ok, "guest_open": False, "junk": False}
        self.commands: List[str] = []

    def reset(self):
        self.state = {"route_ok": True, "guest_open": False, "junk": False}

    def resolve_placeholders(self, node, cmd):
        return cmd

    # interfaces / exec
    def ifaces(self, node):
        return ["eth0", "eth1", "eth2"]

    def exec(self, node, argv, stdin=None, timeout=None):
        return ExecResult(0, f"fake output for {node}: {' '.join(argv)}", "")

    def run_command(self, node, cmd):
        self.commands.append(cmd)
        if cmd == GOOD_ROUTE:
            self.state["route_ok"] = True
        elif cmd == OPEN_GUEST:
            self.state["guest_open"] = True
        elif cmd == "ip route del 10.10.3.0/24":
            self.state["route_ok"] = False
        elif cmd == ADD_JUNK:
            self.state["junk"] = True
        elif cmd == DEL_JUNK:
            self.state["junk"] = False
        else:
            return ExecResult(2, "", "RTNETLINK answers: No such process")
        return ExecResult(0, "", "")

    # state
    def snapshot(self, node):
        snap = copy.deepcopy(self.state)
        junk = self.state["junk"] and node == "r-edge"  # the leftover lives on one device
        snap["iptables"] = "-A FORWARD -s 10.10.9.9/32 -j DROP" if junk else ""
        return snap

    def restore(self, node, snap):
        self.state = {k: snap[k] for k in STATE_KEYS}
        return []

    @staticmethod
    def snapshots_equal(a, b):
        return a == b

    # flows
    def run_flow(self, flow):
        r, g = self.state["route_ok"], self.state["guest_open"]
        if flow.src == "pc-staff":
            return r
        if flow.id in ("guest_web_http", "guest_web_bulk"):
            return r
        if flow.dst in ("fileserver", "webserver"):
            return r and g
        if flow.dst == "pc-staff":
            return g
        return False


class FakeLLM:
    """Returns pre-scripted assistant turns. Each turn is a list of (tool_name, args) or a string."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = 0
        self.seen_messages = []

    def chat(self, messages, tools):
        self.seen_messages.append(copy.deepcopy(messages))
        turn = self.turns[self.calls] if self.calls < len(self.turns) else "I am done."
        self.calls += 1
        usage = {"prompt": 1000, "completion": 100, "cached": 400}
        if isinstance(turn, str):
            return {"role": "assistant", "content": turn}, usage
        calls = []
        for i, (name, args) in enumerate(turn):
            arg_text = args if isinstance(args, str) else json.dumps(args)
            calls.append({"id": f"call_{self.calls}_{i}", "type": "function",
                          "function": {"name": name, "arguments": arg_text}})
        return {"role": "assistant", "content": "", "tool_calls": calls}, usage


def plan_args(commands, device="r-edge", fault_class="route_missing"):
    return {
        "root_cause": {"device": device, "fault_class": fault_class, "summary": "route to servers missing"},
        "plan": {"device": device, "commands": commands, "rationale": "restore route",
                 "expected_effect": "staff reach servers", "rollback": ["ip route del 10.10.3.0/24"],
                 "blast_radius": "one route"},
    }
