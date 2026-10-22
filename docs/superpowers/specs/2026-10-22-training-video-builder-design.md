# Training Video Builder, MVP 1: Design

Date: 2026-10-22
Status: drafted for builder review
Source documents: `docs/Training_Video_Builder_PRD_v1.0.md` (product baseline), `docs/Copilot_Prompting_for_Beginners_Slide_Descriptions.md` (first video source).

## 1. Intent

Build a local tool, operated from OpenCode or a terminal, that turns a description document plus a short question-and-answer session into a finished, animated, narrated training video. The user stays in control: nothing is produced until they approve a storyboard with duration, and a script. MVP 1 delivers one video: a condensed, light-hearted animated version of the "Copilot Prompting for Beginners" workshop, about five minutes long, with a female synthetic voice.

## 2. Goals

- One polished video per project, reproducible from persisted project files.
- Conversational revision in OpenCode ("shorten scene 3") without rebuilding unchanged scenes or audio.
- Source-grounded narration: factual claims trace to the source document; nothing important invented silently.
- Exact brand compliance: the PRD palette and Pangram Sans only; no logos anywhere.
- Zero paid APIs; everything runs locally through LiteLLM and local tools.

## 3. Non-goals and anti-goals

- No courses, LMS packaging, custom browser editor, cloud TTS, or auto-publishing (PRD section 11).
- Anti-goals: approximate brand colours as substitutes; decorative "orbs"/floating-sphere artwork anywhere (explicit user rejection); fabricated logos; unapproved production runs; silent fact invention.

## 4. Decided, with owner

| Decision | Value | Owner |
|---|---|---|
| Entry points | Both: OpenCode commands/skills in chat, and a thin CLI. Both drive the same project files. | User |
| Build/runtime model | `litellm/local-qwen` (Qwen 3.5 35B local). User decision 2026-10-22, overriding the PRD's Flint references. All model calls stay behind LiteLLM, interfaces model-agnostic. | User |
| Visual style | Direction B: flat vector character ("the smart new colleague"), flat brand colour fields, kinetic typography. No sphere/orb decoration. | User |
| Narration | Fully local TTS, female voice, light/witty/cute tone. Candidate engine: Kokoro; final choice after a voice spike the user listens to and approves. No accent requirement; the user picks from shortlisted samples. | User + builder |
| Video 1 scope | Condensed highlights of the workshop, not slide-by-slide. Target 4:30 to 6:00. | User |
| Export | 1080p 16:9, 30 fps MP4, SRT subtitles. | Builder default, no objection raised |
| Fonts | Pangram Sans complete family already in `src/fonts/` (OTF/TTF/WOFF2). Stays out of Git until the user confirms licence. Brand config references the local path. | Builder call, flagged to user |
| Workflow shape | Python pipeline (uv package at repo root) owns project state, LLM calls, TTS and validation; the existing `remotion-starter/` Node package owns composition, Studio preview and rendering, invoked via npm scripts. Renaming the starter package is deferred. | Builder call |
| Approval gates | Storyboard + duration, then script, recorded in `projects/<id>/approvals.json`. Production blocked without them. | PRD |
| Video 1 content source | Storyboard and script are drafted by the pipeline's own model steps (`litellm/local-qwen`, verified serving on this machine) and approved through the gates. No hand-authored seed content. | User |
| Distribution | MVP 1 output is for personal preview. Font licence confirmation is deferred but becomes a blocking gate before any sharing. | User |
| Captions | Burned in with brand styling in every scene, plus SRT sidecar export. | Builder call |
| Music and sound effects | Deferred. MVP 1 is narration only, keeping the video licence-free. | Builder call |
| External research | Deferred, keeping schema hooks. Video 1 uses local Markdown only; the PRD's demo criteria never exercise research. | Builder call |

## 5. Architecture

```text
OpenCode chat (commands/skills)  or  CLI (uv run poc-remotion ...)
        |
        v
Python pipeline (repo root package)
  project state: projects/<video-id>/*.json (validated, versioned)
  LLM calls via LiteLLM (openai-compatible, litellm/local-qwen)
  TTS adapter -> scene/segment audio + timing source
  brand validation (tokens, fonts, contrast)
        |
        v (npm run / npx remotion, via subprocess)
remotion-starter/ (React + TypeScript)
  scene component library (typed scene schemas in, React out)
  deterministic composition from projects/<id>/ data
  Remotion Studio preview; remotion render -> MP4
```

- Project data layout follows PRD section 9 (`brief.json`, `sources.json`, `claims.json`, `storyboard.json`, `script.json`, `approvals.json`, `audio/`, `assets/`, `subtitles/`, `output/`, `manifest.json`).
- Typed data contracts: pydantic models in Python are the source of truth; a JSON Schema is generated from them; TypeScript scene components consume validated JSON. Schema drift is caught by tests.
- Scene identity: stable scene IDs; revision requests target scene IDs; unchanged scenes and audio are not regenerated.

## 6. Scene library for MVP 1

Each scene type is a React component plus a typed schema. For video 1:

1. `title`: opener with character entrance and kinetic title.
2. `newsGrid`: 2x2 cautionary cards (the "AI goes wrong" hook).
3. `framework`: G/C/S/E panels revealed in step with narration.
4. `beforeAfter`: vague prompt vs GCSE prompt, character reacts.
5. `quote`: full-bleed lime golden rule.
6. `analogy`: lorry-and-letter visual for model modes.
7. `cheatSheet`: summary panels.
8. `outro`: call to action and character wave.

Character component: flat vector shapes only, with expressions/poses (idle, point, shrug, cheer, oops) driven by props. No photographic or 3D assets. Software-demo and character-animation ambitions beyond this are deferred (PRD risks).

## 7. Video 1 outline (approx. 5:00)

| Scene | Content | Source slides |
|---|---|---|
| title | Better prompts, better results; meet the colleague | 1 |
| newsGrid | Two cautionary stories, checked-output lesson | 2 (condensed) |
| beforeAfter | "Write an email about the game launch" fails; GCSE rewrite wins | 3, 5 |
| framework | Goal, Context, Source, Expectations | 4 |
| quote | Golden rule: ask clarifying questions | 12 |
| analogy | Lorry vs letter: pick the light model first | 19-22 (condensed) |
| cheatSheet | GCSE + golden rule + check-before-use | 24 |
| outro | Try-this-today prompt; character waves | 25 |

Workshop mechanics (votes, exercises, live demos) are folded into narration, not re-enacted. Narration claims map to the slide-descriptions document in the claim register.

## 8. Pipeline and approvals

1. `init`: create `projects/<video-id>/` from schemas.
2. `ingest`: parse source document(s) (plain text/Markdown solid; PDF/DOCX/PPTX best-effort with recorded extraction limitations). For video 1 the source is Markdown.
3. `brief`: conversational discovery (audience, objectives, tone, duration feel) captured into `brief.json`. Resumable.
4. `storyboard`: model proposes objectives, duration, scene list; user approves storyboard + duration (gate 1).
5. `script`: narration + on-screen text with claim references; user approves (gate 2).
6. `narrate`: TTS per scene segment; caption timings from audio (engine timestamps if available, otherwise local forced alignment; decided during implementation with a measured comparison).
7. `assemble` + preview: scene data -> Remotion; user previews in Studio.
8. `revise`: targeted scene edits; re-run brand validation and claim recheck for touched scenes.
9. `export`: MP4 + SRT + script + storyboard + source register + manifest (model/tool versions, brand config version).

## 9. Quality

- pytest for schemas, brand validation, CLI flows and register logic; ruff clean.
- TypeScript: eslint + tsc (existing starter scripts).
- Deterministic composition: render output depends only on project files and pinned tool versions.
- Failure behaviour: clear errors for missing fonts, missing audio, failed render, unapproved gates.
- Repo hygiene: `.superpowers/`, `src/fonts/`, project audio/output stay out of Git; no secrets anywhere in artefacts.

## 10. Success criteria for MVP 1

PRD section 10 pass criteria, applied with these specifics: character present with no orb decoration; light/witty/cute female narration the user has approved from a voice sample; total duration within 4:30-6:00; every factual claim in `claims.json` maps to the slide-descriptions document; both approval gates recorded before any render; one conversational scene revision completed without losing other approved state; captions burned in, synchronised and exported as SRT; the storyboard and script drafted by the pipeline's own model steps, not hand-seeded.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Kokoro voice quality/latency unsuitable | Voice spike first; user approves sample; fallbacks: Piper, macOS `say` (development only) |
| Caption timing drift | Prefer engine-provided timestamps; otherwise forced alignment; verified in preview |
| Font licence unconfirmed | Fonts stay untracked; user confirms licence before any distribution beyond personal preview |
| Local render performance | Scene-level regeneration, low-res preview profile for iteration |
| Qwen tool-use reliability | Structured JSON outputs validated against schemas; deterministic Python for repeatable steps; model swappable |

## 12. Left to the builder

Exact schema fields, prompt wording, component APIs, TTS adapter interface details, alignment tooling choice, Studio workflow niceties, CLI ergonomics.
