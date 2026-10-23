"""Plan B end-to-end flow: every stage through cli.main with a scripted transport."""

import json

import pytest

from poc_remotion import cli
from poc_remotion.cli import main
from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Brief, Claim, ScriptDoc, Storyboard

SOURCE_MD = "# Platform Guide\n\nintro\n\n## Deployment\n\ntext\n"

QUESTIONS = [
    "Who is the audience?",
    "What should viewers do differently afterwards?",
    "What tone suits the subject matter?",
    "How long should the video feel?",
    "Which source sections matter most?",
]

ANSWERS = [
    "Platform engineers",
    "Ship a change through the pipeline",
    "Practical",
    "Around 5 minutes",
    "The Deployment section",
]

DISCOVERY_REPLY = json.dumps({"questions": QUESTIONS})

CAPTURE_REPLY = json.dumps(
    {
        "audience": "Platform engineers",
        "objectives": ["Explain the deployment pipeline"],
        "tone": "Practical",
        "duration_minutes": 5,
        "notes": "",
    }
)

OBJECTIVES = ["Explain the deployment pipeline"]


def _scene(
    id: str, kind: str, seconds: float, summary: str, on_screen: list[str]
) -> dict:
    return {
        "id": id,
        "kind": kind,
        "purpose": f"Cover {summary.lower()}",
        "seconds": seconds,
        "summary": summary,
        "on_screen": on_screen,
    }


def _storyboard_reply(duration_seconds: float, scenes: list[dict]) -> str:
    return json.dumps(
        {
            "objectives": OBJECTIVES,
            "duration_seconds": duration_seconds,
            "rationale": "Scenes follow the source flow.",
            "scenes": scenes,
        }
    )


def _valid_scenes() -> list[dict]:
    return [
        _scene("opening", "title", 60, "Meet the colleague", ["headline", "subheadline"]),
        _scene("rule", "quote", 60, "Ask clarifying questions", ["quote line"]),
        _scene(
            "gcse",
            "framework",
            60,
            "Goal, Context, Source, Expectations",
            ["panel label G", "panel label C", "panel label S", "panel label E"],
        ),
        _scene("summary", "cheatSheet", 60, "Recap the rules", ["panel 1", "panel 2", "panel 3"]),
        _scene("closing", "outro", 60, "Try it today", ["call to action"]),
    ]


STORYBOARD_REPLY = _storyboard_reply(300, _valid_scenes())

SCENE_IDS = ["opening", "rule", "gcse", "summary", "closing"]

# 21 words; repeated five times per line gives 105 words per line, so five
# scenes land at 525 words, inside the 487.5 to 1012.5 window for 300 seconds.
_LINE_TEXT = (
    "Here is a line of narration with plenty of words to keep the pacing "
    "natural and the count inside the window. " * 5
)

SCRIPT_REPLY = json.dumps(
    {"lines": [{"scene_id": scene_id, "text": _LINE_TEXT} for scene_id in SCENE_IDS]}
)

CLAIMS_FIRST_REPLY = json.dumps(
    {
        "claims": [
            {
                "text": "The pipeline deploys with one command.",
                "source_heading": "Deployment",
            },
            {"text": "The canteen opens at seven.", "source_heading": "No Such Section"},
        ]
    }
)
CLAIMS_EMPTY_REPLY = json.dumps({"claims": []})


def _patch_client(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, int], list[dict]]:
    """Route cli's LLMClient by prompt markers (ruling R-B4).

    Returns the call count per route and every captured payload. Route
    precedence: claim extraction, then the capture marker, then narration,
    then storyboard, otherwise discovery.
    """
    routes = {"claims": 0, "capture": 0, "script": 0, "storyboard": 0, "discovery": 0}
    claims_replies = [CLAIMS_FIRST_REPLY] + [CLAIMS_EMPTY_REPLY] * (len(SCENE_IDS) - 1)
    calls: list[dict] = []

    def fake_post(url: str, key: str, payload: dict) -> str:
        calls.append(payload)
        system = payload["messages"][0]["content"]
        user = payload["messages"][1]["content"]
        if "claim extraction" in system:
            routes["claims"] += 1
            return claims_replies.pop(0)
        if "Answers to incorporate:" in user:
            routes["capture"] += 1
            return CAPTURE_REPLY
        if "narration" in system:
            routes["script"] += 1
            return SCRIPT_REPLY
        if "storyboard" in system:
            routes["storyboard"] += 1
            return STORYBOARD_REPLY
        routes["discovery"] += 1
        return DISCOVERY_REPLY

    monkeypatch.setattr(
        cli,
        "LLMClient",
        lambda: LLMClient(base_url="http://test", api_key="k", model="test-model", _post=fake_post),
    )
    return routes, calls


def test_full_pipeline_b_flow(tmp_path, capsys, monkeypatch):
    """A project goes from empty to fully gated through cli.main alone."""
    routes, calls = _patch_client(monkeypatch)
    project_root = tmp_path / "projects"
    project_dir = project_root / "demo"

    src = tmp_path / "guide.md"
    src.write_text(SOURCE_MD)
    qa_file = tmp_path / "qa.json"
    qa_file.write_text(
        json.dumps(
            [{"question": question, "answer": answer} for question, answer in zip(QUESTIONS, ANSWERS)]
        )
    )

    assert main(["init", "--id", "demo", "--projects-root", str(project_root)]) == 0
    assert (
        main(["ingest", "--id", "demo", "--source", str(src), "--projects-root", str(project_root)])
        == 0
    )
    assert main(["discover", "--id", "demo", "--projects-root", str(project_root)]) == 0
    assert (
        main(
            [
                "brief",
                "--id",
                "demo",
                "--qa-file",
                str(qa_file),
                "--projects-root",
                str(project_root),
            ]
        )
        == 0
    )
    assert main(["draft-storyboard", "--id", "demo", "--projects-root", str(project_root)]) == 0
    assert (
        main(["approve", "--id", "demo", "--stage", "storyboard", "--projects-root", str(project_root)])
        == 0
    )
    assert (
        main(["approve", "--id", "demo", "--stage", "duration", "--projects-root", str(project_root)])
        == 0
    )
    assert main(["draft-script", "--id", "demo", "--projects-root", str(project_root)]) == 0
    assert (
        main(["approve", "--id", "demo", "--stage", "script", "--projects-root", str(project_root)])
        == 0
    )
    assert main(["claims", "--id", "demo", "--projects-root", str(project_root)]) == 0

    # Each stage received its own reply kind: one call per drafting stage
    # and one per script line for claims (9 calls in total).
    assert routes == {"claims": 5, "capture": 1, "script": 1, "storyboard": 1, "discovery": 1}
    assert len(calls) == 9

    brief = Brief.model_validate(json.loads((project_dir / "brief.json").read_text()))
    assert brief.audience == "Platform engineers"
    assert brief.tone == "Practical"
    assert brief.duration_minutes == 5

    storyboard = Storyboard.model_validate(
        json.loads((project_dir / "storyboard.json").read_text())
    )
    assert storyboard.duration_seconds == 300
    assert [scene.id for scene in storyboard.scenes] == SCENE_IDS

    script = ScriptDoc.model_validate(json.loads((project_dir / "script.json").read_text()))
    assert [line.scene_id for line in script.lines] == SCENE_IDS

    claims = [
        Claim.model_validate(item)
        for item in json.loads((project_dir / "claims.json").read_text())
    ]
    assert [claim.id for claim in claims] == ["claim-1-1", "claim-1-2"]
    assert claims[0].status == "supported"
    assert claims[0].source_ids
    assert claims[1].status == "unresolved"

    assert Project.load(project_dir).all_approved()

    out = capsys.readouterr().out
    assert "claim-1-1  supported" in out
    assert "claim-1-2  unresolved" in out
    assert "1 unresolved" in out
