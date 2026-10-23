# Training Video Builder Plan B: Pipeline Brain, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the intelligence layer: source ingest into projects, conversational discovery captured to `brief.json`, model-drafted storyboard and script behind the existing approval gates, and a claim register tracing every fact to its source.

**Architecture:** Pure-Python pipeline stages on top of Plan A's store (`Project`), schemas and `LLMClient.chat_json`. Each stage is one module with a `run_*(project, ...) -> result` function plus a thin CLI subcommand; LLM outputs are always validated through pydantic, never trusted. Nothing here touches TTS, audio or TypeScript; that is Plan C.

**Tech Stack:** Python 3.13, uv, pydantic v2, pytest, ruff; LiteLLM gateway (`litellm/local-qwen` per design) behind `poc_remotion.llm.LLMClient`.

**Spec:** `docs/superpowers/specs/2026-10-22-training-video-builder-design.md` (pipeline section 8, video 1 outline section 7, success criteria section 10). This plan argues from that spec.

## Global Constraints

- All model calls go through `poc_remotion.llm.LLMClient`; runtime model is the env default `local-qwen` (design decision, owner: user). Never bypass LiteLLM.
- No paid APIs; no network calls in tests (every LLM test uses the `_post` injection seam).
- pydantic models are the schema source of truth; field names snake_case; `SceneKind` order fixed: `title, newsGrid, beforeAfter, framework, quote, analogy, cheatSheet, outro`.
- Approval gates stay exactly: storyboard + duration (gate 1), script (gate 2). Production (`render`) stays blocked without them.
- British English everywhere; no em dashes in any file; ruff clean; test output pristine.
- `src/fonts/`, `data/voice_samples/`, `.superpowers/`, project audio/output stay out of Git; no secrets in code or commits.
- Existing public APIs are contracts (do not rename): `Project.create/load`, `save_sources/save_storyboard/save_script`, `record_approval(stage)`, `is_approved`, `all_approved`, `manifest`, `LLMClient(base_url, api_key, model, _post).chat_json(system, user, schema) -> T`, `ingest_markdown(path) -> SourceRef`, `render_video(project, opts) -> Path`.

## Review Focus

1. A structurally valid LLM reply that is semantically wrong (duration outside target, scene seconds not summing, unknown scene kind): the draft stage must fail loudly and save nothing, not store a bad draft. Test in Task 6.
2. Commands run from outside the repository root: brand and fonts paths must resolve from the repo root, never the cwd. Test in Task 1.
3. Drafting with prerequisites missing (no brief before storyboard, no sources before discover, unapproved gates before script): exit code 2 with the missing prerequisite named. Tests in Tasks 5, 6, 7.
4. A malformed `--qa-file` (bad JSON, non-object entries, empty answers): the brief command must exit 2 with a message, never a traceback. Test in Task 4.
5. Re-running any stage must be safe (resumable discovery, re-draft overwrites cleanly, approvals unaffected by drafting). Test in Task 9.

---

### Task 1: Python hardening carry-forward

**Files:**
- Modify: `src/poc_remotion/project.py`, `src/poc_remotion/cli.py`, `src/poc_remotion/ingest.py`, `src/poc_remotion/llm.py`, `tests/test_brand.py`, `src/poc_remotion/render.py`
- Test: `tests/test_hardening.py`

**Interfaces:**
- Consumes: existing `Project`, `cli.main`, `ingest_markdown`, `LLMClient`, `validate_brand`.
- Produces: `Project.GATED_STAGES: ClassVar[list[str]]` (value `["storyboard", "duration", "script"]`); `cli.REPO_ROOT: Path`; `LLMError` raised for transport failures; `LITELLM_TIMEOUT` env (seconds, default `120`) honoured by `_default_post`.

- [ ] **Step 1: Write the failing tests** in `tests/test_hardening.py`

```python
def test_gated_stages_single_source(): ...        # project.GATED_STAGES == ["storyboard", "duration", "script"]; all_approved() and render gate read it (patch the list to see behaviour change or assert identity of source)
def test_help_exits_zero(capsys): ...             # main(["--help"]) returns 0, help text on stdout
def test_validate_catches_type_error(tmp_path, monkeypatch): ...  # storyboard.json containing a JSON array -> validate exits 2 with message, no traceback
def test_validate_works_from_other_cwd(tmp_path, monkeypatch): ...  # monkeypatch.chdir(tmp_path); main(["validate", ...]) against repo project -> exit 0 (brand resolved from REPO_ROOT)
def test_ingest_handles_bom(tmp_path): ...        # markdown file starting with UTF-8 BOM: title extracted, not "\ufeffTitle"
def test_transport_error_wrapped(): ...           # _post raises URLError -> chat_json raises LLMError, original message preserved
def test_timeout_from_env(monkeypatch): ...       # LITELLM_TIMEOUT=7 -> urlopen called with timeout=7
```

- [ ] **Step 2: Run `uv run pytest tests/test_hardening.py -v`**

Expected: FAIL (attributes/behaviour missing).

- [ ] **Step 3: Implement**

- `project.py`: add `GATED_STAGES` class variable; `is_approved`, `all_approved` iterate it.
- `render.py`: replace the local `_GATED_STAGES` with `Project.GATED_STAGES`.
- `cli.py`: `REPO_ROOT = Path(__file__).resolve().parents[2]`; brand load becomes `load_brand(REPO_ROOT / "brand/brand.json")`, fonts dir `REPO_ROOT / brand.fonts_dir`; `_parse_args` converts SystemExit to exit code 2 only when `exc.code` is a non-zero int (help passes through); `cmd_validate` handler tuple becomes `(ProjectError,)` then a combined `except (ValueError, TypeError, OSError)` returning 2.
- `ingest.py`: `bytes_data.decode("utf-8-sig")`.
- `llm.py`: `_default_post` wraps `urllib.error.URLError` and `HTTPError` in `LLMError(f"gateway unreachable: {reason}")` (key never in message); timeout read from `LITELLM_TIMEOUT` (int, default 120).
- `tests/test_brand.py`: add `@pytest.mark.skipif(not Path("src/fonts").is_dir(), reason="local font binaries not present")` to `test_validate_ok_on_real_files`.

- [ ] **Step 4: Run `uv run pytest tests/ -v` then `uv run ruff check src tests`**

Expected: all green, pristine.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion tests/test_hardening.py tests/test_brand.py
git commit -m "fix: hardening carry-forward from plan A review"
```

### Task 2: Brief schema and store methods

**Files:**
- Modify: `src/poc_remotion/schemas.py`, `src/poc_remotion/project.py`, `tests/test_project.py`
- Test: `tests/test_project.py` (extend)

**Interfaces:**
- Produces: `class DiscoveryAnswer(BaseModel)` fields `question: str`, `answer: str`; `class Brief(BaseModel)` fields `audience: str = ""`, `objectives: list[str] = []`, `tone: str = ""`, `duration_minutes: float | None = None`, `notes: str = ""`, `qa: list[DiscoveryAnswer] = []`; `Project.save_brief(brief: Brief) -> None` (writes `brief.json`), `Project.load_brief() -> Brief` (raises `ProjectError` naming the file if absent), `Project.brief_present() -> bool` (True iff `brief.json` exists with a non-empty `qa` or non-empty `audience`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_project.py`)

```python
def test_brief_roundtrip(tmp_path): ...          # save Brief(qa=[...]), load returns equal model
def test_load_brief_missing_raises(tmp_path): ...  # ProjectError naming brief.json
def test_brief_present(tmp_path): ...            # False on fresh project, True after save_brief(qa non-empty), False after save_brief(Brief()) empty
```

- [ ] **Step 2: Run `uv run pytest tests/test_project.py -v`**

Expected: new tests FAIL (`save_brief` missing), existing 12 PASS.

- [ ] **Step 3: Implement** the models in `schemas.py` (after `ApprovalState`) and the three methods in `project.py` (pattern of `save_script`/`load_script`).

- [ ] **Step 4: Run full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/schemas.py src/poc_remotion/project.py tests/test_project.py
git commit -m "feat: brief schema and store methods"
```

### Task 3: Typed claims store

**Files:**
- Modify: `src/poc_remotion/project.py`, `tests/test_project.py`
- Test: `tests/test_project.py` (extend)

**Interfaces:**
- Consumes: `Claim` (schemas: `id`, `text`, `source_ids: list[str]`, `locator: str | None`, `status: Literal["supported", "unresolved", "conflict"]`).
- Produces: `Project.save_claims(claims: list[Claim]) -> None` (writes `claims.json`, list JSON), `Project.load_claims() -> list[Claim]` (empty list when file absent, `ProjectError` naming the file on invalid content).

- [ ] **Step 1: Write the failing tests**

```python
def test_claims_roundtrip(tmp_path): ...          # save two Claims, load returns equal list
def test_load_claims_empty_when_absent(tmp_path): ...
def test_load_claims_invalid_raises(tmp_path): ... # claims.json = {"not": "a list"} -> ProjectError
```

- [ ] **Step 2: Run** `uv run pytest tests/test_project.py -v`. Expected: new tests FAIL.

- [ ] **Step 3: Implement** (parse with `Claim.model_validate` per item; wrap errors in `ProjectError`).

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/project.py tests/test_project.py
git commit -m "feat: typed claims store"
```

### Task 4: Ingest CLI command

**Files:**
- Modify: `src/poc_remotion/cli.py`, `tests/test_cli.py`
- Test: `tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: `ingest_markdown(path: Path) -> SourceRef`, `Project.save_sources(list[SourceRef]) / load_sources()`.
- Produces: `poc-remotion ingest --id ID --source PATH [--source PATH ...] --projects-root DIR` (source repeatable, required at least one). Replace-all semantics: sources.json holds exactly the files from this invocation. Prints one line per source: `<id>  <title>  (<n> headings)`. Exit 0; missing file or bad markdown exit 2 with message.

- [ ] **Step 1: Write the failing tests**

```python
def test_ingest_saves_sources(tmp_path): ...      # two temp .md files -> sources.json has 2 entries, fields id/title/path/kind, paths absolute, exit 0
def test_ingest_missing_file_exits_two(tmp_path): ...
def test_ingest_replace_all_semantics(tmp_path): ...  # second run with one file -> sources.json has exactly 1
```

- [ ] **Step 2: Run** `uv run pytest tests/test_cli.py -v`. Expected: new FAIL.

- [ ] **Step 3: Implement** `cmd_ingest` + parser (follow `cmd_validate` patterns; catch `OSError` and `ValueError` to exit 2).

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/cli.py tests/test_cli.py
git commit -m "feat: ingest subcommand registering sources"
```

### Task 5: Discovery question generation (`discover`)

**Files:**
- Create: `src/poc_remotion/discovery.py`
- Modify: `src/poc_remotion/cli.py`, `tests/test_discovery.py` (create)
- Test: `tests/test_discovery.py`

**Interfaces:**
- Consumes: `LLMClient.chat_json`, `Project.load_sources()`, `Brief`, `Project.save_brief/load_brief/brief_present`.
- Produces: `class DiscoveryQuestions(BaseModel)` field `questions: list[str]` (min 4, max 8); `run_discovery(project: Project, client: LLMClient) -> list[str]`: builds a prompt naming the source titles and headings, asks for audience/objective/tone/duration-feel questions, merges into `brief.json` as `DiscoveryAnswer(question, answer="")` entries; questions already present in `brief.json` (string equality) are not duplicated; returns the full question list. CLI: `poc-remotion discover --id ID [--projects-root DIR]` prints numbered questions; exit 2 with "no sources registered; run ingest first" when `sources.json` absent.

- [ ] **Step 1: Write the failing tests**

```python
def test_discovery_questions_saved(tmp_path): ...      # mocked _post returns {"questions": ["Who is the audience?", ...x5]}; brief.json gains 5 qa entries with empty answers; exit 0; output numbered
def test_discovery_is_resumable(tmp_path): ...         # pre-seed brief with one answered qa; re-run: existing question kept with its answer, only new questions appended
def test_discovery_requires_sources(tmp_path): ...     # no sources -> exit 2, message names ingest
def test_discovery_rejects_empty_questions(tmp_path): ...  # LLM returns {"questions": []} -> DraftError -> exit 2, nothing saved
```

- [ ] **Step 2: Run** `uv run pytest tests/test_discovery.py -v`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement** `DraftError(Exception)` in `discovery.py` (shared by drafting stages; importable by later tasks); CLI wiring catching `DraftError` like `ProjectError` (exit 2).

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/discovery.py src/poc_remotion/cli.py tests/test_discovery.py
git commit -m "feat: discovery question generation"
```

### Task 6: Brief capture from answers (`brief`)

**Files:**
- Modify: `src/poc_remotion/discovery.py`, `src/poc_remotion/cli.py`, `tests/test_discovery.py`
- Test: `tests/test_discovery.py` (extend)

**Interfaces:**
- Consumes: `Brief`, `DiscoveryAnswer`, `LLMClient.chat_json`.
- Produces: `class BriefCore(BaseModel)` fields matching `Brief`'s first five (`audience`, `objectives`, `tone`, `duration_minutes`, `notes`); `capture_brief(project: Project, client: LLMClient, qa: list[DiscoveryAnswer]) -> Brief`: requires every answer non-empty (else `DraftError` naming the unanswered question), one `chat_json` call deriving `BriefCore` from the question-answer pairs, merges with existing brief (qa replaced by the new set), saves. CLI: `poc-remotion brief --id ID --qa-file PATH [--projects-root DIR]`: PATH is JSON `[{...}, ...]` with keys `question`/`answer`; malformed JSON, non-object entries, or empty answers exit 2 with a message; success prints the derived audience, tone, duration target.

- [ ] **Step 1: Write the failing tests**

```python
def test_capture_brief_saves_core_and_qa(tmp_path): ...   # mocked two-call sequence (discovery prompt vs capture prompt distinguished by payload): brief.json has audience "New hires", duration_minutes 5, qa answers stored
def test_brief_rejects_empty_answer(tmp_path): ...        # answer "" -> DraftError naming the question; brief.json untouched
def test_cli_brief_malformed_json_exits_two(tmp_path): ...# --qa-file with invalid JSON -> exit 2, message, no traceback
def test_cli_brief_happy_path(tmp_path): ...              # file input -> exit 0, printed summary contains audience and "5"
```

- [ ] **Step 2: Run** `uv run pytest tests/test_discovery.py -v`. Expected: new FAIL.

- [ ] **Step 3: Implement.** The mocked-transport discriminator: the capture call's user prompt must contain the literal marker `"Answers to incorporate:"` so tests can route payloads.

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/discovery.py src/poc_remotion/cli.py tests/test_discovery.py
git commit -m "feat: brief capture from discovery answers"
```

### Task 7: Storyboard drafting (`draft-storyboard`)

**Files:**
- Create: `src/poc_remotion/storyboard.py`
- Modify: `src/poc_remotion/cli.py`, `tests/test_storyboard.py` (create)
- Test: `tests/test_storyboard.py`

**Interfaces:**
- Consumes: `Storyboard`, `StoryboardScene`, `SceneKind`, `Project.load_brief/load_sources/save_storyboard/brief_present`, `LLMClient.chat_json`.
- Produces:
  - `SCENE_ON_SCREEN_SPEC: dict[str, list[str]]` pinning the TypeScript on-screen contract per kind: `title: ["headline", "subheadline"]`, `quote: ["quote line"]`, `framework: ["panel label G", "panel label C", "panel label S", "panel label E"]`, `beforeAfter: ["before text", "after text"]`, `newsGrid: ["card 1", "card 2", "card 3", "card 4"]`, `analogy: ["scene caption"]`, `cheatSheet: ["panel 1", "panel 2", "panel 3"]`, `outro: ["call to action"]`.
  - `DURATION_TOLERANCE = 0.25`; `run_storyboard(project, client) -> Storyboard`.
  - Rules enforced after parsing: `brief_present()` else `DraftError("brief not captured; run discover and brief first")`; sources registered else `DraftError` naming ingest; `3 <= len(scenes) <= 12`; every `on_screen` list length equals `len(SCENE_ON_SCREEN_SPEC[kind])`; `abs(duration_seconds - brief.duration_minutes * 60) <= DURATION_TOLERANCE * brief.duration_minutes * 60` else `DraftError` stating target vs actual; `abs(sum(scene.seconds) - duration_seconds) <= 1.5` triggers exactly one repair re-ask (same schema, user prompt appended with the mismatch) then `DraftError` if still off. Saves via `save_storyboard` only after all checks pass.
  - CLI: `poc-remotion draft-storyboard --id ID [--projects-root DIR]`; prints the scene table (id, kind, seconds, summary); exit 2 on `DraftError`.

- [ ] **Step 1: Write the failing tests**

```python
def test_draft_storyboard_happy_path(tmp_path): ...        # brief+sources seeded; mocked reply valid per rules -> saved storyboard, printed table, exit 0
def test_draft_requires_brief(tmp_path): ...               # no brief -> exit 2, message names discover/brief
def test_draft_duration_outside_window(tmp_path): ...      # brief 5 minutes, reply says 2 minutes -> exit 2, message shows "5.0 minutes" and "2.0 minutes"; storyboard.json absent
def test_scene_seconds_mismatch_repairs_once(tmp_path): ...# first reply sum off by 10s, second reply correct -> saved; captured payloads show repair text containing "seconds"
def test_on_screen_length_enforced(tmp_path): ...          # reply with framework scene having 2 on_screen entries -> DraftError naming the scene id and kind
```

- [ ] **Step 2: Run** `uv run pytest tests/test_storyboard.py -v`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement.** The system prompt embeds the 8-kind catalogue with each kind's purpose (one line, from design section 7) and `SCENE_ON_SCREEN_SPEC`; the user prompt embeds the brief (audience, objectives, tone, duration target) and source titles with headings.

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/storyboard.py src/poc_remotion/cli.py tests/test_storyboard.py
git commit -m "feat: model-drafted storyboard with semantic checks"
```

### Task 8: Script drafting (`draft-script`)

**Files:**
- Create: `src/poc_remotion/script_draft.py`
- Modify: `src/poc_remotion/cli.py`, `tests/test_script_draft.py` (create)
- Test: `tests/test_script_draft.py`

**Interfaces:**
- Consumes: `Project.load_storyboard/is_approved/save_script`, `Brief`, `SourceRef` list, `LLMClient.chat_json`.
- Produces: `run_script(project, client) -> ScriptDoc`. Rules: requires `is_approved("storyboard")` and `is_approved("duration")` else `DraftError("approve the storyboard and duration gates first")`; one line minimum per scene id (exactly the storyboard's scene ids, no extras); lines carry no timings (`start_seconds`/`end_seconds` left None); `ScriptDoc.on_screen` omitted (scenes render their storyboard `on_screen`); total narration word count within 35 percent of `duration_seconds / 60 * 150` words else `DraftError` stating both numbers. Saves via `save_script` after checks. CLI: `poc-remotion draft-script --id ID [--projects-root DIR]`; prints per-scene line counts and word total.

- [ ] **Step 1: Write the failing tests**

```python
def test_draft_script_happy_path(tmp_path): ...            # approved gates; mocked reply one line per scene -> saved, exit 0
def test_draft_script_requires_gates(tmp_path): ...        # gates not approved -> exit 2, message names the gates
def test_draft_script_unknown_scene_rejected(tmp_path): ...# reply with scene_id "sX" -> DraftError naming it; script.json absent
def test_draft_script_word_count_window(tmp_path): ...     # 5 min storyboard, reply with ~40 words total -> DraftError showing "40" and expected window
```

- [ ] **Step 2: Run** `uv run pytest tests/test_script_draft.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.** Prompt embeds the approved storyboard (ids, kinds, seconds, summaries, on_screen spec) plus brief; instruction: conversational British narration, light and witty, one to three sentences per scene, no invented facts beyond the source summaries.

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/script_draft.py src/poc_remotion/cli.py tests/test_script_draft.py
git commit -m "feat: model-drafted narration script behind gates"
```

### Task 9: Claim register from the approved script (`claims`)

**Files:**
- Create: `src/poc_remotion/claims.py`
- Modify: `src/poc_remotion/cli.py`, `tests/test_claims.py` (create)
- Test: `tests/test_claims.py`

**Interfaces:**
- Consumes: `Claim`, `Project.load_script/load_sources/save_claims/load_claims`, `LLMClient.chat_json`.
- Produces: `run_claims(project, client) -> list[Claim]`. Rules: requires `is_approved("script")` else `DraftError("approve the script gate first")`; one `chat_json` call per script line batching is not needed (lines are few) extracting `{text, source_heading}` factual claims; `id` assigned `claim-<line no>-<n>`; `source_ids`: ids of sources whose `headings` contain `source_heading` (case-insensitive) else empty; `status`: `"supported"` when `source_ids` non-empty and `locator` set to the matched heading, else `"unresolved"` with `locator = source_heading` as returned. Saves the full register. CLI: `poc-remotion claims --id ID [--projects-root DIR]`; prints `<id>  <status>  <text>` lines and a final `N unresolved` warning line when N > 0.

- [ ] **Step 1: Write the failing tests**

```python
def test_claims_extracted_and_supported(tmp_path): ...     # mocked reply heading matches source -> claim supported with source id and locator
def test_claims_unresolved_when_heading_unknown(tmp_path): ...  # heading not in source headings -> status unresolved, empty source_ids
def test_claims_requires_script_gate(tmp_path): ...        # script not approved -> exit 2 naming the gate
def test_claims_rerun_replaces_register(tmp_path): ...     # second run -> claims.json holds exactly the new register
```

- [ ] **Step 2: Run** `uv run pytest tests/test_claims.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/claims.py src/poc_remotion/cli.py tests/test_claims.py
git commit -m "feat: claim register traced to sources"
```

### Task 10: Plan B end-to-end flow

**Files:**
- Test: `tests/test_pipeline_b.py` (create)

**Interfaces:**
- Consumes: everything above through `cli.main` with a scripted mocked `_post` that routes by prompt markers (`"Answers to incorporate:"` -> capture reply; `"storyboard"` in system prompt -> storyboard reply; `"narration"` -> script reply; `"claim"` -> claims reply).

- [ ] **Step 1: Write the failing test**

```python
def test_full_pipeline_b_flow(tmp_path): ...
# init -> ingest (one temp source md) -> discover -> brief --qa-file ->
# draft-storyboard -> approve storyboard + duration -> draft-script ->
# approve script -> claims
# Assert: exit codes all 0; brief.json, storyboard.json, script.json,
# claims.json all present and schema-valid; all_approved() True; unresolved
# claims reported in claims output.
```

- [ ] **Step 2: Run** `uv run pytest tests/test_pipeline_b.py -v`. Expected: PASS after fixing any wiring gaps it exposes (fix product code, not the test).

- [ ] **Step 3: Full suite + ruff.** Expected: green, pristine.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pipeline_b.py
git commit -m "test: plan B pipeline end-to-end flow"
```

---

## Definition of Done (Plan B)

- `uv run pytest tests/ -v` and `uv run ruff check src tests` clean.
- `poc-remotion ingest/discover/brief/draft-storyboard/draft-script/claims` all exist with the documented exit codes; `poc-remotion --help` exits 0.
- A project can go from empty to fully gated (storyboard + script approved, claims registered) entirely through the CLI with a real `local-qwen` gateway, run from any working directory.
- No changes to TypeScript files; render behaviour byte-identical to Plan A for the fixture project.
