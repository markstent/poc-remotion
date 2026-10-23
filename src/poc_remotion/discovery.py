"""Discovery question generation for a project's brief."""

from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import DiscoveryAnswer, DiscoveryQuestions


class DraftError(Exception):
    """Raised when a drafting stage cannot produce usable output."""


_NO_SOURCES = "no sources registered; run ingest first"


def run_discovery(project: Project, client: LLMClient) -> list[str]:
    """Generate discovery questions from the project's sources.

    Asks the model for audience, objective, tone and duration-feel questions
    and merges them into brief.json as empty-answer DiscoveryAnswer entries.
    Questions already present (string equality) are left untouched with their
    answers; new questions are appended. Returns the full question list,
    existing entries first.
    """
    if not (project.dir / "sources.json").exists():
        raise DraftError(_NO_SOURCES)
    sources = project.load_sources()
    if not sources:
        raise DraftError(_NO_SOURCES)

    source_lines = []
    for source in sources:
        headings = ", ".join(source.headings) if source.headings else "none"
        source_lines.append(f"- {source.title}; headings: {headings}")
    sources_text = "\n".join(source_lines)

    system = (
        "You write discovery questions for a training video project. "
        "Given the source material, propose questions that clarify the "
        "audience, the objective, the tone and the duration feel of the video."
    )
    user = (
        f"Source material for the video:\n{sources_text}\n\n"
        "Propose 4 to 8 discovery questions covering audience, objective, "
        "tone and duration feel, so the video can be planned well. "
        'Answer with JSON of the form {"questions": ["...", "..."]}.'
    )

    result = client.chat_json(system, user, DiscoveryQuestions)
    if not result.questions:
        raise DraftError("discovery returned no questions")

    brief = project.load_brief()
    known = {qa.question for qa in brief.qa}
    for question in result.questions:
        if question not in known:
            brief.qa.append(DiscoveryAnswer(question=question, answer=""))
            known.add(question)
    project.save_brief(brief)
    return [qa.question for qa in brief.qa]
