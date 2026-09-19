import json

from pydantic import BaseModel, ValidationError


class StructuredOutputError(Exception):
    """Raised by invoke_structured_with_repair when the model's tool-call output still
    doesn't validate against `schema` after a repair attempt and one retry. Carries the
    last raw (unparsed) args so the caller can log/flag them for review instead of just
    losing the failure context to a generic ValidationError."""

    def __init__(self, schema_name: str, raw_args, attempts: int):
        self.schema_name = schema_name
        self.raw_args = raw_args
        self.attempts = attempts
        super().__init__(f"Could not parse a valid {schema_name} after {attempts} attempt(s): {raw_args!r}")


def _json_decode_str_fields(d: dict) -> dict:
    """Some malformed responses double-encode a list/object field as a JSON string
    instead of returning it directly - decode any field that parses to a list/dict.
    A no-op for fields that are already the right shape or aren't valid JSON."""
    fixed = dict(d)
    for key, value in d.items():
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, (list, dict)):
                fixed[key] = parsed
    return fixed


def _repair_candidates(raw_args, required_fields: set[str]):
    """Yields candidate dicts to try validating against the schema, in order - covers
    every malformed shape actually observed from Claude's tool-call output so far:
    the real fields nested one level under a single placeholder key ('parameter',
    'parameter name', ...), a field's value re-serialized as a JSON string of the
    WHOLE payload instead of just that field, or a plain single-field JSON-string
    wrapper. Never raises - an un-decodable candidate is simply skipped."""
    if not isinstance(raw_args, dict):
        return

    yield raw_args
    yield _json_decode_str_fields(raw_args)

    for value in raw_args.values():
        if not isinstance(value, str):
            continue
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict) and required_fields.issubset(parsed.keys()):
            yield parsed
            yield _json_decode_str_fields(parsed)

    if len(raw_args) == 1:
        inner = next(iter(raw_args.values()))
        if isinstance(inner, dict):
            yield inner
            yield _json_decode_str_fields(inner)
        elif isinstance(inner, str):
            try:
                parsed = json.loads(inner)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                yield parsed
                yield _json_decode_str_fields(parsed)


def invoke_structured_with_repair(llm, schema: type[BaseModel], prompt: str, max_attempts: int = 2) -> BaseModel:
    """Same contract as llm.with_structured_output(schema).invoke(prompt), except a
    malformed tool call is repaired and re-validated (see _repair_candidates) instead
    of raising Pydantic's ValidationError straight away, and the whole call is retried
    with a fresh LLM invocation (a malformed response can't be fixed by re-parsing the
    same text differently) before giving up. Raises StructuredOutputError - never a
    bare ValidationError - if every attempt still fails, carrying the last raw args so
    the caller can persist/flag them instead of the failure being silently swallowed.
    """
    required_fields = set(schema.model_fields.keys())
    structured_llm = llm.with_structured_output(schema, include_raw=True)

    last_raw_args = None
    for _ in range(max_attempts):
        result = structured_llm.invoke(prompt)
        if result["parsing_error"] is None:
            return result["parsed"]

        tool_calls = getattr(result["raw"], "tool_calls", None) or []
        raw_args = tool_calls[0]["args"] if tool_calls else None
        last_raw_args = raw_args

        for candidate in _repair_candidates(raw_args, required_fields):
            try:
                return schema(**candidate)
            except (ValidationError, TypeError):
                continue

    raise StructuredOutputError(schema.__name__, last_raw_args, max_attempts)
