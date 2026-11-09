//! MainStreet AI demo film: renders build/plan.json (written by prep.py from film.toml).
//! One fframes scene per segment; every video is a pre-trimmed 30 fps intermediate that plays
//! from the scene's first frame. See README.md for the edit list schema.
use fframes::animation::{AnimationRuntime, Easing};
use fframes::{
    AnimateRuntimeInput, AudioMap, AudioTimestamp, AudioTrack, Color, Duration, FFramesContext,
    FFramesSyncedVideoFrame, FontQuery, Frame, Overlap, Scene, Scenes, Svgr, SyncVideoFrameInput, Video,
};
use serde::Deserialize;
use serde_json::Value;

fframes::include_media_dir!(pub struct FilmMedia, "media");

pub const WIDTH: usize = 1920;
pub const HEIGHT: usize = 1080;
pub const FPS: usize = 30;

const BG: &str = "#141414";
const FG: &str = "#f2efe9";
const MUTED: &str = "#a8a39b";
const DIM: &str = "#7d7972";
const ACCENT: &str = "#f08a3c";
const FONT: &str = "Inter";
const PANEL_X: f32 = 1056.0;

#[derive(Deserialize, Debug)]
pub struct Plan {
    pub source: String,
    pub total_frames: usize,
    pub segments: Vec<SegSpec>,
    pub audio: Vec<TrackSpec>,
    #[serde(default)]
    pub dips: Vec<usize>,
    #[serde(default)]
    pub master_gain_db: f32,
}

#[derive(Deserialize, Debug)]
pub struct SegSpec {
    pub kind: String,
    pub name: String,
    pub frames: usize,
    pub fade_frames: usize,
    pub start_frame: usize,
    #[serde(default)]
    pub video: Option<String>,
    #[serde(default)]
    pub vw: f32,
    #[serde(default)]
    pub vh: f32,
    pub params: Value,
}

#[derive(Deserialize, Debug)]
pub struct TrackSpec {
    pub file: String,
    pub at: f32,
    pub gain_db: f32,
    #[serde(default)]
    pub voice: bool,
    #[serde(default)]
    pub fade_in: f32,
    #[serde(default)]
    pub music: bool,
    #[serde(default)]
    pub end: f32,
}

// ------------------------------------------------------------------ small helpers
fn fv(v: &Value, k: &str) -> Option<f32> {
    v.get(k).and_then(|x| x.as_f64()).map(|x| x as f32)
}
fn sv<'a>(v: &'a Value, k: &str) -> Option<&'a str> {
    v.get(k).and_then(|x| x.as_str())
}
fn bv(v: &Value, k: &str) -> bool {
    v.get(k).and_then(|x| x.as_bool()).unwrap_or(false)
}
fn arr<'a>(v: &'a Value, k: &str) -> &'a [Value] {
    v.get(k).and_then(|x| x.as_array()).map(|a| a.as_slice()).unwrap_or(&[])
}
fn clamp01(x: f32) -> f32 {
    x.clamp(0.0, 1.0)
}
fn ease_in_out(t: f32) -> f32 {
    let t = clamp01(t);
    if t < 0.5 { 4.0 * t * t * t } else { 1.0 - (-2.0 * t + 2.0).powi(3) / 2.0 }
}

const SPRING: Easing = Easing::Spring { mass: 1.0, stiffness: 150.0, damping: 18.0 };

/// Rise 20 px and fade in over 0.5 s, starting at `start` (scene seconds).
fn enter(frame: &Frame, start: f32) -> (f32, f32) {
    let spring = AnimationRuntime::new(3.0, &SPRING);
    let fade = AnimationRuntime::new(0.5, &Easing::EaseOut);
    let y = frame.animate_runtime(AnimateRuntimeInput { on_second: start, from: 20.0_f32, to: 0.0, animation_runtime: &spring });
    let o = frame.animate_runtime(AnimateRuntimeInput { on_second: start, from: 0.0_f32, to: 1.0, animation_runtime: &fade });
    (y, o)
}

fn font(size: usize, weight: u16) -> FontQuery<'static> {
    FontQuery { family: FONT, size, weight, ..Default::default() }
}

/// Measured text widths, cached; text_width wants a string that lives as long as the context,
/// so measured strings are interned (a bounded set: the film's words and wrap candidates).
static WIDTHS: std::sync::LazyLock<std::sync::Mutex<std::collections::HashMap<(String, usize, u16), f32>>> =
    std::sync::LazyLock::new(Default::default);

fn width_of(frame: &mut Frame, ctx: &FFramesContext, size: usize, weight: u16, s: &str) -> f32 {
    let key = (s.to_string(), size, weight);
    if let Some(w) = WIDTHS.lock().unwrap().get(&key) {
        return *w;
    }
    let st: &'static str = Box::leak(s.to_string().into_boxed_str());
    let w = frame.text_width(ctx, font(size, weight), st).map(|w| w as f32).unwrap_or(s.len() as f32 * size as f32 * 0.55);
    WIDTHS.lock().unwrap().insert(key, w);
    w
}

/// Greedy word wrap by measured width.
fn wrap(frame: &mut Frame, ctx: &FFramesContext, size: usize, weight: u16, text: &str, max_w: f32) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    for para in text.split('\n') {
        let mut cur = String::new();
        for word in para.split_whitespace() {
            let cand = if cur.is_empty() { word.to_string() } else { format!("{cur} {word}") };
            if !cur.is_empty() && width_of(frame, ctx, size, weight, &cand) > max_w {
                lines.push(std::mem::take(&mut cur));
                cur = word.to_string();
            } else {
                cur = cand;
            }
        }
        lines.push(cur);
    }
    lines
}

#[allow(clippy::too_many_arguments)]
fn txt<'a>(x: f32, y: f32, size: usize, weight: u16, fill: &'static str, anchor: &'static str, ls: f32, s: String) -> Svgr<'a> {
    fframes::svgr!(
        <text x={x} y={y} font-family="Inter" font-size={size} font-weight={weight.to_string()} fill={fill} text-anchor={anchor} letter-spacing={ls}>{s}</text>
    )
}

/// Lines of text, each `lh` apart, first baseline at `y`.
#[allow(clippy::too_many_arguments)]
fn lines_svg<'a>(lines: &[String], x: f32, y: f32, lh: f32, size: usize, weight: u16, fill: &'static str, anchor: &'static str, ls: f32) -> Svgr<'a> {
    let items: Vec<Svgr> = lines.iter().enumerate().map(|(i, l)| txt(x, y + i as f32 * lh, size, weight, fill, anchor, ls, l.clone())).collect();
    fframes::svgr!(<g>{items}</g>)
}

fn reveal<'a>(frame: &Frame, start: f32, child: Svgr<'a>) -> Svgr<'a> {
    let (dy, o) = enter(frame, start);
    fframes::svgr!(<g opacity={o} transform={format!("translate(0 {dy})")}>{child}</g>)
}

fn check_mark<'a>(x: f32, y: f32, on: bool) -> Svgr<'a> {
    if on {
        fframes::svgr!(<path d={format!("M{} {} l11 11 l22 -24", x, y - 14.0)} fill="none" stroke={ACCENT} stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round" />)
    } else {
        fframes::svgr!(<circle cx={x + 14.0} cy={y - 14.0} r="7" fill={ACCENT} />)
    }
}

fn card_bg<'a>() -> Svgr<'a> {
    fframes::svgr!(<rect x="0" y="0" width="1920" height="1080" fill="url(#cardbg)" />)
}

// ------------------------------------------------------------------ segment scene
#[derive(Debug)]
pub struct Seg {
    pub spec: SegSpec,
    name: &'static str,
}

impl Scene for Seg {
    fn name(&self) -> &'static str {
        self.name
    }
    fn duration(&self) -> Duration<'_> {
        Duration::Frames(self.spec.frames - self.spec.fade_frames)
    }
    fn overlap(&self) -> Overlap {
        if self.spec.fade_frames > 0 {
            Overlap::Previous((self.spec.fade_frames as f32 + 0.5) / FPS as f32)
        } else {
            Overlap::None
        }
    }
    fn render_frame<'a>(&'a self, mut frame: Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let p = &self.spec.params;
        let body = match self.spec.kind.as_str() {
            "clip" | "broll" => self.clip(&mut frame, ctx),
            "split" => self.full_video(&frame, ctx, 0.0, 1920.0),
            "screen" => self.screen(&frame, ctx),
            "card" => self.card(&mut frame, ctx),
            _ => Svgr::empty(),
        };
        let caption = match (sv(p, "caption"), self.spec.kind.as_str()) {
            (Some(c), k) if k != "card" => caption(&mut frame, ctx, c),
            _ => Svgr::empty(),
        };
        let fade = if self.spec.fade_frames > 0 { clamp01(frame.index as f32 / self.spec.fade_frames as f32) } else { 1.0 };
        fframes::svgr!(<g opacity={fade}>{body}{caption}</g>)
    }
}

fn caption<'a>(frame: &mut Frame, ctx: &FFramesContext, c: &str) -> Svgr<'a> {
    let w = width_of(frame, ctx, 32, 500, c) + 56.0;
    let x = 960.0 - w / 2.0;
    let (_, o) = enter(frame, 0.2);
    fframes::svgr!(<g opacity={o}>
        <rect x={x} y="988" width={w} height="56" rx="28" fill="#000000" fill-opacity="0.72" />
        <text x="960" y="1027" font-family="Inter" font-size="32" font-weight="500" fill={FG} text-anchor="middle">{c.to_string()}</text>
    </g>)
}

impl Seg {
    fn video_image<'a>(&'a self, frame: &Frame, ctx: &FFramesContext<'a, '_>, x: f32, y: f32, w: f32, h: f32) -> Svgr<'a> {
        let Some(name) = self.spec.video.as_deref() else { return Svgr::empty() };
        let input = SyncVideoFrameInput { start_from: 0., looping: false, editor_fallback_image: None };
        let Some(clip) = frame.get_synced_video_frame(ctx, name, &input) else {
            return Svgr::empty();
        };
        let img = clip.into_image();
        fframes::svgr!(<image href={img.href()} x={x} y={y} width={w} height={h} preserveAspectRatio="none" />)
    }

    fn full_video<'a>(&'a self, frame: &Frame, ctx: &FFramesContext<'a, '_>, x: f32, w: f32) -> Svgr<'a> {
        self.video_image(frame, ctx, x, 0.0, w, 1080.0)
    }

    fn clip<'a>(&'a self, frame: &mut Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let p = &self.spec.params;
        let (video, panel) = match p.get("panel") {
            Some(panel) => (self.full_video(frame, ctx, 0.0, PANEL_X), timeline_panel(frame, ctx, panel)),
            None => (self.full_video(frame, ctx, 0.0, 1920.0), Svgr::empty()),
        };
        let lt = match p.get("lower_third") {
            Some(lt) => lower_third(frame, ctx, lt),
            None => Svgr::empty(),
        };
        fframes::svgr!(<g>{video}{panel}{lt}</g>)
    }

    fn screen<'a>(&'a self, frame: &Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let p = &self.spec.params;
        let (vw, vh) = (self.spec.vw.max(1.0), self.spec.vh.max(1.0));
        let full = bv(p, "full");
        let (max_w, max_h, cy) = if full {
            (1920.0, 1080.0, 540.0)
        } else if p.get("caption").is_some() {
            (1766.0, 920.0, 500.0)
        } else {
            (1766.0, 980.0, 540.0)
        };
        let s = (max_w / vw).min(max_h / vh);
        let (bw, bh) = (vw * s, vh * s);
        let (bx, by) = (960.0 - bw / 2.0, cy - bh / 2.0);

        // eased push-in onto a region given as fractions of the recording
        let mut tf = String::from("translate(0 0)");
        if let Some(z) = p.get("zoom") {
            let t = frame.seconds();
            let at = fv(z, "at").unwrap_or(0.0);
            let dur = fv(z, "dur").unwrap_or(1.2).max(0.05);
            let mut k = ease_in_out((t - at) / dur);
            if let Some(until) = fv(z, "until") {
                k *= 1.0 - ease_in_out((t - until) / dur);
            }
            let (zx, zy) = (fv(z, "x").unwrap_or(0.0), fv(z, "y").unwrap_or(0.0));
            let (zw, zh) = (fv(z, "w").unwrap_or(1.0).max(0.05), fv(z, "h").unwrap_or(1.0).max(0.05));
            let s1 = (1.0 / zw).min(1.0 / zh).max(1.0);
            let sc = 1.0 + (s1 - 1.0) * k;
            let half = 0.5 / sc;
            let cx = (0.5 + (zx + zw / 2.0 - 0.5) * k).clamp(half, 1.0 - half);
            let cyf = (0.5 + (zy + zh / 2.0 - 0.5) * k).clamp(half, 1.0 - half);
            tf = format!(
                "translate({} {}) scale({}) translate({} {})",
                bx + bw / 2.0,
                by + bh / 2.0,
                sc,
                -(bx + cx * bw),
                -(by + cyf * bh)
            );
        }
        let video = self.video_image(frame, ctx, bx, by, bw, bh);
        if full {
            return fframes::svgr!(<g>
                <rect x="0" y="0" width="1920" height="1080" fill="#0e0e0e" />
                <g transform={tf}>{video}</g>
            </g>);
        }
        let r = 14.0;
        fframes::svgr!(<g>
            {card_bg()}
            <defs>
                <clipPath id={format!("scr{}", self.spec.start_frame)}>
                    <rect x={bx} y={by} width={bw} height={bh} rx={r} />
                </clipPath>
            </defs>
            // soft shadow and bezel
            <rect x={bx - 2.0} y={by + 14.0} width={bw + 4.0} height={bh + 10.0} rx={r + 6.0} fill="#000000" fill-opacity="0.35" />
            <rect x={bx - 10.0} y={by - 10.0} width={bw + 20.0} height={bh + 20.0} rx={r + 8.0} fill="#232323" stroke="#2e2e2e" stroke-width="1.5" />
            <g clip-path={format!("url(#scr{})", self.spec.start_frame)}>
                <rect x={bx} y={by} width={bw} height={bh} fill="#000000" />
                <g transform={tf}>{video}</g>
            </g>
        </g>)
    }

    fn card<'a>(&'a self, frame: &mut Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let p = &self.spec.params;
        let dur = self.spec.frames as f32 / FPS as f32;
        let body = match sv(p, "style").unwrap_or("") {
            "section" => section(frame, ctx, p),
            "number" => number(frame, ctx, p),
            "pair" => pair(frame, ctx, p),
            "bullets" => bullets(frame, ctx, p),
            "timeline" => timeline(frame, ctx, p),
            "image" => image(frame, ctx, p, dur),
            "credits" => credits(frame, ctx, p),
            _ => Svgr::empty(),
        };
        fframes::svgr!(<g>{card_bg()}{body}</g>)
    }
}

// ------------------------------------------------------------------ overlays
fn lower_third<'a>(frame: &mut Frame, ctx: &FFramesContext, lt: &Value) -> Svgr<'a> {
    let name = sv(lt, "name").unwrap_or("Ishaan Kalra").to_string();
    let line = sv(lt, "line").unwrap_or("").to_string();
    let hold = fv(lt, "dur").unwrap_or(4.0);
    let t = frame.seconds();
    if t > hold {
        return Svgr::empty();
    }
    let out = 1.0 - clamp01((t - (hold - 0.3)) / 0.3);
    let w = width_of(frame, ctx, 44, 600, &name).max(width_of(frame, ctx, 30, 500, &line)) + 92.0;
    let (dy1, o1) = enter(frame, 0.3);
    let (dy2, o2) = enter(frame, 0.42);
    let bar = frame.animate_runtime(AnimateRuntimeInput {
        on_second: 0.2,
        from: 0.5_f32,
        to: 1.0,
        animation_runtime: &AnimationRuntime::new(0.5, &Easing::CubicBezier(0.16, 1.0, 0.3, 1.0)),
    });
    fframes::svgr!(<g opacity={out}>
        <rect x="72" y="846" width={w * bar} height="132" rx="12" fill="#0c0c0c" fill-opacity="0.74" />
        <rect x="96" y="870" width="6" height="84" rx="3" fill={ACCENT} opacity={o1} />
        <g opacity={o1} transform={format!("translate(0 {dy1})")}>
            <text x="126" y="910" font-family="Inter" font-size="44" font-weight="600" fill={FG}>{name}</text>
        </g>
        <g opacity={o2} transform={format!("translate(0 {dy2})")}>
            <text x="126" y="952" font-family="Inter" font-size="30" font-weight="500" fill={MUTED}>{line}</text>
        </g>
    </g>)
}

fn timeline_panel<'a>(frame: &mut Frame, ctx: &FFramesContext, panel: &Value) -> Svgr<'a> {
    let x0 = PANEL_X + 80.0;
    let blocks = arr(panel, "blocks");
    let n = blocks.len().max(1) as f32;
    let top = 250.0;
    let step = (760.0 / n).min(210.0);
    let title = sv(panel, "title").map(|t| txt(x0, 170.0, 30, 600, ACCENT, "start", 3.0, t.to_uppercase())).unwrap_or_default();
    let rail_end = top + step * (n - 1.0);
    let mut items = Vec::new();
    for (i, b) in blocks.iter().enumerate() {
        let y = top + step * i as f32;
        let at = fv(b, "at").unwrap_or(0.5);
        let (dy, o) = enter(frame, at);
        let sub = wrap(frame, ctx, 28, 400, sv(b, "line").unwrap_or(""), 680.0);
        let body = fframes::svgr!(<g>
            <circle cx={x0} cy={y} r="9" fill={ACCENT} />
            {txt(x0 + 40.0, y + 9.0, 26, 600, ACCENT, "start", 2.0, sv(b, "label").unwrap_or("").to_uppercase())}
            {txt(x0 + 40.0, y + 58.0, 40, 600, FG, "start", -0.5, sv(b, "title").unwrap_or("").to_string())}
            {lines_svg(&sub[..sub.len().min(2)], x0 + 40.0, y + 100.0, 36.0, 28, 400, MUTED, "start", 0.0)}
        </g>);
        items.push(fframes::svgr!(<g opacity={o} transform={format!("translate(0 {dy})")}>{body}</g>));
    }
    fframes::svgr!(<g>
        <rect x={PANEL_X} y="0" width={1920.0 - PANEL_X} height="1080" fill="#161616" />
        <rect x={PANEL_X} y="0" width="2" height="1080" fill="#262626" />
        {title}
        <rect x={x0 - 1.5} y={top} width="3" height={(rail_end - top).max(1.0)} fill="#2c2c2c" />
        {items}
    </g>)
}

// ------------------------------------------------------------------ cards
fn section<'a>(frame: &mut Frame, ctx: &FFramesContext, p: &Value) -> Svgr<'a> {
    let x = 192.0;
    let title = wrap(frame, ctx, 96, 700, sv(p, "title").unwrap_or(""), 1500.0);
    let sub = sv(p, "subtitle").map(|s| wrap(frame, ctx, 44, 400, s, 1400.0)).unwrap_or_default();
    let h = 60.0 + title.len() as f32 * 112.0 + if sub.is_empty() { 0.0 } else { 30.0 + sub.len() as f32 * 58.0 };
    let y0 = 540.0 - h / 2.0;
    let eyebrow = sv(p, "eyebrow").unwrap_or("").to_uppercase();
    let ty = y0 + 60.0 + 88.0;
    let sy = y0 + 60.0 + title.len() as f32 * 112.0 + 30.0 + 40.0;
    let bar = frame.animate_runtime(AnimateRuntimeInput {
        on_second: 0.15,
        from: 0.5_f32,
        to: 72.0,
        animation_runtime: &AnimationRuntime::new(0.6, &Easing::CubicBezier(0.16, 1.0, 0.3, 1.0)),
    });
    fframes::svgr!(<g>
        <rect x={x} y={y0 - 34.0} width={bar} height="6" rx="3" fill={ACCENT} />
        {reveal(frame, 0.2, txt(x, y0 + 28.0, 30, 600, ACCENT, "start", 4.0, eyebrow))}
        {reveal(frame, 0.32, lines_svg(&title, x, ty, 112.0, 96, 700, FG, "start", -2.0))}
        {reveal(frame, 0.55, lines_svg(&sub, x, sy, 58.0, 44, 400, MUTED, "start", 0.0))}
    </g>)
}

fn number<'a>(frame: &mut Frame, ctx: &FFramesContext, p: &Value) -> Svgr<'a> {
    let line = wrap(frame, ctx, 44, 500, sv(p, "line").unwrap_or(""), 1300.0);
    let src = sv(p, "source").map(|s| wrap(frame, ctx, 28, 400, s, 1400.0)).unwrap_or_default();
    let h = 220.0 + 40.0 + line.len() as f32 * 58.0 + if src.is_empty() { 0.0 } else { 40.0 + src.len() as f32 * 38.0 };
    let y0 = 540.0 - h / 2.0;
    let fy = y0 + 180.0;
    let ly = y0 + 220.0 + 40.0 + 30.0;
    let sy = ly + (line.len() as f32 - 1.0) * 58.0 + 30.0 + 50.0;
    let fig = sv(p, "figure").unwrap_or("").to_string();
    fframes::svgr!(<g>
        {reveal(frame, 0.15, txt(960.0, fy, 220, 700, ACCENT, "middle", -6.0, fig))}
        {reveal(frame, 0.45, lines_svg(&line, 960.0, ly, 58.0, 44, 500, FG, "middle", 0.0))}
        {reveal(frame, 0.75, lines_svg(&src, 960.0, sy, 38.0, 28, 400, DIM, "middle", 0.0))}
    </g>)
}

fn pair<'a>(frame: &mut Frame, ctx: &FFramesContext, p: &Value) -> Svgr<'a> {
    let mut cols = Vec::new();
    for (i, k) in ["left", "right"].iter().enumerate() {
        let Some(c) = p.get(*k) else { continue };
        let cx = if i == 0 { 540.0 } else { 1380.0 };
        let line = wrap(frame, ctx, 40, 500, sv(c, "line").unwrap_or(""), 680.0);
        let fig = sv(c, "figure").unwrap_or("").to_string();
        let start = 0.15 + i as f32 * 0.35;
        cols.push(fframes::svgr!(<g>
            {reveal(frame, start, txt(cx, 470.0, 180, 700, ACCENT, "middle", -5.0, fig))}
            {reveal(frame, start + 0.2, lines_svg(&line, cx, 560.0, 54.0, 40, 500, FG, "middle", 0.0))}
        </g>));
    }
    let src = sv(p, "source").map(|s| wrap(frame, ctx, 28, 400, s, 1500.0)).unwrap_or_default();
    fframes::svgr!(<g>
        <rect x="959" y="330" width="2" height="360" fill="#2a2a2a" />
        {cols}
        {reveal(frame, 1.0, lines_svg(&src, 960.0, 860.0, 38.0, 28, 400, DIM, "middle", 0.0))}
    </g>)
}

fn bullets<'a>(frame: &mut Frame, ctx: &FFramesContext, p: &Value) -> Svgr<'a> {
    let x = 192.0;
    let title = wrap(frame, ctx, 72, 700, sv(p, "title").unwrap_or(""), 1500.0);
    let items = arr(p, "items");
    let mut rows: Vec<(Vec<String>, bool, f32)> = Vec::new();
    for it in items {
        let text = sv(it, "text").unwrap_or("");
        rows.push((wrap(frame, ctx, 44, 500, text, 1380.0), bv(it, "check"), fv(it, "at").unwrap_or(0.5)));
    }
    let body_h: f32 = rows.iter().map(|(l, _, _)| l.len() as f32 * 56.0 + 36.0).sum::<f32>() - 36.0;
    let h = title.len() as f32 * 86.0 + 60.0 + body_h.max(0.0);
    let y0 = (540.0 - h / 2.0).max(120.0);
    let mut y = y0 + 64.0 + title.len() as f32 * 86.0 + 40.0;
    let mut out = Vec::new();
    for (lines, check, at) in rows {
        let row = fframes::svgr!(<g>
            {check_mark(x, y, check)}
            {lines_svg(&lines, x + 70.0, y, 56.0, 44, 500, FG, "start", 0.0)}
        </g>);
        out.push(reveal(frame, at, row));
        y += lines.len() as f32 * 56.0 + 36.0;
    }
    fframes::svgr!(<g>
        {reveal(frame, 0.1, lines_svg(&title, x, y0 + 64.0, 86.0, 72, 700, FG, "start", -1.5))}
        {out}
    </g>)
}

fn timeline<'a>(frame: &mut Frame, ctx: &FFramesContext, p: &Value) -> Svgr<'a> {
    let blocks = arr(p, "blocks");
    let n = blocks.len().max(1);
    let (x0, x1) = (160.0, 1760.0);
    let col = (x1 - x0) / n as f32;
    let rail_y = 500.0;
    let title = sv(p, "title").map(|t| reveal(frame, 0.1, txt(x0, 330.0, 72, 700, FG, "start", -1.5, t.to_string()))).unwrap_or_default();
    let mut items = Vec::new();
    for (i, b) in blocks.iter().enumerate() {
        let x = x0 + col * i as f32;
        let at = fv(b, "at").unwrap_or(0.5);
        let t_lines = wrap(frame, ctx, 44, 600, sv(b, "title").unwrap_or(""), col - 50.0);
        let l_lines = wrap(frame, ctx, 30, 400, sv(b, "line").unwrap_or(""), col - 50.0);
        let ly = 630.0 + (t_lines.len() as f32 - 1.0) * 54.0 + 56.0;
        let body = fframes::svgr!(<g>
            <circle cx={x + 10.0} cy={rail_y} r="10" fill={ACCENT} />
            {txt(x, 570.0, 28, 600, ACCENT, "start", 2.5, sv(b, "label").unwrap_or("").to_uppercase())}
            {lines_svg(&t_lines, x, 630.0, 54.0, 44, 600, FG, "start", -0.5)}
            {lines_svg(&l_lines, x, ly, 42.0, 30, 400, MUTED, "start", 0.0)}
        </g>);
        items.push(reveal(frame, at, body));
    }
    fframes::svgr!(<g>
        {title}
        <rect x={x0} y={rail_y - 1.5} width={x1 - x0} height="3" fill="#2c2c2c" />
        {items}
    </g>)
}

fn image<'a>(frame: &mut Frame, ctx: &FFramesContext<'a, '_>, p: &Value, dur: f32) -> Svgr<'a> {
    let Some(img) = sv(p, "image").and_then(|n| ctx.get_image(n)) else { return Svgr::empty() };
    let s = 1.0 + 0.06 * clamp01(frame.seconds() / dur.max(0.1));
    let (_, o) = enter(frame, 0.0);
    let pad = fv(p, "pad").unwrap_or(48.0);
    fframes::svgr!(<g opacity={o} transform={format!("translate({} {}) scale({}) translate(-960 -540)", 960.0, 540.0, s)}>
        <image href={img.href()} x={pad} y={pad} width={1920.0 - 2.0 * pad} height={1080.0 - 2.0 * pad} preserveAspectRatio="xMidYMid meet" />
    </g>)
}

fn credits<'a>(frame: &mut Frame, ctx: &FFramesContext, p: &Value) -> Svgr<'a> {
    let names: Vec<String> = arr(p, "names").iter().filter_map(|v| v.as_str().map(String::from)).collect();
    let coach = sv(p, "coach").map(|c| wrap(frame, ctx, 32, 400, c, 1400.0)).unwrap_or_default();
    let title = sv(p, "title").unwrap_or("Team Forge").to_string();
    let url = sv(p, "url").unwrap_or("").to_string();
    let h = 110.0 + 50.0 + names.len() as f32 * 66.0 + if coach.is_empty() { 0.0 } else { 40.0 + coach.len() as f32 * 44.0 } + 120.0;
    let y0 = 540.0 - h / 2.0;
    let ny = y0 + 96.0 + 80.0;
    let cy = ny + names.len() as f32 * 66.0 + 30.0;
    let uy = cy + coach.len() as f32 * 44.0 + 90.0;
    let name_rows: Vec<Svgr> = names
        .into_iter()
        .enumerate()
        .map(|(i, n)| reveal(frame, 0.45 + i as f32 * 0.1, txt(960.0, ny + i as f32 * 66.0, 48, 500, FG, "middle", 0.0, n)))
        .collect();
    fframes::svgr!(<g>
        {reveal(frame, 0.15, txt(960.0, y0 + 96.0, 96, 700, FG, "middle", -2.0, title))}
        {name_rows}
        {reveal(frame, 0.9, lines_svg(&coach, 960.0, cy, 44.0, 32, 400, MUTED, "middle", 0.0))}
        {reveal(frame, 1.1, txt(960.0, uy, 40, 600, ACCENT, "middle", 0.0, url))}
    </g>)
}

// ------------------------------------------------------------------ the film
pub struct Film {
    segs: Vec<Seg>,
    pub plan: Plan,
}

impl std::fmt::Debug for Film {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Film").field("segments", &self.segs.len()).finish()
    }
}

impl Film {
    pub fn new(mut plan: Plan) -> Self {
        let segs = std::mem::take(&mut plan.segments)
            .into_iter()
            .map(|spec| Seg { name: Box::leak(spec.name.clone().into_boxed_str()), spec })
            .collect();
        Film { segs, plan }
    }
}

impl Video for Film {
    const FPS: usize = FPS;
    const WIDTH: usize = WIDTH;
    const HEIGHT: usize = HEIGHT;
    const BACKGROUND_COLOR: Color = Color::BLACK;

    fn duration(&self) -> Duration<'_> {
        Duration::Frames(self.plan.total_frames)
    }

    fn audio(&self) -> AudioMap<'_> {
        use AudioTimestamp::*;
        AudioMap::from(
            self.plan
                .audio
                .iter()
                .map(|a| {
                    if a.music {
                        AudioTrack::new(&a.file, Second(0.0)..Second(a.end))
                            .gain_db(a.gain_db)
                            .fade_in(1.0)
                            .fade_out(2.0)
                            .duck_under_voice()
                    } else {
                        let mut t = AudioTrack::new(&a.file, Second(a.at)..Eof).gain_db(a.gain_db);
                        if a.voice {
                            t = t.voice();
                        }
                        if a.fade_in > 0.0 {
                            t = t.fade_in(a.fade_in);
                        }
                        t
                    }
                })
                .collect::<Vec<_>>(),
        )
    }

    fn define_scenes(&self) -> Scenes<'_> {
        Scenes::from(self.segs.iter().map(|s| s as &dyn Scene).collect::<Vec<_>>())
    }

    fn render_frame<'a>(&'a self, frame: Frame, ctx: &FFramesContext<'a, '_>) -> Svgr<'a> {
        let g = frame.global_index as f32;
        // dip to black around each section card's first frame
        let dip = self
            .plan
            .dips
            .iter()
            .map(|&s| {
                let d = (g - s as f32).abs();
                1.0 - clamp01((d - 1.0) / 9.0)
            })
            .fold(0.0_f32, f32::max);
        let scene = ctx.render_scenes(&frame);
        fframes::svgr!(
            <svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">
                <defs>
                    <radialGradient id="cardbg" cx="50%" cy="42%" r="78%">
                        <stop offset="0" stop-color="#1c1c1c" />
                        <stop offset="1" stop-color="#111111" />
                    </radialGradient>
                </defs>
                <rect x="0" y="0" width="1920" height="1080" fill={BG} />
                {scene}
                <rect x="0" y="0" width="1920" height="1080" fill="#000000" opacity={dip} />
            </svg>
        )
    }
}
