# Training Video Builder Plan C: Voice, Revision and Video 1, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn an approved, gated project into a narrated, exported video: local TTS per script line, audio-true caption timings, narration in the composition, SRT sidecar, targeted scene revision, a full export bundle, and the production run for video 1.

**Architecture:** Content-addressed audio cache (file name = hash of voice + text) makes revision cheap: unchanged lines are never resynthesised. Timing is derived from real audio durations (per-line synthesis), then written back into `script.json` and `storyboard.json`. The composition receives an optional narration list; without it, renders stay byte-identical to Plan A behaviour. A final runbook produces video 1 with the user at every gate.

**Tech Stack:** Python 3.13, uv, pydantic, pytest, ruff; kokoro-onnx 0.6.1 (installed in Plan A) with `bf_emma` from `config/tts.json`; Remotion 4.0.538 (npm), `npx remotion render`.

**Spec:** `docs/superpowers/specs/2026-10-22-training-video-builder-design.md` (pipeline steps 6-9, risks section 11, success criteria section 10). Plan B (`docs/superpowers/plans/2026-10-23-tvb-b-pipeline-brain.md`) is a prerequisite: narration requires a gated project.

## Global Constraints

- Same standing constraints as Plan B (LiteLLM-only model calls, no paid APIs, snake_case contracts, British English, no em dashes, ruff/pytest clean, repo hygiene).
- Voice: `bf_emma` from `config/tts.json` (`{"engine": "kokoro-onnx", "voice": "bf_emma"}`); never hard-code the voice id in pipeline code; load the config.
- Audio files live only in `projects/<id>/audio/` and `remotion-starter/public/audio/` copies; never committed.
- Determinism: given identical project files, `render` output is reproducible; no timestamps injected into artefacts.
- Duration target for video 1: total 4:30 to 6:00 (design section 10); narrate reports the actual total and warns outside it but never silently truncates audio.
- Approval gates: narration and export require all three gates approved; `revise` resets them (user re-approves).

## Review Focus

1. TTS engine or model files missing at `narrate` time: fail with a named, actionable error before any project file is touched. Test in Task 2.
2. Real audio running longer than the storyboard planned: scenes must grow to fit the audio (storyboard updated to the actual span), never cut or speed up speech, with the new total reported against the 4:30-6:00 window. Test in Task 2.
3. Rendering with narration: audio must come from `public/audio/` copies and the render must fail with a clear message if a narration file is missing. Tests in Task 3.
4. Untimed script lines reaching the SRT exporter: they must be skipped and reported, never emitted as `00:00:00,000` blanks. Test in Task 4.
5. Revision damage: `revise` must reset gates but preserve claims, sources, and audio of untouched lines (content-addressed cache), and delete audio orphaned by the edit. Test in Task 5.

---

### Task 1: TTS configuration and adapter

**Files:**
- Create: `src/poc_remotion/tts.py`, `tests/test_tts.py`

**Interfaces:**
- Consumes: `config/tts.json` (from Plan A).
- Produces:
  - `class TTSConfig(BaseModel)`: `engine: Literal["kokoro-onnx"]`, `voice: str`; `load_tts_config(path: Path = Path("config/tts.json")) -> TTSConfig` (raises `TTSConfigError` naming the file when missing or invalid).
  - `class TtsResult(BaseModel)`: `path: str`, `duration_seconds: float`.
  - `class TtsEngine(Protocol)`: `synthesize(text: str, voice: str, out_path: Path) -> None`.
  - `class KokoroAdapter`: `__init__(self, cache_dir: Path, engine: TtsEngine | None = None)`; engine lazily built on first use (kokoro-onnx pipeline, `lang_code="b"` for `bf_` voices or `"a"` for `af_` voices, derived from the voice id prefix); `synthesize(text: str, voice: str, out_path: Path) -> TtsResult`; cache path = `cache_dir / (sha256(voice + "\n" + text)[:16] + ".wav")`; existing cache file short-circuits the engine; duration read with the `wave` module (`frames / framerate`, guarded for 0).
  - `TTSConfigError(Exception)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_tts.py`

```python
def test_load_tts_config_reads_pick(): ...          # reads repo config/tts.json -> voice "bf_emma"
def test_load_tts_config_missing_raises(tmp_path): ...
def test_synthesize_creates_cached_wav(tmp_path): ...  # FakeEngine writes a tiny valid wav; file created under hash name; duration > 0
def test_cache_hit_skips_engine(tmp_path): ...      # call twice; engine call count == 1; same TtsResult path
def test_zero_frame_wav_reports_zero_duration(tmp_path): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_tts.py -v`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement.** FakeEngine-friendly: `engine` parameter accepts any callable-compatible object; the real engine builder is a module-level `_build_engine(voice: str) -> TtsEngine` imported lazily inside it so tests never import kokoro.

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/tts.py tests/test_tts.py
git commit -m "feat: content-addressed TTS adapter with config"
```

### Task 2: Narration with audio-true timings (`narrate`)

**Files:**
- Create: `src/poc_remotion/narrate.py`
- Modify: `src/poc_remotion/cli.py`, `tests/test_narrate.py` (create)
- Test: `tests/test_narrate.py`

**Interfaces:**
- Consumes: `Project.load_script/load_storyboard/save_script/save_storyboard/is_approved/all_approved`, `KokoroAdapter.synthesize`, `TTSConfig`.
- Produces:
  - `NARRATION_GAP = 0.35` (seconds between scenes), `LINE_GAP = 0.15` (between lines in a scene), `SCENE_TAIL = 0.3` (scene extends this far past its last line).
  - `run_narrate(project: Project, tts: KokoroAdapter) -> dict`: requires `all_approved()` else `NarrateError` naming the gates; synthesises each `ScriptLine` (audio into `project.dir / "audio/"` via the adapter cache); computes a timing pass: scene starts at the storyboard's cumulative plan, line i start = scene start + sum(previous line durations + LINE_GAP), line end = start + duration; scene span = last line end - scene start + SCENE_TAIL; next scene start = max(planned start, previous line end + NARRATION_GAP); rewrites `script.json` with `start_seconds`/`end_seconds` and `storyboard.json` with each scene's `seconds = span` and `duration_seconds = last line end + SCENE_TAIL`; approvals preserved; returns a summary dict `{total_seconds, lines, audio_files}`. Any engine failure raises `NarrateError` naming the line before any JSON is rewritten (synthesis loop completes for all lines first, then a single write phase).
  - CLI: `poc-remotion narrate --id ID [--projects-root DIR]` prints per-scene audio spans, the new total, and a warning when outside the brief's window (reads `brief.json`; tolerance from Plan B's `DURATION_TOLERANCE`); exit 2 on `NarrateError`.

- [ ] **Step 1: Write the failing tests**

```python
def test_narrate_produces_timings(tmp_path): ...           # FakeTTS with per-text durations (0.5s line) -> script line start/end exact per rules; storyboard scene seconds == span
def test_narrate_preserves_approvals(tmp_path): ...
def test_narrate_requires_gates(tmp_path): ...             # not approved -> exit 2, gates named
def test_narrate_long_audio_grows_scene(tmp_path): ...     # FakeTTS returns 40s for one line in a 3s scene -> scene seconds grow to ~40.3, total reported 40-ish
def test_narrate_engine_failure_leaves_project_untouched(tmp_path): ...  # FakeTTS raises on line 2 -> NarrateError; script.json and storyboard.json mtimes/contents unchanged
def test_narrate_second_run_is_noop_for_audio(tmp_path): ...  # engine call count stays 1 across two runs (cache); timings identical
```

- [ ] **Step 2: Run** `uv run pytest tests/test_narrate.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement** (two-phase: synthesise all lines into memory of paths, then rewrite both JSON files).

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/narrate.py src/poc_remotion/cli.py tests/test_narrate.py
git commit -m "feat: narration pass with audio-true timings"
```

### Task 3: Narration in the composition (TypeScript)

**Files:**
- Modify: `remotion-starter/src/lib/types.ts`, `remotion-starter/src/TrainerVideo.tsx`, `remotion-starter/testdata/` (add narration fixture + README), `src/poc_remotion/render.py`, `tests/test_render.py`
- Test: `tests/test_render.py` (extend); TS verification by lint + renders

**Interfaces:**
- Consumes: `NarrationLine` (new): `scene_id: str`, `text: str`, `start_seconds: number`, `end_seconds: number`, `file: string` (path relative to `public/`, e.g. `audio/<hash>.wav`).
- Produces: `TrainerVideoProps.narration?: { lines: NarrationLine[] }`; composition renders one `<Sequence from={Math.round(start_seconds * fps)}><Audio src={staticFile(file)} /></Sequence>` per line inside the main frame container; absent narration renders exactly as before. `render_video` copies `project.dir/audio/*` into `remotion-starter/public/audio/` (flat, by file name) before invoking npx, and after render removes only the files it copied; if `narration.json` references a file missing from the project audio dir, `render_video` raises `RuntimeError` naming the file before invoking npx. Props JSON gains `narration` read from a new `project.dir / "narration.json"` when present (Plan C Task 4 writes it; absent key = absent prop).

- [ ] **Step 1: Write the failing Python tests** (extend `tests/test_render.py`)

```python
def test_render_copies_audio_to_public(tmp_path): ...      # project audio dir with two wavs; mocked subprocess_run asserts the copy happened (real files appear under remotion-starter/public/audio) and are removed after
def test_render_without_audio_touches_nothing(tmp_path): ...  # empty audio dir: public/audio untouched
def test_render_missing_narration_audio_fails(tmp_path): ...  # narration.json references absent.wav -> RuntimeError naming absent.wav, npx never invoked
```

- [ ] **Step 2: Run** `uv run pytest tests/test_render.py -v`. Expected: new FAIL.

- [ ] **Step 3: Implement the Python side** (copy/cleanup in `render_video`; `narration.json` -> props).

- [ ] **Step 4: TypeScript changes.** Add `NarrationLine` to `types.ts` (snake_case keys, matching the JSON); optional `narration` prop; `<Audio>` sequences gated on its presence; add `testdata/narration.json` (two lines, `audio/` paths) and `testdata/README.md` documenting that `props.json` is generated from the fixtures and how to regenerate it (one-paragraph note; script optional).

- [ ] **Step 5: Verify** `cd remotion-starter && npm run lint` clean; then a real render with a narration fixture against a real wav: `uv run poc-remotion render` on a temp project whose `narration.json` references a copied sample wav; confirm exit 0 and the MP4 is larger than the no-narration fixture render (audio track present). Full Python suite green.

- [ ] **Step 6: Commit**

```bash
git add remotion-starter/src remotion-starter/testdata src/poc_remotion/render.py tests/test_render.py
git commit -m "feat: narration playback in composition with audio staging"
```

### Task 4: Narration manifest and SRT sidecar

**Files:**
- Create: `src/poc_remotion/subtitles.py`
- Modify: `src/poc_remotion/narrate.py` (write `narration.json`), `src/poc_remotion/cli.py`, `tests/test_subtitles.py` (create), `tests/test_narrate.py` (extend)
- Test: `tests/test_subtitles.py`, `tests/test_narrate.py` (extend)

**Interfaces:**
- Produces:
  - `class NarrationLine(BaseModel)`: `scene_id: str`, `text: str`, `start_seconds: float`, `end_seconds: float`, `file: str` (public-relative path `audio/<hash>.wav`, exactly what the composition passes to `staticFile`). `run_narrate` now also writes `project.dir / "narration.json"` `{"lines": [...]}` and reports it.
  - `srt_from_script(script: ScriptDoc) -> tuple[str, int]`: (srt text, skipped count); skips lines with `start_seconds is None or end_seconds is None`; timecode format `HH:MM:SS,mmm`; sequence numbers from 1.
  - CLI: `poc-remotion export-srt --id ID [--projects-root DIR]` writes `project.dir / "subtitles" / "<id>.srt"`; prints the path and `skipped N untimed lines` when N > 0; exit 0 even with skips.

- [ ] **Step 1: Write the failing tests** in `tests/test_subtitles.py`

```python
def test_srt_two_timed_lines(): ...               # exact expected SRT text with 00:00:00,000 and millisecond rounding (1.5 -> 00:00:01,500)
def test_srt_skips_untimed_and_counts(): ...      # mixed script -> one cue, skipped == 1
def test_srt_rounds_down_to_ms(): ...             # 1.234567 -> 00:00:01,234
```

Extend `tests/test_narrate.py`: `def test_narrate_writes_narration_manifest(tmp_path): ...`

- [ ] **Step 2: Run** both test files. Expected: FAIL.

- [ ] **Step 3: Implement** + CLI wiring.

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/subtitles.py src/poc_remotion/narrate.py src/poc_remotion/cli.py tests/test_subtitles.py tests/test_narrate.py
git commit -m "feat: narration manifest and SRT sidecar export"
```

### Task 5: Targeted scene revision (`revise`)

**Files:**
- Create: `src/poc_remotion/revise.py`
- Modify: `src/poc_remotion/cli.py`, `tests/test_revise.py` (create)
- Test: `tests/test_revise.py`

**Interfaces:**
- Consumes: `Project.load_storyboard/save_storyboard/load_script/save_script/_load_approvals` (write approvals via a new `Project.reset_approvals() -> None` setting all `GATED_STAGES` false), audio cache layout, `LLMClient.chat_json`.
- Produces: `run_revise(project, client, scene_id: str, instruction: str) -> dict`. Rules: scene id must exist in the storyboard else `ReviseError` naming valid ids; one `chat_json` call returning `{"summary": str, "seconds": float, "on_screen": [...], "text": str}` validated against a `RevisedScene` model (seconds > 0, on_screen length equals `SCENE_ON_SCREEN_SPEC[kind]`); updates that scene and its script line (all lines of the scene replaced by the single new text, timings nulled); other scenes and lines untouched; `reset_approvals()` called; `narration.json` rewritten to drop lines of the revised scene; orphaned audio files (no longer referenced by any narration manifest or line hash) deleted. Returns `{scene_id, summary, seconds, new_text}`. CLI: `poc-remotion revise --id ID --scene ID --instruction "TEXT" [--projects-root DIR]`; prints old vs new summary and the gates-reset warning; exit 2 on `ReviseError`.

- [ ] **Step 1: Write the failing tests** in `tests/test_revise.py`

```python
def test_revise_updates_scene_and_line(tmp_path): ...      # mocked reply -> scene summary/seconds replaced; other scenes byte-identical; line text replaced, timings None
def test_revise_resets_gates(tmp_path): ...                # all three approvals false afterwards; claimed in output
def test_revise_keeps_other_audio(tmp_path): ...           # pre-seeded audio cache: untouched lines' wavs still present; revised scene's stale wav deleted; narration.json no longer lists it
def test_revise_unknown_scene_exits_two(tmp_path): ...
def test_revise_on_screen_length_enforced(tmp_path): ...   # wrong-length on_screen -> ReviseError, storyboard untouched
```

- [ ] **Step 2: Run** `uv run pytest tests/test_revise.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.** Prompt embeds the full storyboard plus the scene's script line and the user instruction; instruction: keep the scene kind, keep British light-witty tone, respect the on-screen contract.

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/revise.py src/poc_remotion/cli.py src/poc_remotion/project.py tests/test_revise.py
git commit -m "feat: targeted scene revision with gate reset"
```

### Task 6: Export bundle (`export`)

**Files:**
- Create: `src/poc_remotion/export.py`
- Modify: `src/poc_remotion/cli.py`, `tests/test_export.py` (create)
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `render_video(project, RenderOptions)`, `srt_from_script`, `Project.load_*` for storyboard, script, claims, sources, manifest, `load_brand`, `load_tts_config`.
- Produces: `run_export(project, scale: float = 1.0) -> Path`. Rules: requires `all_approved()`; requires every script line timed (else `ExportError` naming the untimed line count and `narrate`); renders via `render_video` (which is gate-safe); writes `subtitles/<id>.srt`; copies into `output/bundle/`: `video.mp4` (from `output/video.mp4`), `<id>.srt`, `storyboard.json`, `script.json`, `claims.json`, `sources.json`, `manifest.json`, `brand.json`, `tts.json` (the config). Returns the bundle dir. CLI: `poc-remotion export --id ID [--scale S] [--projects-root DIR]`; prints the bundle path and a file list; exit 2 on `ExportError`.

- [ ] **Step 1: Write the failing tests**

```python
def test_export_bundle_complete(tmp_path): ...             # mocked subprocess; gated+timed project -> all nine bundle files present; srt matches srt_from_script output
def test_export_requires_timed_script(tmp_path): ...       # untimed lines -> exit 2, message names narrate
def test_export_requires_gates(tmp_path): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_export.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**

- [ ] **Step 4: Full suite + ruff.** Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/poc_remotion/export.py src/poc_remotion/cli.py tests/test_export.py
git commit -m "feat: export bundle with video, srt and provenance"
```

### Task 7: Video 1 production runbook (operated by the controller with user gates)

This task is a runbook, not new code. The controller executes it in the session; every user gate pauses for explicit approval in chat. Prerequisite: Tasks 1-6 complete and green.

**Files:**
- Create: `projects/copilot-prompting-basics/` (project state, never committed)
- Reference: `docs/Copilot_Prompting_for_Beginners_Slide_Descriptions.md`

- [ ] **Step 1: Create and populate the project**

```bash
uv run poc-remotion init --id copilot-prompting-basics
uv run poc-remotion ingest --id copilot-prompting-basics --source docs/Copilot_Prompting_for_Beginners_Slide_Descriptions.md
```

- [ ] **Step 2: Discovery (user gate 1)**: run `discover`, present the questions in chat, collect answers, write them to a temp qa file, run `brief`. User approves the derived audience/tone/duration before moving on.

- [ ] **Step 3: Storyboard (user gate 2)**: `draft-storyboard`; present the scene table; on request run `revise`-style tweaks (or re-draft); user approves storyboard + duration:

```bash
uv run poc-remotion approve --id copilot-prompting-basics --stage storyboard
uv run poc-remotion approve --id copilot-prompting-basics --stage duration
```

- [ ] **Step 4: Script (user gate 3)**: `draft-script`; present full narration text; revise on request; user approves: `approve --stage script`. Then `claims`; any `unresolved` claims are shown and resolved (user decides: accept as opinion wording, or re-draft the line via `revise`).

- [ ] **Step 5: Narrate and export**: `narrate` then check the reported total is inside 4:30-6:00 (design success criterion); `export-srt`; `export` (default scale 1.0, 1080p). Open the bundle video for the user.

- [ ] **Step 6: Success criteria checklist** (design section 10): character present, no orbs; narration is the user-approved `bf_emma`; total duration in window; every claim in `claims.json` maps to the source document (`status == "supported"`); both gates were recorded before render; one `revise` cycle completed without losing other approved state; captions burned in and SRT exported; storyboard and script were drafted by the pipeline's model steps; a `draft-script`-produced project renders visible on-screen text (whole-branch B review carry-forward: the on_screen contract end to end). Record each criterion pass/fail in the session ledger; failures are defects to fix before declaring MVP 1 done.

- [ ] **Step 7: Commit** any plan-relevant fixes discovered during production as separate commits; the project directory itself is never committed.

---

## Definition of Done (Plan C)

- `uv run pytest tests/ -v` and `uv run ruff check src tests` clean; `cd remotion-starter && npm run lint` clean.
- `poc-remotion narrate/export-srt/revise/export` exist with the documented exit codes.
- A full local rehearsal (fixture project, FakeTTS replaced by the real adapter) narrates, exports SRT, revises one scene, re-narrates cheaply (cache), and exports a bundle.
- Video 1 produced through the runbook with all user gates passed and the design's success criteria checked off.
