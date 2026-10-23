# Decision: fframes replaces Remotion as the renderer

Date: 2026-10-23

## Decision

The Training Video Builder renders video exclusively with the Rust crate in
`renderer/`, built on fframes 1.3.0 (SVG scenes, Skia/Metal, ffmpeg h264+aac).
The previous Remotion composition (`remotion-starter/`) was removed. The
design spec of 2026-10-22 remains the record of the pipeline, gates and data
model; only the rendering backend changed.

## Why

A side-by-side experiment (`tvb-fframes`, outside the repo) ported all 8
scenes to fframes and produced a frame-accurate match of the approved
video 1 in about 9 seconds of render time, versus several minutes for the
Remotion render. The owner chose fframes as the single renderer.

## Mechanics

- The Python bridge (`poc_remotion.render`) still owns gating. It stages the
  current project's storyboard.json, narration.json and referenced WAVs into
  `renderer/data/` and `renderer/media/`, copies the brand TTFs from the
  gitignored `src/fonts/`, runs `cargo run --release -- render`, and moves
  `out.mp4` to `<project>/output/video.mp4`. Staged data and audio are
  removed after each render so one project never leaks into another.
- All media is embedded at compile time (include_str!/include_media_dir), so
  each render is a (fast, incremental) rebuild.
- The `--scale` CLI flag is gone: output is fixed 1920x1080 at 30 fps.
- Narration `file` fields stay `audio/<name>`; the renderer strips the prefix
  and matches staged bare file names.

## Consequences

- Node and the React toolchain are no longer required to build video.
- Font and audio files stay out of Git; a fresh clone must supply
  `src/fonts/` before rendering.
- Visual changes now happen in Rust (`renderer/src/lib.rs`), mirroring the
  approved Remotion composition scene by scene.
