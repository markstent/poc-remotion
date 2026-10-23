"""Claim register traced to source headings behind the script gate."""

from pydantic import BaseModel

from poc_remotion.discovery import DraftError
from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Claim, ScriptLine, SourceRef


class ExtractedClaim(BaseModel):
    """One factual claim as returned by the model for a script line."""

    text: str
    source_heading: str


class ClaimReply(BaseModel):
    """Reply shape for one script line's claim extraction."""

    claims: list[ExtractedClaim]


_SYSTEM_PROMPT = (
    "You perform claim extraction for one line of a training video "
    "narration script. Split the line into its discrete factual claims. "
    "For each claim, give the claim text and the source document heading "
    "that best supports it.\n\n"
    "Answer with JSON of the form "
    '{"claims": [{"text": "...", "source_heading": "..."}]}. '
    "Return an empty list when the line makes no factual claims."
)


def _user_prompt(line: ScriptLine) -> str:
    return (
        f"Script line (scene {line.scene_id}):\n{line.text}\n\n"
        "Extract the factual claims for this line."
    )


def _match_sources(
    sources: list[SourceRef], source_heading: str
) -> tuple[str | None, list[str]]:
    """Find sources whose headings contain the given heading.

    Matching is case-insensitive string equality after stripping. Returns
    the first matched heading as stored (None when nothing matches) and
    the ids of every matched source.
    """
    wanted = source_heading.strip().lower()
    matched_heading: str | None = None
    source_ids: list[str] = []
    for source in sources:
        for heading in source.headings:
            if heading.strip().lower() == wanted:
                if matched_heading is None:
                    matched_heading = heading
                source_ids.append(source.id)
                break
    return matched_heading, source_ids


def run_claims(project: Project, client: LLMClient) -> list[Claim]:
    """Build the claim register from the approved script.

    Prerequisites run before any LLM call: the script gate must be
    approved. Each script line gets exactly one chat_json call whose reply
    holds that line's factual claims. Claim ids are claim-<line no>-<n>
    with a 1-based line index and a per-line claim counter. A claim is
    supported when its source_heading matches a registered source heading
    (case-insensitive, after stripping); locator then prefers the stored
    heading casing. Unmatched claims stay unresolved with the returned
    heading as locator. The full register replaces any previous one.
    """
    if not project.is_approved("script"):
        raise DraftError("approve the script gate first")

    script = project.load_script()
    sources = project.load_sources()

    claims: list[Claim] = []
    for line_no, line in enumerate(script.lines, start=1):
        reply = client.chat_json(_SYSTEM_PROMPT, _user_prompt(line), ClaimReply)
        for n, extracted in enumerate(reply.claims, start=1):
            matched_heading, source_ids = _match_sources(sources, extracted.source_heading)
            if source_ids:
                claims.append(
                    Claim(
                        id=f"claim-{line_no}-{n}",
                        text=extracted.text,
                        source_ids=source_ids,
                        locator=matched_heading,
                        status="supported",
                    )
                )
            else:
                claims.append(
                    Claim(
                        id=f"claim-{line_no}-{n}",
                        text=extracted.text,
                        source_ids=[],
                        locator=extracted.source_heading,
                        status="unresolved",
                    )
                )

    project.save_claims(claims)
    return claims
