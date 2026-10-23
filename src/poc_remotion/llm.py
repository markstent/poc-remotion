import json
import os
import re
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError


def _strip_code_fences(text: str) -> str:
    """Strip Markdown code fences from text."""
    pattern = r"^```(?:json)?\n|```$"
    return re.sub(pattern, "", text, flags=re.MULTILINE)


class LLMError(Exception):
    """Raised when the LLM client encounters a failure."""


T = TypeVar("T", bound=BaseModel)


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

    def chat_json(self, system: str, user: str, schema: type[T]) -> T:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        url = f"{self._base_url}/chat/completions"
        repair_count = 0
        first_error: str | None = None
        last_cleaned: str = ""

        while True:
            raw = self._post(url, self._api_key, payload)
            cleaned = _strip_code_fences(raw.strip())
            last_cleaned = cleaned

            try:
                outer = json.loads(cleaned)
                choices = outer.get("choices", [])
                if isinstance(choices, list) and len(choices) > 0 and "message" in choices[0]:
                    content = choices[0]["message"].get("content", "")
                    last_cleaned = _strip_code_fences(content.strip())
            except (json.JSONDecodeError, KeyError, IndexError):
                pass

            try:
                parsed = json.loads(last_cleaned)
                return schema.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError, TypeError) as err:
                repair_count += 1
                if first_error is None:
                    first_error = str(err)
                if repair_count > 1:
                    raise LLMError(f"{first_error}. Repair failed: {err}. Last output: {last_cleaned}") from err

                # Honest repair prompt: system untouched, user message includes original + error + requested fix
                repair_text = f"\n\nPrevious output: {cleaned}\n\nValidation error: {err}\n\nPlease return valid JSON matching the schema."
                payload["messages"] = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user + repair_text},
                ]
