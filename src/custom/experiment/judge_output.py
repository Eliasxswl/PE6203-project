"""Judge serialization contract; no rubric changes, repairs, or extra requests."""
import json

from jsonschema import Draft202012Validator

from .results import SCORES
from .selection import digest

REASONS = ("task_fulfillment_reasoning", "grounding_reasoning", "planning_efficiency_reasoning")
SCHEMA = {
    "type": "object",
    "properties": {
        **{name: {"type": "integer", "enum": list(range(1, 11))} for name in SCORES},
        **{name: {"type": "string"} for name in REASONS},
    },
    "required": [*SCORES, *REASONS],
    "additionalProperties": False,
}
VALIDATOR = Draft202012Validator(SCHEMA)


def contract(config):
    mode = config.get("judge_output_mode", "text")
    return {"mode": mode, "schema_sha256": digest(SCHEMA) if mode == "json_object" else None,
            "validation": "local_json_schema" if mode == "json_object" else "legacy_score_fields",
            "server_strict_schema": False}


def request_options(config, prompt):
    options = {"model": config.get("judge_model") or config["agent_model"],
               "temperature": config["judge_temperature"], "max_tokens": config["judge_max_tokens"]}
    if config.get("judge_thinking"):
        options["extra_body"] = {"thinking": {"type": config["judge_thinking"]}}
    if config.get("judge_output_mode", "text") == "json_object":
        options["response_format"] = {"type": "json_object"}
        prompt += ("\n\nSerialization contract (format only; apply the rubric above unchanged):\n"
                   "Return one JSON object matching this JSON Schema, without Markdown or extra text. "
                   "Scores must be integers 1 through 10.\n" + json.dumps(SCHEMA, ensure_ascii=False))
    options["messages"] = [{"role": "user", "content": prompt}]
    return options


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate judge JSON key: {key}")
        result[key] = value
    return result


def parse(raw, config=None):
    mode = (config or {}).get("judge_output_mode", "text")
    if mode == "json_object":
        try:
            result = json.loads(raw, object_pairs_hook=_unique_object)
        except (ValueError, TypeError) as exc:
            raise ValueError("Judge returned invalid JSON") from exc
        error = next(VALIDATOR.iter_errors(result), None)
        if error is not None:
            path = "/".join(str(p) for p in error.absolute_path) or "<root>"
            raise ValueError(f"Judge JSON Schema validation failed at {path}: {error.message}")
    else:
        from custom.analysis.answer.evaluation import extract_json_from_markdown
        result = extract_json_from_markdown(raw)
    # Keep the original integer-only score policy (also rejects JSON 8.0).
    if not isinstance(result, dict) or any(type(result.get(s)) is not int or not 1 <= result[s] <= 10 for s in SCORES):
        raise ValueError("Invalid or missing judge scores")
    return result


def validate_completion(response, config):
    if config.get("judge_output_mode", "text") != "json_object":
        return
    choice = response.choices[0]
    if getattr(choice.message, "refusal", None):
        raise ValueError("Judge refused the scoring request")
    if getattr(choice, "finish_reason", None) != "stop":
        raise ValueError("Judge response did not finish normally")
