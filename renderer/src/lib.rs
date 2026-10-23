//! Trainer Video renderer: fframes port of the original Remotion composition.
//!
//! The Python pipeline (storyboard.json + narration.json + per-scene WAVs) is
//! unchanged: it stages the current project's data into `data/` and the
//! referenced audio into `media/` before each build, so the crate renders any
//! pipeline project. Scene visuals, spring timings, brand tokens and the
//! audio timeline are the renderer of record for the Training Video Builder.
use fframes::{
    AnimateRuntimeInput, AudioMap, BreakLinesOpts, Duration, FFramesContext, FontQuery, Frame,
    Scene, Scenes, Svgr, TextAlign, Transform, Video,
    animation::{AnimationRuntime, Easing},
    include_media_dir,
};
use serde::Deserialize;
use std::sync::LazyLock;

// Every file of `media/` is embedded into the binary (fonts + the 8 WAVs).
include_media_dir!(pub struct TrainerMedia, "media");

pub const WIDTH: usize = 1920;
pub const HEIGHT: usize = 1080;

// Brand tokens (projects/.../brand.json).
const TURQUOISE: &str = "#27E2CC";
const DARK_TEAL: &str = "#1D4757";
const LIME: &str = "#C4F600";
const PALE_BLUE: &str = "#CCFFFF";
const WHITE: &str = "#FFFFFF";
const FONT: &str = "PP Pangram Sans";
const BOLD: u16 = 700;
const REGULAR: u16 = 400;

const FPS: f32 = 30.0;

/// Remotion SPRING_CONFIG { damping: 14, stiffness: 110, mass: 0.7 }.
static SPRING: LazyLock<AnimationRuntime> = LazyLock::new(|| {
    AnimationRuntime::new(3.5, &Easing::Spring { mass: 0.7, stiffness: 110.0, damping: 14.0 })
});
/// Remotion character-in spring { damping: 12, stiffness: 70, mass: 0.9 }.
static SPRING_SOFT: LazyLock<AnimationRuntime> = LazyLock::new(|| {
    AnimationRuntime::new(4.0, &Easing::Spring { mass: 0.9, stiffness: 70.0, damping: 12.0 })
});
/// Remotion Colleague settle spring { damping: 10, stiffness: 90, mass: 0.6 }.
static SETTLE: LazyLock<AnimationRuntime> = LazyLock::new(|| {
    AnimationRuntime::new(3.0, &Easing::Spring { mass: 0.6, stiffness: 90.0, damping: 10.0 })
});

#[derive(Deserialize)]
struct StoryboardDoc {
    scenes: Vec<StoryboardScene>,
}

#[derive(Deserialize)]
struct StoryboardScene {
    id: String,
    kind: String,
    seconds: f32,
    on_screen: Vec<String>,
}

#[derive(Deserialize)]
struct NarrationDoc {
    lines: Vec<NarrationLine>,
}

#[derive(Deserialize)]
struct NarrationLine {
    scene_id: String,
    #[allow(dead_code)]
    text: String,
    start_seconds: f32,
    #[allow(dead_code)]
    end_seconds: f32,
    file: String,
}

const STORYBOARD_JSON: &str = include_str!("../data/storyboard.json");
const NARRATION_JSON: &str = include_str!("../data/narration.json");

/// 0 -> 1 spring, starting `delay_frames` into the scene.
fn spring_in(frame: &Frame, runtime: &'static AnimationRuntime, delay_frames: f32) -> f32 {
    frame.animate_runtime(AnimateRuntimeInput {
        on_second: delay_frames / FPS,
        from: 0.0,
        to: 1.0,
        animation_runtime: runtime,
    })
}

/// `px` -> 0 spring offset, matching Remotion's `(1 - spring) * px` rise.
fn rise(frame: &Frame, runtime: &'static AnimationRuntime, delay_frames: f32, px: f32) -> f32 {
    let p = spring_in(frame, runtime, delay_frames);
    (1.0 - p) * px
}

fn wrap_count<'a>(
    frame: &mut Frame,
    ctx: &FFramesContext<'a, '_>,
    text: &'a str,
    size: usize,
    weight: u16,
    width: f32,
) -> usize {
    let font = FontQuery { family: FONT, size, weight, ..Default::default() };
    text.split('\n')
        .map(|hard| {
            let w = frame.text_width(ctx, font, hard).unwrap_or(0) as f32;
            (w / width).ceil().max(1.0) as usize
        })
        .sum()
}

/// A wrapped multi-line text block. `x` is the LEFT edge of the content box;
/// `align` positions each wrapped line inside it. `y` is the first line's
/// BASELINE (svg semantics): for a block whose top should be `top`, pass
/// `top + 0.96 * size` (PP Pangram Sans ascent is 0.96 em).
fn para<'a>(
    frame: &mut Frame,
    ctx: &FFramesContext<'a, '_>,
    text: &str,
    size: usize,
    weight: u16,
    fill: &'a str,
    x: f32,
    y: f32,
    width: f32,
    line_height: f32,
    align: TextAlign,
) -> Svgr<'a> {
    let font = FontQuery { family: FONT, size, weight, ..Default::default() };
    frame
        .text_break_lines(ctx, text, BreakLinesOpts {
            font,
            width: width as usize,
            x: x as usize,
            y: y as usize,
            align,
            fill,
            line_height,
            ..Default::default()
        })
        .unwrap_or_default()
}

/// First-line baseline for a block whose top edge is `top`.
fn baseline(top: f32, size: usize) -> f32 {
    top + 0.96 * size as f32
}

pub struct TrainerVideo<'a> {
    #[allow(dead_code)]
    media: &'a TrainerMedia,
    scenes: Vec<KindScene>,
    audio: Vec<(String, f32)>,
}

impl<'a> TrainerVideo<'a> {
    pub fn new(media: &'a TrainerMedia) -> Self {
        let sb: StoryboardDoc = serde_json::from_str(STORYBOARD_JSON).expect("storyboard.json");
        let n: NarrationDoc = serde_json::from_str(NARRATION_JSON).expect("narration.json");
        // Narration file fields are project-relative "audio/<name>"; the WAVs
        // are staged flat into media/, so only the bare name is needed.
        let audio: Vec<(String, f32)> = n
            .lines
            .iter()
            .map(|l| {
                let name = l
                    .file
                    .strip_prefix("audio/")
                    .unwrap_or(l.file.as_str());
                (name.to_owned(), l.start_seconds)
            })
            .collect();
        let mut scenes: Vec<KindScene> = sb
            .scenes
            .into_iter()
            .map(|s| KindScene {
                kind: s.kind,
                on_screen: s.on_screen,
                seconds: s.seconds,
                is_last: false,
            })
            .collect();
        if let Some(last) = scenes.last_mut() {
            // Remotion adds a 0.5 s trailing pad after the final scene.
            last.is_last = true;
        }
        Self { media, scenes, audio }
    }
}

impl std::fmt::Debug for TrainerVideo<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TrainerVideo").finish()
    }
}

impl Video for TrainerVideo<'_> {
    const FPS: usize = 30;
    const WIDTH: usize = WIDTH;
    const HEIGHT: usize = HEIGHT;
    const BACKGROUND_COLOR: fframes::Color = fframes::Color::WHITE;

    fn duration(&self) -> Duration<'_> {
        Duration::Auto
    }

    fn audio(&self) -> AudioMap<'_> {
        use fframes::{AudioTimestamp::*, AudioTrack};
        AudioMap::from(
            self.audio
                .iter()
                .map(|(file, start)| {
                    AudioTrack::new(file.as_str(), Second(*start)..Eof).voice()
                })
                .collect::<Vec<_>>(),
        )
    }

    fn define_scenes(&self) -> Scenes<'_> {
        Scenes::from(self.scenes.iter().map(|s| s as &dyn Scene).collect::<Vec<_>>())
    }

    fn render_frame<'a>(&'a self, frame: Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        fframes::svgr!(
            <svg xmlns="http://www.w3.org/2000/svg" width={WIDTH} height={HEIGHT} viewBox="0 0 1920 1080">
                {ctx.render_scenes(&frame)}
            </svg>
        )
    }
}

#[derive(Debug)]
struct KindScene {
    kind: String,
    on_screen: Vec<String>,
    seconds: f32,
    is_last: bool,
}

impl Scene for KindScene {
    fn duration(&self) -> Duration<'_> {
        Duration::Seconds(self.seconds + if self.is_last { 0.5 } else { 0.0 })
    }

    fn render_frame<'a>(&'a self, mut frame: Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let duration_frames = self.seconds * FPS;
        let bg = match self.kind.as_str() {
            "title" => PALE_BLUE,
            "quote" | "analogy" => LIME,
            _ => DARK_TEAL,
        };
        let body = match self.kind.as_str() {
            "title" => self.title_scene(&mut frame, ctx),
            "quote" => self.quote_scene(&mut frame, ctx),
            "framework" => self.framework_scene(&mut frame, ctx),
            "beforeAfter" => self.before_after_scene(&mut frame, ctx, duration_frames),
            "newsGrid" => self.news_grid_scene(&mut frame, ctx, duration_frames),
            "analogy" => self.analogy_scene(&mut frame, ctx, duration_frames),
            "cheatSheet" => self.cheat_sheet_scene(&mut frame, ctx, duration_frames),
            "outro" => self.outro_scene(&mut frame, ctx, duration_frames),
            _ => Svgr::empty(),
        };
        fframes::svgr!(
            <g font-family={FONT}>
                <rect width="1920" height="1080" fill={bg} />
                {body}
            </g>
        )
    }
}

/// The flat teal colleague character. Drawn in a 200x248 box scaled to `size`.
fn colleague<'a>(pose: &str, x: f32, y: f32, size: f32, bob: f32, light: bool) -> Svgr<'a> {
    // Dark scenes need a pale body to be visible at all (the original drew a
    // darkTeal character on darkTeal backgrounds); light scenes keep the
    // classic darkTeal body with white eyes.
    let (body, eye) = if light { (PALE_BLUE, DARK_TEAL) } else { (DARK_TEAL, WHITE) };
    let s = size / 248.0;
    let (left, right) = match pose {
        "oops" => ("58,138 50,196", "142,138 150,196"),
        "cheer" => ("58,138 36,90", "142,138 164,90"),
        "point" => ("58,138 42,193", "142,138 186,92"),
        "shrug" => ("58,140 30,158 38,124", "142,140 170,158 162,124"),
        // idle
        _ => ("58,138 40,193", "142,138 160,193"),
    };
    let mouth: Svgr = if pose == "oops" {
        fframes::svgr!(<circle cx="100" cy="92" r="9" fill={LIME} />)
    } else {
        fframes::svgr!(
            <path d="M 78 82 Q 100 102 122 82" stroke={LIME} stroke-width="7" stroke-linecap="round" fill="none" />
        )
    };
    let scale_move = format!("translate({x:.2} {y:.2}) scale({s:.5}) translate(0 {bob:.3})");
    fframes::svgr!(
        <g transform={scale_move}>
            <rect x="54" y="110" width="92" height="132" rx="30" fill={body} />
            <circle cx="100" cy="68" r="46" fill={body} />
            <polyline points={left} stroke={body} stroke-width="15" stroke-linecap="round" stroke-linejoin="round" fill="none" />
            <polyline points={right} stroke={body} stroke-width="15" stroke-linecap="round" stroke-linejoin="round" fill="none" />
            <g fill={eye}>
                <circle cx="84" cy="58" r="7" />
                <circle cx="116" cy="58" r="7" />
            </g>
            {mouth}
        </g>
    )
}

impl KindScene {
    fn title_scene<'a>(&'a self, frame: &mut Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let line1 = self.on_screen.first().map(String::as_str).unwrap_or("");
        let line2 = self.on_screen.get(1).map(String::as_str).unwrap_or("");
        let l1 = spring_in(frame, &SPRING, 2.0);
        let l2 = spring_in(frame, &SPRING, 10.0);
        let bar = spring_in(frame, &SPRING, 20.0);
        let chin = spring_in(frame, &SPRING_SOFT, 4.0);
        let bob = (frame.seconds() * 3.6).sin() * 4.0 * chin;
        let char_x = 1920.0 - 440.0 * 0.92 + (1.0 - chin) * (1920.0 + 440.0 - (1920.0 - 440.0 * 0.92));
        // Remotion stacks two wrapped blocks (lineHeight 1.05) above a 34px gap,
        // a 22px lime bar, all centred vertically.
        let advance = 1.05 * 108.0;
        let lines1 = wrap_count(frame, ctx, line1, 108, BOLD, 1075.2) as f32;
        let lines2 = wrap_count(frame, ctx, line2, 108, BOLD, 1075.2) as f32;
        let block_h = (lines1 + lines2) * advance + 34.0 + 22.0;
        let top = (1080.0 - block_h) / 2.0;
        let text1 = para(frame, ctx, line1, 108, BOLD, DARK_TEAL, 153.6, baseline(top, 108), 1075.2, 1.05, TextAlign::Left);
        let text2 = para(frame, ctx, line2, 108, BOLD, DARK_TEAL, 153.6, baseline(top, 108) + lines1 * advance, 1075.2, 1.05, TextAlign::Left);
        let bar_y = top + (lines1 + lines2) * advance + 34.0;
        let bar_w = 560.0 * bar;
        let char_y = 1080.0 - 108.0 - 440.0;
        let mate = colleague("idle", char_x, char_y, 440.0, bob, false);
        fframes::svgr!(
            <g>
                <g opacity={l1} transform={Transform::translate(0, rise(frame, &SPRING, 2.0, 110.0))}>{text1}</g>
                <g opacity={l2} transform={Transform::translate(0, rise(frame, &SPRING, 10.0, 110.0))}>{text2}</g>
                <rect x="153.6" y={bar_y} width={bar_w} height="22" fill={LIME} />
                {mate}
            </g>
        )
    }

    fn quote_scene<'a>(&'a self, frame: &mut Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let line = self.on_screen.first().map(String::as_str).unwrap_or("");
        let words = line.split_whitespace().count();
        let size = if words <= 8 { 132 } else if words <= 12 { 108 } else { 88 };
        let line_in = spring_in(frame, &SPRING, 2.0);
        let char_in = spring_in(frame, &SPRING, 8.0);
        let bubble_in = spring_in(frame, &SPRING, 14.0);
        let bubble_scale = 0.6 + 0.4 * bubble_in;
        let text = para(frame, ctx, line, size, BOLD, DARK_TEAL, 192.0, baseline(237.6, size), 1536.0, 1.05, TextAlign::Center);
        let bubble_text = "What's missing?";
        let font = FontQuery { family: FONT, size: 60, weight: BOLD, ..Default::default() };
        let bw = frame.text_width(ctx, font, bubble_text).unwrap_or(500) as f32 + 112.0;
        // Tail sits 99px from the bubble's left edge, as in the Remotion layout,
        // and points at the colleague standing to the bubble's lower left.
        let tail_cx = -bw / 2.0 + 99.0;
        let mate = colleague("idle", 420.0, 560.0 + (1.0 - char_in) * 60.0, 300.0, 0.0, false);
        fframes::svgr!(
            <g>
                <g opacity={line_in} transform={Transform::translate(0, rise(frame, &SPRING, 2.0, 60.0))}>{text}</g>
                <g opacity={char_in}>{mate}</g>
                <g opacity={bubble_in} transform={format!("translate(960 691) scale({bubble_scale:.4})")}>
                    <rect x={-bw / 2.0} y="0" width={bw} height="128" rx="44" fill={WHITE} />
                    <text x="0" y="82" text-anchor="middle" font-family={FONT} font-weight={BOLD} font-size="60" fill={DARK_TEAL}>{bubble_text}</text>
                    <rect x={tail_cx - 20.0} y="104" width="40" height="40" rx="8" fill={WHITE} transform={format!("rotate(45 {tail_cx:.2} 124)")} />
                </g>
            </g>
        )
    }

    fn framework_scene<'a>(&'a self, frame: &mut Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let stagger = self.seconds / 5.0 * FPS;
        let colors = [TURQUOISE, PALE_BLUE, PALE_BLUE, LIME];
        let letters = ["G", "C", "S", "E"];
        let panels: Vec<Svgr> = (0..4)
            .map(|i| {
                let p = spring_in(frame, &SPRING, stagger * i as f32);
                let x = 238.2 + i as f32 * (326.4 + 46.0);
                let y = 259.2 + (1.0 - p) * 70.0;
                let letter = letters[i];
                let caption = self.on_screen.get(i).map(String::as_str).unwrap_or("");
                let cap = if caption.is_empty() {
                    Svgr::empty()
                } else {
                    para(frame, ctx, caption, 34, REGULAR, DARK_TEAL, x + 24.2, baseline(y + 320.0, 34), 278.0, 1.2, TextAlign::Center)
                };
                fframes::svgr!(
                    <g opacity={p}>
                        <rect x={x} y={y} width="326.4" height="561.6" rx="48" fill={colors[i]} />
                        <text x={x + 163.2} y={y + 240.0} text-anchor="middle" font-family={FONT} font-weight={BOLD} font-size="190" fill={DARK_TEAL}>{letter}</text>
                        {cap}
                    </g>
                )
            })
            .collect();
        fframes::svgr!(<g>{panels}</g>)
    }

    fn before_after_scene<'a>(
        &'a self,
        frame: &mut Frame,
        ctx: &FFramesContext<'a, '_>,
        duration_frames: f32,
    ) -> Svgr<'a> {
        let char_in = spring_in(frame, &SPRING, duration_frames * 0.02);
        let before_in = spring_in(frame, &SPRING, duration_frames * 0.05);
        let after_in = spring_in(frame, &SPRING, duration_frames * 0.2);
        let panel_y = 172.8;
        let panel_h = 734.4;
        let before_text = self.on_screen.first().map(String::as_str).unwrap_or("");
        let after_text = self.on_screen.get(1).map(String::as_str).unwrap_or("");
        let bt = para(frame, ctx, before_text, 36, REGULAR, DARK_TEAL, 612.0, baseline(panel_y + 160.0, 36), 384.0, 1.3, TextAlign::Center);
        let at = para(frame, ctx, after_text, 40, BOLD, DARK_TEAL, 1130.3, baseline(panel_y + 160.0, 40), 653.0, 1.3, TextAlign::Center);
        let mate = colleague("oops", 98.0, 280.8 + (1.0 - char_in) * 60.0, 518.4, 0.0, true);
        fframes::svgr!(
            <g>
                {mate}
                <g opacity={before_in} transform={Transform::translate(0, rise(frame, &SPRING, duration_frames * 0.05, 70.0))}>
                    <rect x="573.6" y={panel_y} width="460.8" height={panel_h} rx="40" fill={PALE_BLUE} />
                    <text x="804" y={panel_y + 80.0} text-anchor="middle" font-family={FONT} font-weight={BOLD} font-size="26" letter-spacing="6" fill={DARK_TEAL} opacity="0.6">"BEFORE"</text>
                    {bt}
                </g>
                <g opacity={after_in} transform={Transform::translate(0, rise(frame, &SPRING, duration_frames * 0.2, 70.0))}>
                    <rect x="1092" y={panel_y} width="729.6" height={panel_h} rx="40" fill={WHITE} />
                    <text x="1456.8" y={panel_y + 80.0} text-anchor="middle" font-family={FONT} font-weight={BOLD} font-size="26" letter-spacing="6" fill={DARK_TEAL} opacity="0.6">"AFTER"</text>
                    {at}
                </g>
            </g>
        )
    }

    fn news_grid_scene<'a>(
        &'a self,
        frame: &mut Frame,
        ctx: &FFramesContext<'a, '_>,
        duration_frames: f32,
    ) -> Svgr<'a> {
        // Uniform 2x2 cards: every card fills its 806.4x388.8 cell and the
        // text block is centred vertically inside it, so all four read as
        // one consistent grid instead of text-hugging pills.
        let cards: Vec<Svgr> = (0..4)
            .map(|i| {
                let p = spring_in(frame, &SPRING, duration_frames * i as f32 / 5.0);
                let cell_x = 129.6 + (i % 2) as f32 * (806.4 + 48.0);
                let cell_y = 129.6 + (i / 2) as f32 * (388.8 + 43.2);
                let text = self.on_screen.get(i).map(String::as_str).unwrap_or("");
                let lines = wrap_count(frame, ctx, text, 38, REGULAR, 707.6) as f32;
                let content_h = lines * 47.5;
                let text_y = cell_y + (388.8 - content_h) / 2.0;
                let t = para(frame, ctx, text, 38, REGULAR, DARK_TEAL, cell_x + 60.4, baseline(text_y, 38), 707.6, 1.25, TextAlign::Left);
                let clip = format!("card-clip-{i}");
                fframes::svgr!(
                    <g opacity={p} transform={Transform::translate(0, rise(frame, &SPRING, duration_frames * i as f32 / 5.0, 60.0))}>
                        <defs>
                            <clipPath id={clip.clone()}>
                                <rect x={cell_x} y={cell_y} width="806.4" height="388.8" rx="36" />
                            </clipPath>
                        </defs>
                        <g clip-path={format!("url(#{clip})")}>
                            <rect x={cell_x} y={cell_y} width="806.4" height="388.8" rx="36" fill={WHITE} />
                            <rect x={cell_x} y={cell_y} width="22" height="388.8" fill={LIME} />
                        </g>
                        {t}
                    </g>
                )
            })
            .collect();
        fframes::svgr!(<g>{cards}</g>)
    }

    fn analogy_scene<'a>(
        &'a self,
        frame: &mut Frame,
        ctx: &FFramesContext<'a, '_>,
        duration_frames: f32,
    ) -> Svgr<'a> {
        let truck_in = spring_in(frame, &SPRING, duration_frames * 0.03);
        let caption_in = spring_in(frame, &SPRING, duration_frames * 0.3);
        let svg_x = -1152.0 * 1.2 + truck_in * (1152.0 * 1.2);
        let text = self.on_screen.first().map(String::as_str).unwrap_or("");
        let t = para(frame, ctx, text, 64, BOLD, DARK_TEAL, 0.0, baseline(172.8, 64), 1920.0, 1.1, TextAlign::Center);
        fframes::svgr!(
            <g>
                <g opacity={caption_in} transform={Transform::translate(0, rise(frame, &SPRING, duration_frames * 0.3, 50.0))}>{t}</g>
                <g transform={format!("translate({svg_x:.2} 488.2) scale(1.152)")}>
                    <rect x="110" y="70" width="340" height="210" rx="12" fill={WHITE} stroke={DARK_TEAL} stroke-width="12" />
                    <path d="M 116 82 L 280 200 L 444 82" fill="none" stroke={DARK_TEAL} stroke-width="12" stroke-linecap="round" stroke-linejoin="round" />
                    <rect x="40" y="210" width="570" height="110" rx="22" fill={DARK_TEAL} />
                    <rect x="650" y="150" width="200" height="170" rx="22" fill={DARK_TEAL} />
                    <rect x="690" y="185" width="110" height="70" rx="14" fill={WHITE} />
                    <g>
                        <circle cx="160" cy="345" r="54" fill={DARK_TEAL} />
                        <circle cx="160" cy="345" r="22" fill={WHITE} />
                        <circle cx="350" cy="345" r="54" fill={DARK_TEAL} />
                        <circle cx="350" cy="345" r="22" fill={WHITE} />
                        <circle cx="745" cy="345" r="54" fill={DARK_TEAL} />
                        <circle cx="745" cy="345" r="22" fill={WHITE} />
                    </g>
                </g>
            </g>
        )
    }

    fn cheat_sheet_scene<'a>(
        &'a self,
        frame: &mut Frame,
        ctx: &FFramesContext<'a, '_>,
        duration_frames: f32,
    ) -> Svgr<'a> {
        // Panel content is a centred column: 88px badge, 28px gap, then the
        // wrapped text (34px, line-height 1.3), hugging content vertically.
        let panels: Vec<Svgr> = (0..3)
            .map(|i| {
                let p = spring_in(frame, &SPRING, duration_frames * i as f32 / 4.0);
                let x = 134.4 + i as f32 * (518.4 + 48.0);
                let y = 237.6;
                let number = format!("{}", i + 1);
                let text = self.on_screen.get(i).map(String::as_str).unwrap_or("");
                let lines = wrap_count(frame, ctx, text, 34, REGULAR, 460.8) as f32;
                let content_h = 88.0 + 28.0 + lines * 44.2;
                let content_top = y + (604.8 - content_h) / 2.0;
                let badge_cy = content_top + 44.0;
                let text_top = content_top + 116.0;
                let t = para(frame, ctx, text, 34, REGULAR, DARK_TEAL, x + 28.8, baseline(text_top, 34), 460.8, 1.3, TextAlign::Center);
                fframes::svgr!(
                    <g opacity={p} transform={Transform::translate(0, rise(frame, &SPRING, duration_frames * i as f32 / 4.0, 70.0))}>
                        <rect x={x} y={y} width="518.4" height="604.8" rx="48" fill={WHITE} />
                        <circle cx={x + 259.2} cy={badge_cy} r="44" fill={LIME} />
                        <text x={x + 259.2} y={badge_cy - 44.0 + 20.0 + 0.96 * 48.0} text-anchor="middle" font-family={FONT} font-weight={BOLD} font-size="48" fill={DARK_TEAL}>{number}</text>
                        {t}
                    </g>
                )
            })
            .collect();
        fframes::svgr!(<g>{panels}</g>)
    }

    fn outro_scene<'a>(
        &'a self,
        frame: &mut Frame,
        ctx: &FFramesContext<'a, '_>,
        duration_frames: f32,
    ) -> Svgr<'a> {
        let card_in = spring_in(frame, &SPRING, duration_frames * 0.03);
        let char_in = spring_in(frame, &SPRING, duration_frames * 0.12);
        // Remotion wave: sin(frame * 0.18) degrees around (50%, 85%) of the
        // character box, gated by the entrance spring.
        let wave = (frame.seconds() * FPS * 0.18).sin() * 5.0 * char_in;
        let text = self.on_screen.first().map(String::as_str).unwrap_or("");
        let lines = wrap_count(frame, ctx, text, 56, BOLD, 691.2) as f32;
        let block_h = 64.8 * 2.0 + lines * 67.2 + 32.4 + 20.0;
        let card_y = (1080.0 - block_h) / 2.0;
        let scale = 0.8 + 0.2 * card_in;
        let cx = 279.0 + 403.2;
        let cy = card_y + block_h / 2.0;
        let card_transform = format!("translate({cx:.2} {cy:.2}) scale({scale:.4}) translate({:.2} {:.2})", -cx, -cy);
        let t = para(frame, ctx, text, 56, BOLD, DARK_TEAL, cx - 345.0, baseline(card_y + 64.8, 56), 691.2, 1.2, TextAlign::Center);
        let char_size = 594.0;
        let char_x = 1162.2;
        let char_y = (1080.0 - char_size) / 2.0;
        let char_transform = format!(
            "translate({:.2} 0) rotate({:.3} {:.2} {:.2})",
            (1.0 - char_in) * 120.0,
            wave,
            char_x + char_size * 200.0 / 248.0 / 2.0,
            char_y + char_size * 0.85
        );
        let mate = colleague("cheer", char_x, char_y, char_size, 0.0, true);
        fframes::svgr!(
            <g>
                <g opacity={card_in} transform={card_transform}>
                    <rect x="279" y={card_y} width="806.4" height={block_h} rx="48" fill={WHITE} />
                    {t}
                    <rect x={cx - 110.0 * card_in} y={card_y + 64.8 + lines * 67.2 + 32.4} width={220.0 * card_in} height="20" fill={LIME} />
                </g>
                <g opacity={char_in} transform={char_transform}>
                    {mate}
                </g>
            </g>
        )
    }
}
