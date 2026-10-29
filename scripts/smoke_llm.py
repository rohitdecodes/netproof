"""Smoke test for a model profile: can this endpoint and key do tool calling?

Usage:  python scripts/smoke_llm.py [--profile spark-1.3|spark-1.2|spark-open|glimmer]
"""
import argparse
import json
import sys
import time

sys.path.insert(0, ".")
from netproof.config import load_settings  # noqa: E402

from openai import OpenAI  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=None)
    s = load_settings(ap.parse_args().profile)
    if not s.api_key:
        print(f"{s.key_env} is not set in .env (profile {s.profile}).")
        return 2
    client = OpenAI(api_key=s.api_key, base_url=s.base_url, timeout=180)
    print(f"profile={s.profile} base_url={s.base_url} model={s.model} reasoning_effort={s.reasoning_effort}")
    try:
        ids = sorted(m.id for m in client.models.list().data)
        print("models visible to this key:", ", ".join(ids) or "(none listed)")
    except Exception as e:
        print(f"model listing not available: {type(e).__name__}: {e}")

    tools = [{"type": "function", "function": {
        "name": "ping", "description": "Ping a host from a device.",
        "parameters": {"type": "object", "properties": {
            "src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]}}}]
    kwargs = dict(model=s.model, tools=tools, tool_choice="auto",
                  messages=[{"role": "user", "content": "Use the ping tool to ping 10.10.3.10 from pc-staff."}])
    if s.reasoning_effort:
        kwargs["extra_body"] = {"reasoning_effort": s.reasoning_effort}
    t = time.monotonic()
    resp = client.chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    if msg.tool_calls:
        tc = msg.tool_calls[0]
        print(f"TOOL CALL: yes -> {tc.function.name} {tc.function.arguments}  ({time.monotonic() - t:.1f}s)")
    else:
        print(f"TOOL CALL: NO. Model replied with text: {msg.content!r}")
    print("usage:", resp.usage)
    try:
        args = json.loads(msg.tool_calls[0].function.arguments) if msg.tool_calls else {}
        print("ARGUMENTS PARSE AS JSON:", "yes" if isinstance(args, dict) else "NO")
    except json.JSONDecodeError:
        print("ARGUMENTS PARSE AS JSON: NO")
    return 0 if msg.tool_calls else 1


if __name__ == "__main__":
    sys.exit(main())
