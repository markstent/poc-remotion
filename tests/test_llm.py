import pytest

from poc_remotion.llm import LLMClient, LLMError
from poc_remotion.schemas import Storyboard


def _fixture_storyboard():
    from poc_remotion.schemas import StoryboardScene

    return Storyboard(
        objectives=["x"],
        duration_seconds=120.0,
        rationale="test",
        scenes=[
            StoryboardScene(id="intro", kind="title", purpose="start", seconds=10.0, summary="start"),
        ],
    )


def test_valid_response_parses_to_model():
    sb = _fixture_storyboard()  # same valid Storyboard as Task 1's tests: objectives ["x"]
    client = LLMClient(api_key="k", _post=lambda url, key, payload: sb.model_dump_json())
    assert client.chat_json("s", "u", Storyboard) == sb


def test_code_fences_stripped():
    raw = "```json\n" + _fixture_storyboard().model_dump_json() + "\n```"
    client = LLMClient(api_key="k", _post=lambda *a: raw)
    assert client.chat_json("s", "u", Storyboard).duration_seconds > 0


def test_repair_retry_succeeds():
    responses = iter(["not json at all", _fixture_storyboard().model_dump_json()])
    client = LLMClient(api_key="k", _post=lambda *a: next(responses))
    assert client.chat_json("s", "u", Storyboard).objectives == ["x"]


def test_two_failures_raise_llm_error():
    client = LLMClient(api_key="k", _post=lambda *a: "nope")
    with pytest.raises(LLMError):
        client.chat_json("s", "u", Storyboard)


def test_missing_key_raises_llm_error(monkeypatch):
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    with pytest.raises(LLMError, match="LITELLM_API_KEY"):
        LLMClient(api_key=None).chat_json("s", "u", Storyboard)
