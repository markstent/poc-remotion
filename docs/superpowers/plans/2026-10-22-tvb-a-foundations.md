# Training Video Builder, Plan A: Foundations and First Branded Render, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standing project foundations for the Training Video Builder: typed project state with approval gates, the exact brand system, a LiteLLM JSON client, the Remotion scene library for all eight scene types including the Colleague character, and a gated render bridge producing a real MP4. Ends with a local voice spike the user picks from.

**Architecture:** A Python package at the repo root (`src/poc_remotion/`, uv + pytest + ruff) owns project state, schemas, LLM calls and the render bridge. The existing `remotion-starter/` Node package owns composition, scenes and rendering; Python invokes it via `npx remotion`. Contracts: pydantic models generate JSON Schema; TypeScript mirrors the same field names.

**Tech Stack:** Python 3.13 / uv / pytest / ruff / pydantic v2; TypeScript / React / Remotion 4.0.538 (npm); LiteLLM gateway (openai-compatible, key from environment).

**Spec:** `docs/superpowers/specs/2026-10-22-training-video-builder-design.md` (read together with `docs/Training_Video_Builder_PRD_v1.0.md`).

**Follow-on plans:** B (ingest, discovery, storyboard, script, claims, approvals) and C (TTS, alignment, burned-in captions + SRT, revision, export, video 1 production) are written and reviewed after this plan lands.

## Global Constraints

- Brand tokens, exact values, no others in brand surfaces: turquoise `#27E2CC`, darkTeal `#1D4757`, lime `#C4F600`, paleBlue `#CCFFFF`, white `#FFFFFF`, black `#000000`, turquoise75 `#5DE9D9`, turquoise50 `#93F0E5`, turquoise25 `#C9F8F2`, darkTeal75 `#496E7A`, darkTeal50 `#829BA3`, darkTeal25 `#C3CFD1`.
- No lime tints exist; never invent them. No orb/sphere decoration in any scene. No logos anywhere.
- Fonts: PP Pangram Sans from `src/fonts/` (untracked, licence unconfirmed). WOFF2 preferred. Never fabricate or redistribute font files.
- Every model call goes through the LiteLLM gateway. Credentials come from the environment (`LITELLM_API_KEY`); never in code, config, project data or Git.
- No paid APIs. Local-only execution.
- Python 3.13 with uv; pytest for tests; ruff for lint. Node 24 with npm; Remotion stays at 4.0.538.
- British English in all user-facing copy; no em dashes.
- Deterministic composition: render output depends only on project files and pinned tool versions (no Math.random, no wall-clock inside scenes).
- Never commit: `src/fonts/`, `.superpowers/`, `data/voice_samples/`, `.env*` (except `.env.example`), project `audio/`/`output/` artefacts.

## Review Focus

1. A near-miss brand colour (for example `#28E3CD`) must be rejected, never silently accepted. Test in Task 4.
2. A missing font file must fail validation listing the missing weights, never pass silently. Test in Task 4.
3. Production must stay blocked while any approval gate is unrecorded, even when storyboard and script files exist. Tests in Task 2 and Task 12.
4. Malformed model output must never be written into project state: one repair retry, then a clear error. Test in Task 6.
5. An unsafe project id (path separators, uppercase, spaces) must be rejected at creation. Test in Task 2.

---

### Task 1: Data schemas

**Files:**
- Create: `src/poc_remotion/schemas.py`
- Modify: `pyproject.toml` (add `pydantic>=2` dependency)
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces: `SceneKind = Literal["title", "newsGrid", "beforeAfter", "framework", "quote", "analogy", "cheatSheet", "outro"]`; models `SourceRef`, `Claim`, `StoryboardScene`, `Storyboard`, `ScriptLine`, `ScriptDoc`, `ApprovalState`, `ProjectManifest`; `generate_json_schemas(out_dir: Path) -> list[Path]`.
- Field names are snake_case and are the wire contract for TypeScript in Task 7. Later tasks import these names unchanged.

- [ ] **Step 1: Write the failing tests**

```python
SCENE_KINDS = ["title", "newsGrid", "beforeAfter", "framework", "quote", "analogy", "cheatSheet", "outro"]

def test_scene_kinds_match_design():
    assert get_args(SceneKind) == tuple(SCENE_KINDS)  # order too: scenes index by position

def test_storyboard_roundtrip():
    sb = Storyboard(objectives=["x"], duration_seconds=5.0, rationale="r", scenes=[_scene("s1", "title", 3.0), _scene("s2", "quote", 2.0)])
    assert Storyboard.model_validate_json(sb.model_dump_json()) == sb

def test_nonpositive_duration_rejected():
    with pytest.raises(ValidationError):
        Storyboard(objectives=[], duration_seconds=0, rationale="r", scenes=[_scene("s1", "title", 1.0)])

def test_duplicate_scene_ids_rejected():
    with pytest.raises(ValidationError):
        Storyboard(objectives=[], duration_seconds=2.0, rationale="r", scenes=[_scene("s1", "title", 1.0), _scene("s1", "quote", 1.0)])

def test_schema_files_generated(tmp_path):
    paths = generate_json_schemas(tmp_path)
    assert {p.name for p in paths} >= {"Storyboard.json", "ScriptDoc.json"}
```

`_scene(id, kind, seconds)` builds a valid `StoryboardScene` (purpose, summary, on_screen filled with placeholder strings).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL, `ModuleNotFoundError: poc_remotion.schemas` (or ImportError of names).

- [ ] **Step 3: Implement `src/poc_remotion/schemas.py`**

Pydantic v2 models with exactly these fields:
- `SourceRef`: `id: str`, `title: str`, `path: str`, `kind: Literal["markdown", "text"]`, `sha256: str`, `headings: list[str] = []`, `extraction_notes: str = ""`.
- `Claim`: `id: str`, `text: str`, `source_ids: list[str]`, `locator: str | None = None`, `status: Literal["supported", "unresolved", "conflict"]`.
- `StoryboardScene`: `id`, `kind: SceneKind`, `purpose: str`, `seconds: float` (validator `> 0`), `summary: str`, `on_screen: list[str] = []`, `source_ids: list[str] = []`; id validator: regex `^[a-z0-9][a-z0-9-]*$`.
- `Storyboard`: `objectives: list[str]`, `duration_seconds: float` (validator `> 0`), `rationale: str`, `scenes: list[StoryboardScene]`; model validator: scene ids unique.
- `ScriptLine`: `scene_id: str`, `text: str`, `start_seconds: float | None = None`, `end_seconds: float | None = None`.
- `ScriptDoc`: `lines: list[ScriptLine]`, `on_screen: dict[str, list[str]] = {}`.
- `ApprovalState`: `storyboard: bool = False`, `duration: bool = False`, `script: bool = False`.
- `ProjectManifest`: `id: str`, `created_at: str`, `updated_at: str`, `model: str = ""`, `brand_version: str = ""`.
- `generate_json_schemas` writes `model_json_schema()` per model to `out_dir/<Name>.json`.

- [ ] **Step 4: Add the dependency and run tests**

Run: `uv add pydantic` then `uv run pytest tests/test_schemas.py -v`
Expected: PASS (all five).

- [ ] **Step 5: Lint**

Run: `uv run ruff check src tests`
Expected: no findings.

- [ ] **Step 6: Commit**

```bash
git add src/poc_remotion/schemas.py tests/test_schemas.py pyproject.toml uv.lock
git commit -m "feat: typed project schemas as contract source of truth"
```

### Task 2: Project store with approval gates

**Files:**
- Create: `src/poc_remotion/project.py`
- Test: `tests/test_project.py`

**Interfaces:**
- Consumes: Task 1 models.
- Produces: `class ProjectError(Exception)`; `class Project` with `create(cls, dir: Path, id: str, model: str = "") -> Project`, `load(cls, dir: Path) -> Project`, `dir: Path`, `id: str`; `save_sources(list[SourceRef]) / load_sources() -> list[SourceRef]`; `save_storyboard(Storyboard) / load_storyboard() -> Storyboard`; `save_script(ScriptDoc) / load_script() -> ScriptDoc`; `record_approval(stage: Literal["storyboard", "duration", "script"]) -> None`; `is_approved(stage) -> bool`; `all_approved() -> bool`; `manifest() -> ProjectManifest`.
- Layout under `dir`: `brief.json` (empty until plan B), `sources.json`, `claims.json`, `storyboard.json`, `script.json`, `approvals.json`, `manifest.json`, `audio/`, `assets/`, `subtitles/`, `output/`.

- [ ] **Step 1: Write the failing tests**

```python
def test_create_creates_layout(tmp_path):
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    for name in ["manifest.json", "approvals.json"]:
        assert (p.dir / name).exists()
    for sub in ["audio", "assets", "subtitles", "output"]:
        assert (p.dir / sub).is_dir()

def test_unsafe_ids_rejected(tmp_path):
    for bad in ["../evil", "A B", "Upper", "a/b", "", "-x"]:
        with pytest.raises(ProjectError):
            Project.create(tmp_path / "projects" / "x", bad)

def test_gates_default_closed(tmp_path):
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    assert not p.all_approved()
    for stage in ["storyboard", "duration", "script"]:
        assert not p.is_approved(stage)

def test_approvals_persist_across_load(tmp_path):
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    p.record_approval("storyboard"); p.record_approval("duration")
    p2 = Project.load(tmp_path / "projects" / "demo")
    assert p2.is_approved("storyboard") and p2.is_approved("duration") and not p2.is_approved("script")

def test_load_missing_document_raises(tmp_path):
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    with pytest.raises(ProjectError):
        p.load_storyboard()

def test_storyboard_roundtrip_through_store(tmp_path):
    p = Project.create(tmp_path / "projects" / "demo", "demo")
    sb = _fixture_storyboard()
    p.save_storyboard(sb)
    assert Project.load(p.dir).load_storyboard() == sb
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_project.py -v`
Expected: FAIL, `ModuleNotFoundError: poc_remotion.project`.

- [ ] **Step 3: Implement `src/poc_remotion/project.py`**

- id validator: `^[a-z0-9][a-z0-9-]{1,63}$` else `ProjectError` (Review Focus 5).
- Every save writes the model JSON plus updates `manifest.json` (`updated_at`, `model`). `created_at` set once at create.
- `record_approval` persists `ApprovalState` to `approvals.json`; loading merges unknown extra keys away by parsing as `ApprovalState`.
- Missing document files raise `ProjectError` naming the file.
- `all_approved()` returns `storyboard and duration and script`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_project.py -v`
Expected: PASS (all six).

- [ ] **Step 5: Lint and commit**

Run: `uv run ruff check src tests` (no findings), then:

```bash
git add src/poc_remotion/project.py tests/test_project.py
git commit -m "feat: project store with approval gates"
```

### Task 3: CLI skeleton: init, status, approve, validate

**Files:**
- Create: `src/poc_remotion/cli.py`
- Modify: `pyproject.toml` (`[project.scripts] poc-remotion = "poc_remotion.cli:main"`), `src/poc_remotion/__init__.py` (remove the template `main`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `main(argv: list[str] | None = None) -> int`.
- Subcommands: `init --id ID [--projects-root DIR]`; `status --id [--projects-root DIR]`; `approve --id --stage {storyboard,duration,script}`; `validate --id [--projects-root DIR]` (store integrity now; brand checks join in Task 4).
- Exit codes: 0 success, 2 on `ProjectError` with message on stderr. Default `--projects-root` is `./projects`.

- [ ] **Step 1: Write the failing tests**

```python
def test_init_then_status(tmp_path, capsys):
    assert main(["init", "--id", "demo", "--projects-root", str(tmp_path)]) == 0
    assert main(["status", "--id", "demo", "--projects-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "storyboard: not approved" in out and "script: not approved" in out

def test_approve_updates_status(tmp_path, capsys):
    main(["init", "--id", "demo", "--projects-root", str(tmp_path)])
    assert main(["approve", "--id", "demo", "--stage", "storyboard", "--projects-root", str(tmp_path)]) == 0
    main(["status", "--id", "demo", "--projects-root", str(tmp_path)])
    assert "storyboard: approved" in capsys.readouterr().out

def test_bad_stage_exits_two(tmp_path):
    assert main(["approve", "--id", "demo", "--stage", "nope", "--projects-root", str(tmp_path)]) == 2

def test_validate_ok_on_fresh_project(tmp_path):
    main(["init", "--id", "demo", "--projects-root", str(tmp_path)])
    assert main(["validate", "--id", "demo", "--projects-root", str(tmp_path)]) == 0
```

Note: argparse rejects an invalid `--stage` choice with exit code 2 by itself; the test pins that contract.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL, `ModuleNotFoundError: poc_remotion.cli`.

- [ ] **Step 3: Implement `src/poc_remotion/cli.py`**

argparse with the four subcommands, calling Task 2's `Project`. `status` prints one line per gate (`storyboard: approved|not approved`, then duration, script). `validate` loads every document that exists, re-validates through pydantic, prints `ok`, exits 0; `ProjectError` exits 2. Update `pyproject.toml` entry point; replace `__init__.py` body with a module docstring.

- [ ] **Step 4: Run tests and full suite**

Run: `uv run pytest tests/ -v`
Expected: PASS (all, including existing `test_smoke.py`).

- [ ] **Step 5: Lint and commit**

Run: `uv run ruff check src tests` (no findings), then:

```bash
git add src/poc_remotion/cli.py src/poc_remotion/__init__.py pyproject.toml tests/test_cli.py uv.lock
git commit -m "feat: CLI init, status, approve, validate"
```

### Task 4: Brand system and validation

**Files:**
- Create: `brand/brand.json`
- Create: `src/poc_remotion/brand.py`
- Modify: `src/poc_remotion/cli.py` (`validate` also runs brand checks)
- Test: `tests/test_brand.py`

**Interfaces:**
- Produces: `load_brand(path: Path = Path("brand/brand.json")) -> BrandConfig`; `contrast_ratio(hex_a: str, hex_b: str) -> float`; `validate_brand(brand: BrandConfig, fonts_dir: Path) -> list[str]` (empty list means valid).
- `BrandConfig` fields: `version: str`, `tokens: dict[str, str]` (12 entries), `font_family: str = "PP Pangram Sans"`, `fonts: dict[str, str]` (weight name -> file name inside the WOFF2 directory), `contrast_pairs: list[tuple[str, str, float]]` (fg, bg, minimum ratio), `fonts_dir: str = "src/fonts"`.
- TypeScript consumes the same file in Task 7.

- [ ] **Step 1: Write `brand/brand.json`**

Tokens, exact keys and hex values: `turquoise #27E2CC`, `darkTeal #1D4757`, `lime #C4F600`, `paleBlue #CCFFFF`, `white #FFFFFF`, `black #000000`, `turquoise75 #5DE9D9`, `turquoise50 #93F0E5`, `turquoise25 #C9F8F2`, `darkTeal75 #496E7A`, `darkTeal50 #829BA3`, `darkTeal25 #C3CFD1`. No lime tints.
Fonts map, one entry per WOFF2 weight file found by listing `src/fonts/NEW PangramSans – Web Open Font ` (exact directory name includes the trailing space; record actual file names): at minimum `extrabold`, `bold`, `semibold`, `regular`, `condensedBold`.
Contrast pairs (minimum 4.5): darkTeal on white, darkTeal on paleBlue, darkTeal on turquoise, darkTeal on lime, white on darkTeal, turquoise on darkTeal, darkTeal on turquoise25.

- [ ] **Step 2: Write the failing tests**

```python
EXPECTED = {"turquoise": "#27E2CC", "darkTeal": "#1D4757", "lime": "#C4F600", "paleBlue": "#CCFFFF",
            "white": "#FFFFFF", "black": "#000000", "turquoise75": "#5DE9D9", "turquoise50": "#93F0E5",
            "turquoise25": "#C9F8F2", "darkTeal75": "#496E7A", "darkTeal50": "#829BA3", "darkTeal25": "#C3CFD1"}

def test_tokens_exact_set_and_values():
    brand = load_brand()
    assert brand.tokens == EXPECTED

def test_near_miss_token_rejected(tmp_path):
    bad = dict(EXPECTED, turquoise="#28E3CD")  # one off from approved
    _write(tmp_path, bad)
    with pytest.raises(ValidationError):
        load_brand(tmp_path / "brand.json")

def test_contrast_values():
    assert contrast_ratio("#1D4757", "#FFFFFF") >= 4.5
    assert contrast_ratio("#C4F600", "#CCFFFF") < 4.5

def test_validate_ok_on_real_files():
    assert validate_brand(load_brand(), Path("src/fonts")) == []

def test_missing_font_listed(tmp_path):
    problems = validate_brand(load_brand(), tmp_path)  # empty dir
    assert problems and all("missing font" in p for p in problems)

def test_contrast_failure_listed():
    brand = load_brand().model_copy(deep=True)
    brand.contrast_pairs.append(("lime", "paleBlue", 4.5))
    problems = validate_brand(brand, Path("src/fonts"))
    assert any("contrast" in p for p in problems)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_brand.py -v`
Expected: FAIL, `ModuleNotFoundError: poc_remotion.brand`.

- [ ] **Step 4: Implement `src/poc_remotion/brand.py` and wire `validate`**

- `load_brand` validates against an exact-token pydantic model: extra or missing tokens, or altered hex values, raise `ValidationError` (Review Focus 1).
- `contrast_ratio`: WCAG relative luminance on sRGB hex.
- `validate_brand` returns problem strings: `missing font <weight>: <file>` for each absent file (Review Focus 2), `contrast <fg> on <bg>: <ratio> < required` for each failing pair.
- CLI `validate`: after store checks, run brand validation; problems exit 2 with one line each.

- [ ] **Step 5: Run tests, lint, commit**

Run: `uv run pytest tests/test_brand.py tests/test_cli.py -v` (PASS), `uv run ruff check src tests` (clean), then:

```bash
git add brand/brand.json src/poc_remotion/brand.py src/poc_remotion/cli.py tests/test_brand.py
git commit -m "feat: brand tokens, font manifest and contrast validation"
```

### Task 5: Markdown source ingest

**Files:**
- Create: `src/poc_remotion/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: Task 1 `SourceRef`.
- Produces: `ingest_markdown(path: Path) -> SourceRef`. PDF/DOCX/PPTX parsers are deferred to plan B; this function is the pattern.

- [ ] **Step 1: Write the failing tests**

```python
MD = "# My Title\n\nintro\n\n## One\n\ntext\n\n## Two\n\ntext\n"

def test_id_is_content_hash(tmp_path):
    a = ingest_markdown(_write(tmp_path / "a.md", MD)); b = ingest_markdown(_write(tmp_path / "b.md", MD))
    assert a.id == b.id and len(a.id) == 12

def test_title_from_h1(tmp_path):
    assert ingest_markdown(_write(tmp_path / "a.md", MD)).title == "My Title"

def test_headings_h2_h3_only(tmp_path):
    md = MD + "### Three\n\ntext\n#### Four\n\ntext\n"
    assert ingest_markdown(_write(tmp_path / "a.md", md)).headings == ["One", "Two", "Three"]

def test_extraction_note_records_fidelity(tmp_path):
    assert ingest_markdown(_write(tmp_path / "a.md", MD)).extraction_notes == "full text captured"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: FAIL, `ModuleNotFoundError: poc_remotion.ingest`.

- [ ] **Step 3: Implement `src/poc_remotion/ingest.py`**

`id = hashlib.sha256(bytes).hexdigest()[:12]`; title from first `# ` heading else filename stem; headings from `^## ` and `^### ` lines in order, `### ` stripped of markup; `kind: Literal["markdown"]`; `path` stored absolute.

- [ ] **Step 4: Run tests, lint, commit**

Run: `uv run pytest tests/test_ingest.py -v` (PASS), `uv run ruff check src tests` (clean), then:

```bash
git add src/poc_remotion/ingest.py tests/test_ingest.py
git commit -m "feat: markdown source ingest with content-hash ids"
```

### Task 6: LiteLLM JSON client

**Files:**
- Create: `src/poc_remotion/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces: `class LLMError(Exception)`; `class LLMClient` with `__init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None)` (env fallbacks `LITELLM_BASE_URL` default `http://127.0.0.1:4000/v1`, `LITELLM_API_KEY` required, `LITELLM_MODEL` default `local-qwen`) and `chat_json(self, system: str, user: str, schema: type[T]) -> T`.
- Constructor takes an optional `_post` parameter (transport function `(url, key, payload) -> str`) so tests stub the network. Nothing in this module writes project state.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm.py -v`
Expected: FAIL, `ModuleNotFoundError: poc_remotion.llm`.

- [ ] **Step 3: Implement `src/poc_remotion/llm.py`**

- POST `{base_url}/chat/completions` via urllib with `Authorization: Bearer <key>`; parse `choices[0].message.content`.
- Strip Markdown code fences; `json.loads`; `schema.model_validate`.
- On parse/validation failure: one repair request whose user message includes the original output and the validation error; second failure raises `LLMError` with both messages (Review Focus 4).
- Missing/empty key raises `LLMError` naming `LITELLM_API_KEY`.

- [ ] **Step 4: Run tests, lint, commit**

Run: `uv run pytest tests/test_llm.py -v` (PASS), `uv run ruff check src tests` (clean), then:

```bash
git add src/poc_remotion/llm.py tests/test_llm.py
git commit -m "feat: LiteLLM JSON client with repair retry"
```

### Task 7: Remotion tokens loader and scene types

**Files:**
- Create: `remotion-starter/src/lib/tokens.ts`
- Create: `remotion-starter/src/lib/types.ts`
- Modify: `remotion-starter/tsconfig.json` only if `resolveJsonModule` is not enabled
- Test: verification via the package's own checks

**Interfaces:**
- Consumes: `brand/brand.json` (Task 4).
- Produces: `loadTokens(): BrandTokens` (throws `Error` listing missing required tokens when absent); `export type SceneKind` and `export interface Storyboard`, `StoryboardScene`, `ScriptLine`, `ScriptDoc` mirroring the pydantic field names exactly (snake_case, e.g. `duration_seconds`, `scene_id`, `start_seconds`).

- [ ] **Step 1: Implement `types.ts` and `tokens.ts`**

Types carry the same fields as Task 1 models. `BrandTokens`: `tokens` (12 keys), `fontFamily`, `fonts`, `contrast_pairs`. `loadTokens()` reads `../brand/brand.json` relative to the package root via `fs` at module call time, validates all 12 token keys and hex format `^#[0-9A-F]{6}$`, throws with a `missing tokens:` list otherwise.

- [ ] **Step 2: Verify**

Run: `cd remotion-starter && npm run lint`
Expected: eslint and `tsc` pass.

- [ ] **Step 3: Commit**

```bash
git add remotion-starter/src/lib remotion-starter/tsconfig.json
git commit -m "feat: brand tokens loader and scene types for Remotion"
```

### Task 8: Colleague character component

**Files:**
- Create: `remotion-starter/src/components/Colleague.tsx`

**Interfaces:**
- Produces: `export function Colleague({ pose, mood, size }: { pose: "idle" | "point" | "shrug" | "cheer" | "oops"; mood?: "happy" | "neutral" | "oops"; size: number }): JSX.Element` where `size` is pixel height. Looks match the approved mockup: flat darkTeal body, white eyes, lime smile, on any background. Arm angles per pose; idle adds a gentle deterministic bob via `useCurrentFrame()` with fixed spring config. Colour values come only from `loadTokens()`. Facial feature circles are allowed; background orbs are banned.

- [ ] **Step 1: Implement the component**

- [ ] **Step 2: Verify**

Run: `cd remotion-starter && npm run lint`
Expected: eslint and `tsc` pass. (Pose stills are rendered in Task 11's verification.)

- [ ] **Step 3: Commit**

```bash
git add remotion-starter/src/components/Colleague.tsx
git commit -m "feat: Colleague flat vector character"
```

### Task 9: Scenes batch 1: title, quote, framework

**Files:**
- Create: `remotion-starter/src/scenes/Title.tsx`, `remotion-starter/src/scenes/Quote.tsx`, `remotion-starter/src/scenes/Framework.tsx`

**Interfaces:**
- Consumes: `Colleague`, `loadTokens`, types from Task 7.
- Produces: `export type SceneProps = { scene: StoryboardScene; fps: number }`. Each component fills the frame for `scene.seconds * fps` frames when wrapped in a `<Sequence>` by the parent. Title: character entrance from the right, kinetic two-line title, lime underline bar. Quote: full-bleed lime, huge darkTeal line from `scene.on_screen[0]`, white speech bubble "What's missing?". Framework: four rounded panels (G turquoise, C paleBlue, S paleBlue, E lime) revealed in order across the duration.

- [ ] **Step 1: Implement the three components**

- [ ] **Step 2: Verify**

Run: `cd remotion-starter && npm run lint`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add remotion-starter/src/scenes
git commit -m "feat: title, quote and framework scenes"
```

### Task 10: Scenes batch 2 and complete registry

**Files:**
- Create: `remotion-starter/src/scenes/BeforeAfter.tsx`, `NewsGrid.tsx`, `Analogy.tsx`, `CheatSheet.tsx`, `Outro.tsx`, `remotion-starter/src/scenes/index.ts`

**Interfaces:**
- Produces: `export const SCENES: Record<SceneKind, React.FC<SceneProps>>`. Completeness is enforced by the compiler: `Record` over the eight-kind union fails `tsc` if any component is missing. `BeforeAfter`: narrow pale prompt panel vs wide white GCSE panel, Colleague `oops` beside the before. `NewsGrid`: 2x2 white cards with lime lesson strips on darkTeal. `Analogy`: lorry carrying one envelope (shapes only) on lime, darkTeal line. `CheatSheet`: three rounded summary panels. `Outro`: white panel prompt card, Colleague `cheer` wave.

- [ ] **Step 1: Implement the five components and the registry**

- [ ] **Step 2: Verify**

Run: `cd remotion-starter && npm run lint`
Expected: pass; a missing scene kind would fail `tsc` here.

- [ ] **Step 3: Commit**

```bash
git add remotion-starter/src/scenes
git commit -m "feat: remaining scenes and complete scene registry"
```

### Task 11: TrainerVideo composition, captions, determinism

**Files:**
- Create: `remotion-starter/src/TrainerVideo.tsx`, `remotion-starter/testdata/fixture-storyboard.json`, `remotion-starter/testdata/fixture-script.json`
- Modify: `remotion-starter/src/Root.tsx` (register `TrainerVideo` at 1920x1080 fps 30 with `calculateMetadata`; keep the starter's existing composition untouched)
- Test: verification via still renders

**Interfaces:**
- Consumes: `SCENES`, `Colleague`, types, `loadTokens`.
- Produces: composition id `TrainerVideo` with props `{ storyboard: Storyboard; script: ScriptDoc }`. `calculateMetadata` returns `durationInFrames = Math.ceil((sum(scene.seconds) + 0.5) * 30)`. Renders each scene in a `<Sequence>` and a caption pill (bottom left, translucent darkTeal panel, lime cue bar, white Semibold text) showing the active `ScriptLine` found by `start_seconds <= t < end_seconds`, falling back to nearest line when timings are null.

- [ ] **Step 1: Write the fixtures**

`fixture-storyboard.json`: two scenes, `s1` title 3 seconds, `s2` quote 2 seconds, duration 5, one objective, short rationale. `fixture-script.json`: two lines with timings (0.0-2.8, 3.0-4.8) covering both scenes.

- [ ] **Step 2: Implement `TrainerVideo.tsx` and register it**

- [ ] **Step 3: Verify stills and determinism**

Run:
```bash
cd remotion-starter
npx remotion still TrainerVideo out/test/frame0.png --props=testdata/props.json --frame=0
npx remotion still TrainerVideo out/test/frame90.png --props=testdata/props.json --frame=90
```
with `testdata/props.json` containing both fixtures. Expected: both PNGs exist and are non-trivial size; frame90 shows the caption pill. Determinism: render frame 0 twice, `shasum` both files, hashes must be equal. Also render Colleague pose stills: a temporary props file with a `title` scene is already exercised by frame0; pose coverage is reviewed visually here (idle in frame0, plus one still per remaining pose if the implementer adds a check composition; otherwise reviewer confirms poses in Task 13 video).

- [ ] **Step 4: Lint, add `out/` to `.gitignore`, commit**

```bash
cd remotion-starter && npm run lint && cd ..
echo "remotion-starter/out/" >> .gitignore
git add remotion-starter/src/TrainerVideo.tsx remotion-starter/src/Root.tsx remotion-starter/testdata .gitignore
git commit -m "feat: TrainerVideo composition with caption layer"
```

### Task 12: Gated render bridge

**Files:**
- Create: `src/poc_remotion/render.py`
- Modify: `src/poc_remotion/cli.py` (add `render --id [--scale]`)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Project` (Task 2), CLI (Task 3).
- Produces: `class GateError(Exception)`; `@dataclass RenderOptions: scale: float = 1.0`; `render_video(project: Project, opts: RenderOptions | None = None) -> Path`. Writes `output/props.json` from the project's storyboard and script, runs `npx remotion render TrainerVideo <output/video.mp4> --props=<props.json> --scale=<scale>` with `cwd=remotion-starter`, returns the MP4 path. Raises `GateError` naming the unrecorded stages when `all_approved()` is false (Review Focus 3).

- [ ] **Step 1: Write the failing tests**

```python
def test_render_blocked_without_gates(tmp_path):
    p = _approved_project(tmp_path, stages=[])  # storyboard+script saved, nothing approved
    with pytest.raises(GateError) as e:
        render_video(p)
    assert "storyboard" in str(e.value)

def test_render_builds_expected_command(tmp_path, monkeypatch):
    p = _approved_project(tmp_path, stages=["storyboard", "duration", "script"])
    seen = {}
    monkeypatch.setattr(render_module, "subprocess_run", lambda cmd, **kw: seen.update(cmd=cmd) or _ok())
    out = render_video(p, RenderOptions(scale=0.25))
    cmd = seen["cmd"]
    assert cmd[:3] == ["npx", "remotion", "render"] and "TrainerVideo" in cmd
    assert any(a.startswith("--scale=0.25") for a in cmd)
    assert out == p.dir / "output" / "video.mp4"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL, `ModuleNotFoundError: poc_remotion.render`.

- [ ] **Step 3: Implement `src/poc_remotion/render.py` and the CLI subcommand**

Transport: module-level `subprocess_run(cmd, cwd, capture_output=True)` so tests monkeypatch it; nonzero exit or missing output raises `RuntimeError` including stderr tail. CLI `render` prints the output path.

- [ ] **Step 4: Run tests, lint, commit**

Run: `uv run pytest tests/test_render.py tests/test_cli.py -v` (PASS), `uv run ruff check src tests` (clean), then:

```bash
git add src/poc_remotion/render.py src/poc_remotion/cli.py tests/test_render.py
git commit -m "feat: gated render bridge to Remotion"
```

### Task 13: Local voice spike and user voice pick

**Files:**
- Create: `scripts/voice_spike.py`, `config/tts.json` (after the user picks)
- Modify: `.gitignore` (add `data/voice_samples/`)
- Test: verification by listening; the user's pick is the deliverable

**Interfaces:**
- Produces: `config/tts.json` with `{"engine": "kokoro-onnx", "voice": "<user-picked-id>"}`, consumed by plan C's TTS adapter.

- [ ] **Step 1: Install the candidate engine**

Run: `uv add kokoro-onnx onnxruntime`
If installation or model download fails, try the `piper` fallback and record the deviation; if both fail, stop and report to the user (design names Kokoro as candidate, not commitment).

- [ ] **Step 2: Write and run the spike**

`scripts/voice_spike.py` synthesises the sentence "Before you answer, ask me any clarifying questions. Better prompts, better results." with three female voices (for example `af_heart`, `af_bella`, `bf_emma`) to `data/voice_samples/<voice>.wav`. Run it; verify all three WAVs exist and are non-trivially sized.

- [ ] **Step 3: User picks by ear**

Open the three samples for the user (`open data/voice_samples/*.wav`), present the voice ids in chat, and record the pick. If none satisfies, surface alternatives before proceeding.

- [ ] **Step 4: Record the choice, ignore samples, commit**

Write `config/tts.json`; add `data/voice_samples/` to `.gitignore`; commit:

```bash
git add config/tts.json .gitignore scripts/voice_spike.py
git commit -m "feat: voice spike and selected local TTS voice"
```

---

## Completion of Plan A

Definition of done for this plan: `uv run pytest tests/ -v` and `uv run ruff check src tests` clean; `cd remotion-starter && npm run lint` clean; a project created by `poc-remotion init` passes `poc-remotion validate`; `poc-remotion render` refuses without approvals and produces a playing MP4 from the fixtures once all three gates are approved; `config/tts.json` records the user's voice pick.
