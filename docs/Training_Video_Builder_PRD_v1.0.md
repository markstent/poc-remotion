# Training Video Builder
## Product Requirements Document (PRD) v1.0

**Project:** Latent Space Experimentation Lab / `poc-remotion`  
**Date:** 22 October 2026  
**Status:** Initial MVP product baseline  
**Owner:** Project user  
**Scope:** Generate one polished, source-grounded, branded training video per project.

## 1. Executive summary

Build a local-first, conversational training-video production workflow operated through **OpenCode**. A user describes a training requirement, optionally attaches materials and authorises research, answers a focused discovery interview, then approves a storyboard and script. The system uses **Flint via LiteLLM → Ollama** for planning and content generation, a local TTS engine for narration, and **Remotion** for compositing, live previews in Remotion Studio and MP4 rendering.

The first MVP creates **one polished training video**, not a whole course. Its design should allow later expansion into lessons and courses without requiring that functionality now. No corporate logos will be supplied or used. The visual identity is defined by an exact colour palette and **PP Pangram Sans** font files provided by the user.

## 2. Problem and outcomes

Producing professional training videos manually requires scripting, instructional design, visual design, voice recording, animation and editing. The MVP should reduce manual coordination while keeping an accountable human in control of factual accuracy and editorial approval.

**Desired outcomes:**
- Generate a coherent video covering explicitly agreed learning objectives.
- Make review and revision possible in ordinary language in OpenCode.
- Produce engaging mixed-media scenes while following the supplied brand rules.
- Keep factual claims attributable to documents or approved research.
- Work without mandatory paid AI or voice APIs.
- Retain intermediate artefacts so production is reproducible and local edits are targeted.

**Not an MVP goal:** authoring a complete multi-module course or an LMS package.

## 3. Agreed decisions

| Topic | Decision |
|---|---|
| Deliverable | One polished video per project |
| Production style | Hybrid: motion graphics, character sequences, software demonstrations, mixed scenes |
| AI / orchestration | OpenCode with project-local `litellm/local-flint`; LiteLLM routes to Ollama |
| Autonomy | Guided: storyboard and script must be approved before production |
| Narration | Fully local AI text-to-speech |
| Duration | AI recommends duration based on objectives; user approves |
| Inputs | Natural-language brief, supplied documents, optional explicitly authorised research |
| Reliability | Grounded creativity: source-based factual claims; illustrative fiction clearly identified |
| Reviews | OpenCode for requests/approvals, Remotion Studio for preview |
| Brand | Fixed colour palette and Pangram Sans, controlled creative layouts; no logos |
| Output | MP4 and supporting project, script, subtitles and source information |

## 4. Primary user journey

1. **Start** a project in OpenCode from a natural-language description.
2. **Discover:** ask only necessary questions about audience, baseline knowledge, outcomes, scope, delivery context and available source material; capture answers as a structured brief.
3. **Ingest:** parse supplied materials; optionally research externally only after permission. Create source identifiers and record provenance.
4. **Design:** propose learning objectives, video length, outline and scene-by-scene storyboard including visual mode and references. Ask for explicit approval of the storyboard **and proposed duration**.
5. **Script:** generate complete narration and on-screen text, with citations/claim references for review. Ask for explicit approval of the script.
6. **Produce:** choose appropriate local TTS engine and Remotion components; create or ingest character/graphic/demo assets as available; time scenes and captions to narration.
7. **Preview:** inspect the composition using Remotion Studio and request changes conversationally in OpenCode.
8. **Revise:** update only affected assets/scenes when practicable; warn and seek reapproval when a requested revision materially changes approved factual content.
9. **Export:** render finished MP4 and package script, subtitles, storyboard, sources and reproducibility metadata.

**Approval gate:** production must not run until the storyboard, proposed duration and script have explicit recorded approval. Approval state must be stored in project data, not inferred from conversation history alone.

## 5. Functional requirements

### FR-01 Project initiation and discovery (P0)
- Accept a natural-language training request.
- Ask a purposeful, non-repetitive discovery interview.
- Store a structured brief with audience, learning objectives, key messages, preferred style, constraints and known unknowns.
- Save progress so a session can resume.

### FR-02 Source ingestion and research (P0)
- Accept natural-language context and supplied PDF, PPTX, DOCX and plain text/Markdown documents where parsers can extract useful text.
- Track source identity, title, file/page/slide location where available, and extraction limitations.
- External research is opt-in. Maintain page titles, URLs and retrieval dates for researched claims.
- Treat provided company materials as primary sources by default; flag contradictions rather than silently resolving them.
- Do not describe a parser's output as complete if diagrams, screenshots or embedded visual content were not reliably captured.

### FR-03 Grounded content generation (P0)
- Associate important factual narration claims with one or more sources in a claim/source register.
- Flag missing support, ambiguity, stale claims or source conflicts for user resolution.
- Permit original characters, analogies and workplace scenarios labelled internally as illustrative, not factual evidence.
- Avoid inventing facts about products, organisations or processes.

### FR-04 Instructional outline and duration (P0)
- Propose measurable learning objectives and an appropriate duration, with short rationale.
- Break the video into scenes with a purpose, estimated seconds, narrative summary, planned visuals and source links.
- Select among motion graphics, characters, software demonstrations and combined styles by instructional purpose rather than fixed proportions.
- Record explicit storyboard and duration approval.

### FR-05 Script authoring and approval (P0)
- Write scene-level narration and on-screen text, including pronunciation notes where necessary.
- Show the full script in an easily reviewable format.
- Track approval status and revisions independently of the storyboard.
- Block final production until the script is approved.

### FR-06 Brand system (P0)
- Load colours and font definitions from versioned brand configuration.
- Enforce exact approved hex tokens; never introduce approximate branded colours as substitutes.
- Provide reusable typography, backgrounds, accent shapes, lower-thirds, scene openers and transitions.
- Do not require, fabricate, place or reserve space for company logos.
- Allow layout, animation and scene composition variation within configured brand and accessibility rules.
- Validate technical rules automatically; leave aesthetic brand judgement to preview approval.

### FR-07 Local narration (P0)
- Generate voice audio entirely on-device using a replaceable local TTS adapter.
- Allow a project-level voice/preset choice without changing scripts.
- Generate audio at scene or segment granularity for local regeneration.
- Derive caption timings from actual audio; choose a timing/alignment method and evaluate it during implementation.
- Provide an audible review stage as part of the video preview.

### FR-08 Video generation (P0)
- Build scenes using Remotion/React/TypeScript.
- Support at least a practical motion-graphics scene and a combined text/visual scene in the end-to-end acceptance demo.
- Provide architectural paths for animated characters and software demos; quality and extent depend on validated local asset/capture tools.
- Assemble narration, visuals, captions and timing deterministically from structured scene data.
- Preserve predictable scene boundaries and identify which files each scene depends on.

### FR-09 Review and revision (P0)
- Use OpenCode for conversational revision requests and explicit approvals.
- Use Remotion Studio for browser preview/scrubbing; no custom browser editing application in MVP.
- Make scene identifiers visible and stable for requests such as “shorten scene 3”.
- Avoid unnecessary regeneration of unchanged scenes/audio.
- Recheck claims and brand validation after changes.

### FR-10 Export and provenance (P0)
- Render a playable MP4, with agreed target resolution/frame rate as a configurable export profile.
- Export final script, scene storyboard, subtitles (SRT or equivalent) and source register.
- Save model/tool version identifiers, input references, brand config version and generation settings.
- Do not place secrets or private LiteLLM tokens in generated artefacts or the Git repository.

### FR-11 Reliability and recovery (P1)
- Validate project JSON against schemas.
- Fail clearly on missing fonts, inaccessible sources, absent TTS tools or failed renders.
- Resume from persisted project state and avoid overwriting previous approved versions without warning.
- Run tests and lint checks for relevant generators and project components.

## 6. Non-functional requirements

- **Local first:** inference, narration, asset composition and rendering must function with locally installed tools. External research requires explicit permission and network access.
- **No mandatory paid API calls:** zero paid API dependency is the target, not a claim that computation/time/electricity is free.
- **Model independent:** Flint is the initial model; prompt/task interfaces must not assume Flint is the only provider.
- **Auditable:** retain approvals, source links and asset provenance.
- **Security:** keep confidential input files local unless the user explicitly authorises an external research/upload step; use existing 1Password and LiteLLM project credentials, without putting secrets in project data.
- **Maintainable:** small scene library, typed data contracts and replaceable narration/media adapters; avoid building a new full editor.
- **Accessibility:** captions, adequate contrast and readable typography, including safe text areas.
- **Quality:** render without clipped text, missing fonts/assets, overlapping elements, incomplete captions, broken audio or abrupt unintended cuts.

## 7. Brand specification (authoritative supplied values)

### Palette

| Role | Token | HEX |
|---|---|---|
| Primary | turquoise | `#27E2CC` |
| Primary | darkTeal | `#1D4757` |
| Secondary | lime | `#C4F600` |
| Secondary | paleBlue | `#CCFFFF` |
| Tertiary | white | `#FFFFFF` |
| Tertiary | black | `#000000` |
| Turquoise tint 75% | turquoise75 | `#5DE9D9` |
| Turquoise tint 50% | turquoise50 | `#93F0E5` |
| Turquoise tint 25% | turquoise25 | `#C9F8F2` |
| Dark teal tint 75% | darkTeal75 | `#496E7A` |
| Dark teal tint 50% | darkTeal50 | `#829BA3` |
| Dark teal tint 25% | darkTeal25 | `#C3CFD1` |

Lime tint hex values were not supplied. They are **not** brand-approved and must not be invented or added as official tokens.

**Usage:** prioritise turquoise/dark teal; use lime for emphasis; pale blue/white support backgrounds. Check contrast for each foreground/background combination, including small captions.

### Typography

Use the supplied **PP Pangram Sans** font collection from `pangram.tst.zip`, provided licence terms permit use in video outputs. WOFF2 is the preferred web/Remotion loading format. Proposed hierarchy: Extrabold for main titles, Bold for section titles, Regular for body, Semibold for captions and Condensed Bold for occasional animated statements. These are proposed usage defaults, not user-supplied mandatory style rules.

### No-logo rule

Do not request, invent, reconstruct or insert corporate logos, marks or fabricated wordmarks. Text, colour, shape, animation and typography alone form the video's identity.

## 8. Proposed technical architecture (subject to implementation validation)

```text
OpenCode (conversation, human approvals, task control)
    |
    v
Project workflow / local CLI and typed project files
    |--- Flint via LiteLLM -> Ollama (discovery, scripts, scene plans)
    |--- Local source extraction / permitted research
    |--- Source and claim register
    |--- Brand rules and validation
    |--- Local TTS adapter -> scene audio and word/segment timings
    |--- Remotion/React scene library and optional media/capture adapters
    |          |
    |          +--> Remotion Studio (browser preview)
    |          +--> Remotion render (final MP4)
    |
    +--> Scripts, captions, storyboard, source register, metadata
```

**Important existing state:** `~/Documents/Projects/poc-remotion/remotion-starter/` was generated using Remotion's blank starter. Its nested package and integration status were not verified in the handover. The established `oc` launcher uses OpenCode `--standalone` for project-key isolation. Project OpenCode configuration should point to `litellm/local-flint`; global model default should remain `litellm/local-qwen`. Do not re-run POC bootstrap or change functioning global credential infrastructure.

**Candidate local TTS implementations:** Kokoro, Qwen3-TTS and Chatterbox; benchmark compatibility, clarity, pronunciation and generation speed before committing to one. Character animation and realistic software demo capture require separate feasibility checks and should not be promised as solved by the language model alone.

## 9. Proposed logical project structure (not yet implemented)

```text
poc-remotion/
  brand/
    brand.json
    fonts/                      # licensed files, storage policy to confirm
  remotion-starter/             # existing scaffold; inspect before restructuring
  projects/
    <video-id>/
      brief.json
      sources.json
      claims.json
      storyboard.json
      script.json
      approvals.json
      audio/
      assets/
      subtitles/
      output/
      manifest.json
  docs/
    PRD.md
```

This structure is conceptual. Fit it around the existing repository rather than blindly creating duplicate scaffolds. Keep confidential inputs and binary outputs out of Git where appropriate.

## 10. Minimum acceptable end-to-end demonstration

**Scenario:** one small, internally approved training topic with a short supporting document. The user initiates the request in OpenCode, answers discovery questions, reviews a suggested duration, approves a storyboard, approves a script, and the project creates a locally narrated, branded Remotion video. The user inspects it in Remotion Studio, asks for one scene-specific change and successfully exports MP4, subtitles, script and source register.

**Pass criteria:**
1. All supplied hex colours and selected Pangram fonts are used correctly; no logo or imaginary brand mark appears.
2. The video visibly uses at least two visual treatments, including animated graphics; optional character/demo segments may be used once validated.
3. The factual statements in narration are mapped to source references or explicitly marked as unresolved before approval.
4. No production starts before recorded storyboard/duration and script approvals.
5. Narration and subtitles are generated locally and are reasonably synchronised.
6. Preview and exported MP4 play cleanly, without missing assets, text clipping or unintended silence.
7. A natural-language edit to one scene can be made and previewed without losing other approved project state.
8. No paid API is required for the tested path and no credentials are checked into Git.

## 11. MVP exclusions

- Complete multi-lesson course generation.
- LMS/SCORM packaging, learner progress and assessments platform.
- A custom drag-and-drop browser editor.
- Mandatory cloud TTS, speech or video services.
- Fully automatic publication to external video hosting systems.
- Automatically fabricated corporate identity assets.
- Guaranteed generative video or photorealistic character animation.
- Claims of perfect factual validation without human review.

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Flint performance is slow or tool use is unreliable | Benchmark representative tasks; keep model interface swappable; use deterministic scripts for repeatable tasks |
| Local TTS sounds unnatural | Compare short voice samples; retain scene-level regeneration and alternate local adapters |
| Character or software demonstration media is difficult | Start from reusable vector character rigs and user-provided/captured screencasts; broaden only after feasible tests |
| Generated claims are unsupported | Claim/source register, mandatory approval, contradiction flags |
| Documents contain important graphics not captured by parsers | Surface extraction limitations, request inspection where needed |
| Brand adherence is inconsistent | Central design tokens, reusable components and pre-render checks |
| Large renders are slow or fail | Build low-cost previews, use incremental scene updates, record diagnostic failures |
| Local fonts have usage restrictions | Confirm licence for embedding and rendered video distribution; do not redistribute font archive casually |

## 13. Implementation milestones

**M0: Inspect and baseline.** Confirm the Remotion starter package, current Git state, project OpenCode config, font variants and render tooling. Run a minimal starter preview/render without changing global infrastructure.

**M1: Structured workflow.** Define schemas for brief, sources, storyboard, scripts and approval state; implement a small OpenCode-driven project workflow.

**M2: Brand and rendering.** Install local brand tokens and appropriate font assets; build a small reusable scene library; create a static/animated branded test composition.

**M3: Narration and subtitles.** Select and validate local TTS; generate segmented audio and reliable caption alignment; combine in Remotion.

**M4: Content intelligence.** Add source extraction, optional research permission, claim tracking, discovery and approval gates; integrate with Flint.

**M5: End-to-end video.** Produce the first complete training video, revise one scene, render MP4 and package supporting deliverables.

**M6: Quality hardening.** Add tests, failure/recovery scenarios, provenance and performance benchmarks; evaluate character and demo components.

These are sequencing proposals rather than committed dates or completed work.

## 14. Open decisions for technical design

1. Exact local TTS engine/voice and timing/alignment tool.
2. Preferred export profile (for example, 1080p landscape and frame rate) and caption styling.
3. Font licensing and whether binaries should live in a local ignored folder rather than Git.
4. How software demonstrations are acquired: user-uploaded recordings, guided capture or a more automated browser capture approach.
5. Character asset approach: simple 2D rigs, SVG components or imported assets.
6. Depth of PDF/PPTX/DOCX visual extraction in the first demonstration.
7. Whether the workflow is implemented as OpenCode commands/skills, a thin CLI, or a combination.
8. How research is authorised and tracked in an offline-by-default project.

## 15. Definition of done for MVP 1

MVP 1 is complete when a user can go from a training brief to an approved, locally narrated, source-grounded, visibly branded video using OpenCode and Remotion Studio, make at least one conversational scene edit, and export a playable MP4 plus the agreed supporting files, with no mandatory paid-generation API and no undisclosed use of external sources.

---

**Status note:** This document records agreed product decisions and proposed architecture. It does not claim the application has been built, that Flint has been benchmarked for video-planning tasks, or that the TTS, character and demo pipelines have been validated.
