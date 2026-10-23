"""Discovery question generation for a project's brief."""

from poc_remotion.llm import LLMClient
from poc_remotion.project import Project
from poc_remotion.schemas import Brief, BriefCore, DiscoveryAnswer, DiscoveryQuestions


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
    # The schema's min_length usually rejects empty replies in chat_json
    # before this guard; it remains as defence in depth for stub clients.
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


_CAPTURE_MARKER = "Answers to incorporate:"


def capture_brief(project: Project, client: LLMClient, qa: list[DiscoveryAnswer]) -> Brief:
    """Derive a brief from answered discovery questions and save it.

    Every answer must be non-empty after stripping whitespace, otherwise
    DraftError is raised naming the unanswered question and brief.json is
    left untouched. One chat_json call derives the BriefCore fields from the
    question-answer pairs; they replace any existing audience, objectives,
    tone, duration and notes, and the qa set is replaced by the new answers.
    """
    for answer in qa:
        if not answer.answer.strip():
            raise DraftError(f"unanswered question: {answer.question}")

    qa_text = "\n\n".join(f"Q: {a.question}\nA: {a.answer}" for a in qa)
    system = (
        "You capture a training video brief. Given answered discovery "
        "questions, derive the audience, the objectives, the tone, the "
        "duration in minutes and any notes."
    )
    user = (
        f"{_CAPTURE_MARKER}\n{qa_text}\n\n"
        "Derive the brief from these answers. "
        "Answer with JSON of the form "
        '{"audience": "...", "objectives": ["..."], "tone": "...", '
        '"duration_minutes": 5, "notes": "..."}.'
    )

    core = client.chat_json(system, user, BriefCore)
    # Fresh build is equivalent to a merge because Brief has exactly these
    # five core fields plus qa; revisit if Brief ever gains more fields.
    brief = Brief(**core.model_dump(), qa=qa)
    project.save_brief(brief)
    return brief
