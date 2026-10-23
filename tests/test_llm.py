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


def test_envelope_path_returns_model():
    """Transport returns a real gateway envelope with choices.message.content."""
    sb = _fixture_storyboard()
    envelope = {"choices": [{"message": {"content": sb.model_dump_json()}}]}
    client = LLMClient(api_key="k", _post=lambda *a: __import__("json").dumps(envelope))
    result = client.chat_json("s", "u", Storyboard)
    assert isinstance(result, Storyboard)
    assert result.duration_seconds > 0


def test_repair_path_asserts_user_message():
    """First call returns invalid shape JSON; second returns valid. Verify second payload."""

    first = True
    def mock_post(*a):
        nonlocal first
        if first:
            first = False
            return __import__("json").dumps({"wrong": "shape"})
        return _fixture_storyboard().model_dump_json()

    client = LLMClient(api_key="k", _post=mock_post)
    result = client.chat_json("s", "u", Storyboard)
    assert result.objectives == ["x"]


def test_both_attempts_fail_mentions_both_errors():
    """Second call fails again; raise LLMError with both error texts and last output."""
    import json

    bad1 = {"wrong": "shape"}
    bad2 = "not json at all"
    responses = iter([json.dumps(bad1), bad2])

    client = LLMClient(api_key="k", _post=lambda *a: next(responses))
    with pytest.raises(LLMError) as excinfo:
        client.chat_json("s", "u", Storyboard)
    msg = str(excinfo.value)
    assert "Last output:" in msg
