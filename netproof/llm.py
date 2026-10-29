"""Model client for any OpenAI-compatible Chat Completions endpoint (Meta Model API first)."""
from __future__ import annotations

from typing import List, Tuple

from .config import Settings


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings):
        if not settings.api_key:
            raise LLMError(f"{settings.key_env} is not set (profile {settings.profile}). Put it in .env.")
        from openai import OpenAI

        self.settings = settings
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                             timeout=120, max_retries=3)

    def chat(self, messages: List[dict], tools: List[dict]) -> Tuple[dict, dict]:
        kwargs = dict(model=self.settings.model, messages=messages, tools=tools, tool_choice="auto")
        if self.settings.reasoning_effort:
            kwargs["extra_body"] = {"reasoning_effort": self.settings.reasoning_effort}
        resp = self.client.chat.completions.create(**kwargs)
        if not resp.choices:
            raise LLMError("model returned no choices")
        msg = resp.choices[0].message
        out: dict = {"role": "assistant", "content": msg.content or ""}
        calls = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
            for tc in (msg.tool_calls or [])
        ]
        if calls:
            out["tool_calls"] = calls
        usage = resp.usage
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
        return out, {
            "prompt": getattr(usage, "prompt_tokens", 0) or 0,
            "completion": getattr(usage, "completion_tokens", 0) or 0,
            "cached": cached,
        }


def cost_usd(usage: dict, s: Settings) -> float:
    fresh = max(usage["prompt"] - usage["cached"], 0)
    return (fresh * s.price_in + usage["cached"] * s.price_cached + usage["completion"] * s.price_out) / 1e6
