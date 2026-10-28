"""Step 3 smoke test: can this key call the model with tool calling?

Usage:  python scripts/smoke_llm.py
"""
import json
import sys

sys.path.insert(0, ".")
from netproof.config import load_settings  # noqa: E402

from openai import OpenAI  # noqa: E402


def main() -> int:
    s = load_settings()
    if not s.api_key:
        print("MODEL_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 2
    client = OpenAI(api_key=s.api_key, base_url=s.base_url, timeout=60)
    print(f"base_url={s.base_url} model={s.model}")
    try:
        ids = sorted(m.id for m in client.models.list().data)
        print("models visible to this key:", ", ".join(ids) or "(none listed)")
    except Exception as e:
        print(f"model listing not available: {type(e).__name__}: {e}")

    tools = [{"type": "function", "function": {
        "name": "ping", "description": "Ping a host from a device.",
        "parameters": {"type": "object", "properties": {
            "src": {"type": "string"}, "dst": {"type": "string"}}, "required": ["src", "dst"]}}}]
    resp = client.chat.completions.create(
        model=s.model, tools=tools, tool_choice="auto",
        messages=[{"role": "user", "content": "Use the ping tool to ping 10.10.3.10 from pc-staff."}])
    msg = resp.choices[0].message
    if msg.tool_calls:
        tc = msg.tool_calls[0]
        print(f"TOOL CALL: yes -> {tc.function.name} {tc.function.arguments}")
    else:
        print(f"TOOL CALL: NO. Model replied with text: {msg.content!r}")
    print("usage:", resp.usage)

    try:
        r2 = client.chat.completions.create(
            model=s.model, response_format={"type": "json_object"},
            messages=[{"role": "user", "content": 'Reply with JSON only: {"status": "ok"}'}])
        print("JSON MODE:", json.loads(r2.choices[0].message.content))
    except Exception as e:
        print(f"JSON MODE: not available ({type(e).__name__}: {e})")

    if s.reasoning_effort:
        try:
            client.chat.completions.create(
                model=s.model, extra_body={"reasoning_effort": s.reasoning_effort},
                messages=[{"role": "user", "content": "Say ok."}])
            print(f"REASONING EFFORT '{s.reasoning_effort}': accepted")
        except Exception as e:
            print(f"REASONING EFFORT: rejected ({type(e).__name__}: {e}). Leave NP_REASONING_EFFORT empty.")
    return 0 if msg.tool_calls else 1


if __name__ == "__main__":
    sys.exit(main())
