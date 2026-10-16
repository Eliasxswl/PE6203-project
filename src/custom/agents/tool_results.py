"""Loss-aware text transport for MCP results; raw results stay in the trace."""
import hashlib
import json

MAX_VISIBLE_CHARS = 32000


def raw_result(result):
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json", exclude_none=True)
    return result if isinstance(result, dict) else {"isError": False, "content": [{"type": "text", "text": str(result)}]}


def visible_result(result, max_chars=MAX_VISIBLE_CHARS):
    if max_chars < 512:
        raise ValueError("Tool result visibility must allow at least 512 characters")
    payload = raw_result(result)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(text) <= max_chars:
        return text
    # A valid JSON envelope survives truncation, including the MCP error flag.
    envelope = {"isError": bool(payload.get("isError", False)), "truncated": True,
                "original_characters": len(text),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "preview": ""}
    remaining = max_chars - len(json.dumps(envelope, ensure_ascii=False))
    envelope["preview"] = text[:remaining]
    encoded = json.dumps(envelope, ensure_ascii=False)
    while len(encoded) > max_chars:
        envelope["preview"] = envelope["preview"][:-(len(encoded) - max_chars)]
        encoded = json.dumps(envelope, ensure_ascii=False)
    return encoded
