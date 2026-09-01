"""Thin OpenRouter chat-completions client + a helper to pull JSON out of a reply."""
import json, urllib.request
from . import config

_URL = "https://openrouter.ai/api/v1/chat/completions"

def chat(model, messages, max_tokens=256, temperature=None, timeout=90):
    """Return the assistant message text for a chat-completions call."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        body["temperature"] = temperature
    r = urllib.request.Request(
        _URL, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + config.OPENROUTER_KEY,
                 "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read())["choices"][0]["message"].get("content") or ""

def extract_json(text):
    """Best-effort: parse the first {...} or [...] block out of a model reply."""
    a = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
    if a == -1:
        raise ValueError("no JSON in reply")
    b = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[a:b + 1])
