import os, json
from groq import Groq

MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
_client = None

def run_agent(role, payload, as_json=False):
    """One 'agent' = one LLM call with its own role prompt. Returns None on any failure (callers fall back)."""
    global _client
    if not os.getenv("GROQ_API_KEY"):
        return None
    try:
        _client = _client or Groq()
        kw = {"response_format": {"type": "json_object"}} if as_json else {}
        r = _client.chat.completions.create(
            model=MODEL, temperature=0.2,
            messages=[{"role": "system", "content": role}, {"role": "user", "content": payload}], **kw)
        t = r.choices[0].message.content
        return json.loads(t) if as_json else t
    except Exception as e:
        print("agent error:", e)
        return None
