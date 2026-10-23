import json
import os
import re
from collections.abc import Callable

from pydantic import BaseModel


class LLMError(Exception):
    """Raised when the LLM client encounters a failure."""


def _default_post(url: str, key: str, payload: dict) -> str:
    import urllib.request

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


class LLMClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        _post: Callable[[str, str, dict], str] | None = None,
    ) -> None:
        self._base_url = base_url or os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
        self._api_key = api_key or os.getenv("LITELLM_API_KEY")
        self._model = model or os.getenv("LITELLM_MODEL", "local-qwen")
        self._post = _post or _default_post

        if not self._api_key:
            raise LLMError("LITELLM_API_KEY environment variable is missing or empty. Set api_key or LITELLM_API_KEY.")

    def chat_json(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True}},
        }

        url = f"{self._base_url}/chat/completions"
        repair_count = 0

        while True:
            raw = self._post(url, self._api_key, payload)
            try:
                outer = json.loads(raw)
                choices = outer.get("choices", [])
                if isinstance(choices, list) and len(choices) > 0 and "message" in choices[0]:
                    content = choices[0]["message"].get("content", "")
                else:
                    # Fall back to treating raw response as direct JSON
                    content = None
            except (json.JSONDecodeError, KeyError, IndexError):
                content = None

            if content is None:
                cleaned = _strip_code_fences(raw.strip())
            else:
                cleaned = _strip_code_fences(content.strip())

            try:
                parsed = json.loads(cleaned)
                return schema.model_validate(parsed)
            except (json.JSONDecodeError, TypeError) as err:
                repair_count += 1
                if repair_count > 1:
                    error_msgs = []
                    if repair_count == 2:
                        error_msgs.append(f"First attempt failed: {err}")
                    error_msgs.append(f"{error_msgs[-1] or ''} Repair did not resolve the issue.")
                    raise LLMError(". ".join(error_msgs)) from err

                # Repair prompt: include original output and error for second attempt to fix
                repair_payload = f"\n\nModel output was: {cleaned}\n\nPlease return valid JSON matching the schema."
                payload["messages"] = [
                    {"role": "system", "content": system + repair_payload},
                    *payload["messages"][2:],
                ]


def _strip_code_fences(text: str) -> str:
    """Strip Markdown code fences from text."""
    pattern = r"^```(?:json)?\n|```$"
    return re.sub(pattern, "", text, flags=re.MULTILINE)
