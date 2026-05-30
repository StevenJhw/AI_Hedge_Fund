"""LLM calls — supports Groq (free) and DeepSeek (paid)."""

import json
import os
import time
import threading
from pydantic import BaseModel
from src.utils.progress import progress

# ── Runtime config ─────────────────────────────────────────────────────────────
# Overridden per-call from state["metadata"] when available.
_DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "Groq")      # "Groq" | "DeepSeek"
_DEFAULT_MODEL    = os.getenv("GROQ_MODEL",   "llama-3.3-70b-versatile")

# ── Groq rate-limiter (free tier: ~30 RPM) ─────────────────────────────────────
_groq_lock      = threading.Lock()
_groq_last_call = 0.0
_GROQ_INTERVAL  = float(os.getenv("GROQ_MIN_INTERVAL", "2.1"))

# ── Lazy clients ───────────────────────────────────────────────────────────────
_groq_client     = None
_deepseek_client = None


def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq_client


def _get_deepseek():
    global _deepseek_client
    if _deepseek_client is None:
        from openai import OpenAI
        _deepseek_client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
    return _deepseek_client


def _throttle_groq():
    global _groq_last_call
    with _groq_lock:
        now  = time.monotonic()
        wait = _GROQ_INTERVAL - (now - _groq_last_call)
        if wait > 0:
            time.sleep(wait)
        _groq_last_call = time.monotonic()


def _prompt_to_messages(prompt) -> list[dict]:
    if hasattr(prompt, "messages"):
        result = []
        for m in prompt.messages:
            role = getattr(m, "type", "user")
            role = "system" if role == "system" else "user"
            result.append({"role": role, "content": str(m.content)})
        return result
    return [{"role": "user", "content": str(prompt)}]


def _normalize(data: dict) -> dict:
    """Normalize signal casing and confidence scale in-place."""
    if "signal" in data and isinstance(data["signal"], str):
        s = data["signal"].lower().strip().rstrip(".")
        data["signal"] = s if s in ("bullish", "bearish", "neutral") else "neutral"
    if "confidence" in data:
        try:
            v = float(data["confidence"])
            if v <= 1.0:
                v *= 100
            data["confidence"] = max(0.0, min(100.0, v))
        except (TypeError, ValueError):
            data["confidence"] = 50.0
    return data


def call_llm(
    prompt,
    pydantic_model: type[BaseModel],
    agent_name: str | None = None,
    state=None,
    max_retries: int = 3,
    default_factory=None,
) -> BaseModel:
    # Resolve provider + model from state metadata (set by run.py) or env defaults
    metadata = (state or {}).get("metadata", {})
    provider = metadata.get("model_provider", _DEFAULT_PROVIDER)
    model    = metadata.get("model_name",     _DEFAULT_MODEL)

    messages = _prompt_to_messages(prompt)
    use_deepseek = provider.lower() == "deepseek"

    for attempt in range(max_retries):
        if not use_deepseek:
            _throttle_groq()

        try:
            if use_deepseek:
                resp = _get_deepseek().chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"},
                )
            else:
                resp = _get_groq().chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0,
                    response_format={"type": "json_object"},
                )

            raw  = resp.choices[0].message.content
            data = _normalize(json.loads(raw))
            return pydantic_model(**data)

        except Exception as e:
            err = str(e)
            # Rate limit handling
            is_rate_limit = "429" in err or "rate_limit" in err.lower() or "rate limit" in err.lower()
            if is_rate_limit:
                wait = 5 * (attempt + 1)
                if agent_name:
                    progress.update_status(agent_name, None, f"Rate-limited — waiting {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                if agent_name:
                    progress.update_status(agent_name, None, f"Error - retry {attempt + 1}/{max_retries}")
            if attempt == max_retries - 1:
                if not is_rate_limit:
                    print(f"[LLM] Error after {max_retries} attempts ({provider}): {e}")
                return default_factory() if default_factory else _default_response(pydantic_model)

    return _default_response(pydantic_model)


def _default_response(model_class: type[BaseModel]) -> BaseModel:
    defaults = {}
    for name, field in model_class.model_fields.items():
        ann = field.annotation
        if ann == str:
            defaults[name] = "Error in analysis"
        elif ann in (float, int):
            defaults[name] = 0
        elif hasattr(ann, "__origin__") and ann.__origin__ == dict:
            defaults[name] = {}
        elif hasattr(ann, "__args__"):
            defaults[name] = ann.__args__[0]
        else:
            defaults[name] = None
    return model_class(**defaults)
