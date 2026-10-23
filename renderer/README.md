# tvb-renderer

The Training Video Builder video renderer: a Rust crate built on
[fframes](https://fframes.org) (SVG scenes, Skia/Metal rendering, ffmpeg
encoding). It replaced the previous Remotion composition as the renderer of
record and produces the same 8-scene layout, spring timings and brand tokens.

## How it works

All project data is embedded at compile time:

- `data/storyboard.json` and `data/narration.json`: the current project's
  storyboard and narration documents (gitignored, staged per render).
- `media/*.wav`: the narration audio referenced by narration.json, staged
  flat by bare file name (gitignored, staged per render and removed after).
- `media/*.ttf`: the PP Pangram Sans weights (Bold, Regular, Semibold,
  Extrabold), copied from the gitignored `src/fonts/` directory by the
  render step. The font licence is unconfirmed, so the TTFs are never
  committed.

The Python pipeline (`poc_remotion.render`) owns gating and staging: it
validates the project's approval gates, stages the files above, runs
`cargo run --release -- render` and moves `out.mp4` to the project's
`output/video.mp4`. You normally do not run cargo by hand.

## Manual use

```sh
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$PATH"
cargo run --release -- render    # full render to out.mp4 (1920x1080@30)
cargo run --release -- frame --frame 1800 --output frame.png
cargo run --release -- --help    # all fframes CLI subcommands
```

Staging files must exist or text/audio will be missing: run a pipeline
`render` once (or copy them from a project by hand) before manual use.

## Notes

- Narration `file` fields are project-relative `audio/<name>` paths; the
  renderer strips the prefix and matches the staged bare file names.
- Output is fixed 1920x1080 at 30 fps; there is no scale option.
- `target/` is gitignored; the first build compiles the fframes dependency
  tree and takes a few minutes, later renders are incremental.
