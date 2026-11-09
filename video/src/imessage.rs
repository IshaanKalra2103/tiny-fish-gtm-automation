//! iMessage card: an iPhone on the right plays a conversation from `messages`; an optional
//! kinetic headline (`title`, `subtitle`) sits on the left. Camera: slow push-in on the phone
//! plus a short punch on every new bubble. Everything on the screen is clipped by `imsg-clip`.
use super::{arr, bv, clamp01, ease_in_out, fv, lines_svg, reveal, sv, txt, width_of, wrap};
use fframes::animation::{AnimationRuntime, Easing};
use fframes::{AnimateRuntimeInput, FFramesContext, Frame, Svgr};
use serde_json::Value;

const INK: &str = "#111214";
const MUTED: &str = "#5f646b";
const ACCENT: &str = "#1f9d6b";
const BLUE: &str = "#0a84ff";
const GREY: &str = "#e9e9eb";
const SYS: &str = "#8e8e93";
const WHITE: &str = "#ffffff";

// phone, in its own coordinates (origin at the bezel's top-left), placed at (PX, PY)
const PX: f32 = 1150.0;
const PY: f32 = 60.0;
const PW: f32 = 470.0;
const PH: f32 = 960.0;
const SX: f32 = 12.0;
const SY: f32 = 12.0;
const SW: f32 = 446.0;
const SH: f32 = 936.0;
const PIVOT_Y: f32 = 560.0;

const HEADER_B: f32 = 192.0; // header bottom
const CONTENT_TOP: f32 = 244.0; // first bubble (a "Today" stamp sits above it)
const COMPOSE_B: f32 = 906.0; // compose pill bottom
const PILL_H: f32 = 44.0;
const PILL_X0: f32 = 70.0;
const PILL_X1: f32 = 440.0;
const VIEW_B: f32 = COMPOSE_B - PILL_H - 14.0; // newest bubble's bottom stays above this
const LEFT_X: f32 = 26.0;
const RIGHT_X: f32 = 444.0;

const FS: usize = 24; // bubble text
const LH: f32 = 30.0;
const PAD_X: f32 = 18.0;
const PAD_Y: f32 = 12.0;
const WRAP_W: f32 = 290.0;
const LIST_FS: usize = 22;
const LIST_LH: f32 = 28.0;
const LIST_INDENT: f32 = 28.0;
const TYPING_W: f32 = 78.0;
const TYPING_H: f32 = 46.0;
const LINK_W: f32 = 300.0;
const LINK_IMG_H: f32 = 150.0;
const LINK_INFO_H: f32 = 76.0;
const DELIVERED_H: f32 = 24.0;

const POP: Easing = Easing::Spring { mass: 1.0, stiffness: 340.0, damping: 20.0 };
const RISE: Easing = Easing::Spring { mass: 1.0, stiffness: 120.0, damping: 17.0 };
const WORD: Easing = Easing::Spring { mass: 1.0, stiffness: 220.0, damping: 19.0 };

fn spring(frame: &Frame, e: &Easing, start: f32, from: f32, to: f32) -> f32 {
    let rt = AnimationRuntime::new(3.0, e);
    frame.animate_runtime(AnimateRuntimeInput { on_second: start, from, to, animation_runtime: &rt })
}

fn ease_out(x: f32) -> f32 {
    1.0 - (1.0 - clamp01(x)).powi(3)
}

/// Camera punch: up fast, settles back by 0.35 s.
fn punch(u: f32) -> f32 {
    if !(0.0..0.35).contains(&u) {
        return 0.0;
    }
    let x = u / 0.35;
    if x < 0.22 { 1.0 - (1.0 - x / 0.22).powi(2) } else { 1.0 - ease_in_out((x - 0.22) / 0.78) }
}

/// Rounded rect path with a radius per corner (tl, tr, br, bl).
#[allow(clippy::too_many_arguments)]
fn rrect(x: f32, y: f32, w: f32, h: f32, tl: f32, tr: f32, br: f32, bl: f32) -> String {
    format!(
        "M{} {} H{} A{tr} {tr} 0 0 1 {} {} V{} A{br} {br} 0 0 1 {} {} H{} A{bl} {bl} 0 0 1 {} {} V{} A{tl} {tl} 0 0 1 {} {} Z",
        x + tl,
        y,
        x + w - tr,
        x + w,
        y + tr,
        y + h - br,
        x + w - br,
        y + h,
        x + bl,
        x,
        y + h - bl,
        y + tl,
        x + tl,
        y
    )
}

/// iMessage tail at a bubble's bottom corner (right edge for me, left for them).
fn tail<'a>(x: f32, y: f32, w: f32, h: f32, me: bool, fill: &'static str) -> Svgr<'a> {
    let b = y + h;
    let d = if me {
        let r = x + w;
        format!("M{} {} C{} {} {} {} {} {} C{} {} {} {} {} {} Z", r, b - 28.0, r, b - 10.0, r + 2.0, b - 2.5, r + 8.0, b + 0.5, r + 2.0, b + 1.8, r - 6.0, b + 1.0, r - 13.0, b - 3.0)
    } else {
        format!("M{} {} C{} {} {} {} {} {} C{} {} {} {} {} {} Z", x, b - 28.0, x, b - 10.0, x - 2.0, b - 2.5, x - 8.0, b + 0.5, x - 2.0, b + 1.8, x + 6.0, b + 1.0, x + 13.0, b - 3.0)
    };
    fframes::svgr!(<path d={d} fill={fill} />)
}

struct Msg {
    me: bool,
    at: f32,
    typing: Option<f32>,
    typed: bool,
    text: String,
    lines: Vec<String>,
    list: Vec<Vec<String>>,
    link: Option<(String, String)>,
    w: f32,
    h: f32,     // bubble height
    extra: f32, // reserved space under the bubble ("Delivered")
}

fn measure(frame: &mut Frame, ctx: &FFramesContext, m: &Value, i: usize) -> Msg {
    let me = sv(m, "from").unwrap_or("them") == "me";
    let at = fv(m, "at").unwrap_or(0.6 + i as f32 * 1.5);
    let typing = if me { None } else { fv(m, "typing").filter(|d| *d > 0.0) };
    let text = sv(m, "text").unwrap_or("").to_string();
    let link = m.get("link").map(|l| (sv(l, "title").unwrap_or("").to_string(), sv(l, "url").unwrap_or("").to_string()));
    if let Some(l) = link {
        return Msg { me, at, typing, typed: false, text, lines: vec![], list: vec![], link: Some(l), w: LINK_W, h: LINK_IMG_H + LINK_INFO_H, extra: 0.0 };
    }
    let lines = if text.is_empty() { vec![] } else { wrap(frame, ctx, FS, 400, &text, WRAP_W) };
    let items: Vec<String> = arr(m, "list").iter().filter_map(|v| v.as_str().map(String::from)).collect();
    let list: Vec<Vec<String>> = items.iter().map(|s| wrap(frame, ctx, LIST_FS, 400, s, WRAP_W - LIST_INDENT + 16.0)).collect();
    let mut w: f32 = 0.0;
    for l in &lines {
        w = w.max(width_of(frame, ctx, FS, 400, l));
    }
    for it in &list {
        for l in it {
            w = w.max(LIST_INDENT + width_of(frame, ctx, LIST_FS, 400, l));
        }
    }
    let text_h = lines.len() as f32 * LH;
    let list_h: f32 = list.iter().map(|it| it.len() as f32 * LIST_LH).sum::<f32>() + list.len().saturating_sub(1) as f32 * 10.0;
    let both = if !lines.is_empty() && !list.is_empty() { 12.0 } else { 0.0 };
    let h = (2.0 * PAD_Y + text_h + both + list_h).max(2.0 * PAD_Y + LH);
    Msg { me, at, typing, typed: me && bv(m, "type"), text, lines, list, link: None, w: (w * 1.05 + 2.0 * PAD_X).max(60.0), h, extra: 0.0 }
}

/// Height of message i's slot at time t (None: not on screen yet).
fn slot_h(m: &Msg, t: f32) -> Option<f32> {
    if t >= m.at {
        Some(m.h + m.extra)
    } else {
        m.typing.filter(|d| t >= m.at - d).map(|_| TYPING_H)
    }
}

/// Slots on screen at t: (index, top y before scroll, height), and the content bottom.
fn layout(msgs: &[Msg], t: f32) -> (Vec<(usize, f32, f32)>, f32) {
    let mut out = Vec::new();
    let mut y = CONTENT_TOP;
    let mut prev: Option<bool> = None;
    for (i, m) in msgs.iter().enumerate() {
        let Some(h) = slot_h(m, t) else { continue };
        if let Some(pm) = prev {
            y += if pm == m.me { 6.0 } else { 16.0 };
        }
        out.push((i, y, h));
        y += h;
        prev = Some(m.me);
    }
    (out, y)
}

fn scroll_at(msgs: &[Msg], t: f32) -> f32 {
    let mut events: Vec<f32> = Vec::new();
    for m in msgs {
        events.push(m.at);
        if let Some(d) = m.typing {
            events.push(m.at - d);
        }
    }
    events.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let (mut scroll, mut prev) = (0.0, 0.0);
    for e in events {
        let target = (layout(msgs, e + 0.001).1 - VIEW_B).max(0.0);
        scroll += (target - prev) * ease_out((t - e + 0.08) / 0.5);
        prev = target;
    }
    scroll
}

pub fn imessage<'a>(frame: &mut Frame, ctx: &FFramesContext, p: &serde_json::Value, dur: f32) -> Svgr<'a> {
    let t = frame.seconds();
    let mut msgs: Vec<Msg> = arr(p, "messages").iter().enumerate().map(|(i, m)| measure(frame, ctx, m, i)).collect();
    if let Some(last_me) = msgs.iter().rposition(|m| m.me) {
        msgs[last_me].extra = DELIVERED_H;
    }

    // ---------------------------------------------------------------- conversation
    let (slots, _) = layout(&msgs, t);
    let scroll = scroll_at(&msgs, t);
    let mut bubbles: Vec<Svgr> = Vec::new();
    for (k, &(i, y, _)) in slots.iter().enumerate() {
        let m = &msgs[i];
        let next_same = slots.get(k + 1).map(|&(j, _, _)| msgs[j].me == m.me).unwrap_or(false);
        if t < m.at {
            bubbles.push(typing_bubble(frame, t, m.at - m.typing.unwrap_or(0.0), y));
            continue;
        }
        let x = if m.me { RIGHT_X - m.w } else { LEFT_X };
        // spring pop, overshoot capped so a tall bubble never grows into the one above it
        let s = spring(frame, &POP, m.at, 0.6, 1.0).min(1.0 + 4.0 / m.h);
        let o = clamp01((t - m.at) / 0.08);
        let (ax, ay) = (if m.me { x + m.w } else { x }, y + m.h);
        let body = bubble(frame, m, x, y, !next_same);
        let delivered = if m.extra > 0.0 {
            let od = clamp01((t - m.at - 0.45) / 0.25);
            fframes::svgr!(<g opacity={od}>{txt(RIGHT_X - 4.0, y + m.h + 19.0, 15, 500, SYS, "end", 0.0, "Delivered".to_string())}</g>)
        } else {
            Svgr::empty()
        };
        bubbles.push(fframes::svgr!(<g>
            <g opacity={o} transform={format!("translate({ax} {ay}) scale({s}) translate({} {})", -ax, -ay)}>{body}</g>
            {delivered}
        </g>));
    }
    let stamp = txt(SX + SW / 2.0, CONTENT_TOP - 16.0, 15, 500, SYS, "middle", 0.0, "Today 9:41 AM".to_string());
    let convo = fframes::svgr!(<g transform={format!("translate(0 {})", -scroll)}>{stamp}{bubbles}</g>);

    // ---------------------------------------------------------------- compose bar
    let compose = compose_bar(frame, ctx, &msgs, t);

    // ---------------------------------------------------------------- header
    let contact = sv(p, "contact").unwrap_or("MainStreet AI").to_string();
    let name_w = width_of(frame, ctx, 18, 500, &contact);
    let cx = SX + SW / 2.0;
    let chev_x = cx + name_w / 2.0 + 6.0;
    let initial = contact.chars().next().map(|c| c.to_uppercase().to_string()).unwrap_or_default();
    let header = fframes::svgr!(<g>
        <rect x={SX} y={SY} width={SW} height={HEADER_B - SY} fill="#f6f6f8" />
        <rect x={SX} y={HEADER_B} width={SW} height="1" fill="#d9d9de" />
        {txt(68.0, 50.0, 20, 600, INK, "start", 0.0, "9:41".to_string())}
        <rect x="350" y="45" width="4" height="6" rx="1" fill={INK} />
        <rect x="356" y="42" width="4" height="9" rx="1" fill={INK} />
        <rect x="362" y="39" width="4" height="12" rx="1" fill={INK} />
        <rect x="368" y="36" width="4" height="15" rx="1" fill={INK} />
        <rect x="384" y="36.5" width="30" height="14" rx="4" fill="none" stroke={INK} stroke-opacity="0.4" stroke-width="1.5" />
        <rect x="386.5" y="39" width="22" height="9" rx="2" fill={INK} />
        <rect x="415.5" y="41" width="2.5" height="5" rx="1" fill={INK} fill-opacity="0.4" />
        <path d="M46 98 L34 110 L46 122" fill="none" stroke={BLUE} stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
        <circle cx={cx} cy="110" r="34" fill={ACCENT} />
        {txt(cx, 122.0, 34, 700, WHITE, "middle", 0.0, initial)}
        {txt(cx, 173.0, 18, 500, INK, "middle", 0.0, contact)}
        <path d={format!("M{} 162 L{} 167 L{} 172", chev_x, chev_x + 5.0, chev_x)} fill="none" stroke={SYS} stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
    </g>);

    // ---------------------------------------------------------------- phone + camera
    let rise = spring(frame, &RISE, 0.0, 1000.0, 0.0);
    let push = 1.0 + 0.06 * clamp01(t / dur.max(0.1));
    let kick = msgs.iter().map(|m| punch(t - m.at)).fold(0.0_f32, f32::max);
    let s = push * (1.0 + 0.03 * kick);
    let cam = format!("translate({} {}) translate({} {}) scale({}) translate({} {})", PX, PY + rise, PW / 2.0, PIVOT_Y, s, -PW / 2.0, -PIVOT_Y);
    let phone = fframes::svgr!(<g transform={cam}>
        <defs>
            <clipPath id="imsg-clip">
                <rect x={SX} y={SY} width={SW} height={SH} rx="62" />
            </clipPath>
            <filter id="imsg-shadow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="26" />
            </filter>
            <linearGradient id="imsg-lg" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#27b47c" />
                <stop offset="1" stop-color="#15805a" />
            </linearGradient>
        </defs>
        <rect x="24" y="48" width="422" height="920" rx="70" fill="#0b0d10" fill-opacity="0.28" filter="url(#imsg-shadow)" />
        <rect x="-4" y="190" width="6" height="40" rx="2" fill="#1d1d20" />
        <rect x="-4" y="262" width="6" height="72" rx="2" fill="#1d1d20" />
        <rect x="-4" y="348" width="6" height="72" rx="2" fill="#1d1d20" />
        <rect x="468" y="300" width="6" height="112" rx="2" fill="#1d1d20" />
        <rect x="0" y="0" width={PW} height={PH} rx="76" fill="#0e0e10" />
        <rect x="2.5" y="2.5" width={PW - 5.0} height={PH - 5.0} rx="73.5" fill="none" stroke="#3b3b40" stroke-width="2" />
        <g clip-path="url(#imsg-clip)">
            <rect x={SX} y={SY} width={SW} height={SH} fill={WHITE} />
            {convo}
            {compose}
            {header}
        </g>
        <rect x={PW / 2.0 - 62.0} y="24" width="124" height="36" rx="18" fill="#000000" />
        <rect x={PW / 2.0 - 70.0} y="930" width="140" height="5" rx="2.5" fill={INK} />
    </g>);

    // ---------------------------------------------------------------- headline
    let headline = headline(frame, ctx, p);
    fframes::svgr!(<g>{headline}{phone}</g>)
}

fn typing_bubble<'a>(frame: &Frame, t: f32, start: f32, y: f32) -> Svgr<'a> {
    let x = LEFT_X;
    let s = spring(frame, &POP, start, 0.6, 1.0);
    let o = clamp01((t - start) / 0.08);
    let (ax, ay) = (x, y + TYPING_H);
    let dots: Vec<Svgr> = (0..3)
        .map(|k| {
            let ph = (t - start) * std::f32::consts::TAU * 1.5 - k as f32 * 0.9;
            let up = ph.sin().max(0.0);
            fframes::svgr!(<circle cx={x + 21.0 + k as f32 * 18.0} cy={y + TYPING_H / 2.0 - 4.0 * up} r="6" fill={SYS} fill-opacity={0.45 + 0.55 * up} />)
        })
        .collect();
    fframes::svgr!(<g opacity={o} transform={format!("translate({ax} {ay}) scale({s}) translate({} {})", -ax, -ay)}>
        <circle cx={x - 3.0} cy={y + TYPING_H + 5.0} r="4" fill={GREY} />
        <circle cx={x + 4.0} cy={y + TYPING_H - 4.0} r="8" fill={GREY} />
        <rect x={x} y={y} width={TYPING_W} height={TYPING_H} rx={TYPING_H / 2.0} fill={GREY} />
        {dots}
    </g>)
}

fn bubble<'a>(_frame: &mut Frame, m: &Msg, x: f32, y: f32, with_tail: bool) -> Svgr<'a> {
    let (fill, ink) = if m.me { (BLUE, WHITE) } else { (GREY, INK) };
    if let Some((title, url)) = &m.link {
        let iy = y + LINK_IMG_H;
        let tl = if with_tail { tail(x, y, LINK_W, m.h, m.me, fill) } else { Svgr::empty() };
        let (lx, ly) = (x + LINK_W / 2.0, y + LINK_IMG_H / 2.0);
        return fframes::svgr!(<g>
            {tl}
            <path d={rrect(x, y, LINK_W, LINK_IMG_H, 20.0, 20.0, 0.0, 0.0)} fill="url(#imsg-lg)" />
            <circle cx={lx} cy={ly} r="58" fill="none" stroke={WHITE} stroke-opacity="0.16" stroke-width="2" />
            <circle cx={lx} cy={ly} r="92" fill="none" stroke={WHITE} stroke-opacity="0.10" stroke-width="2" />
            <rect x={lx - 32.0} y={ly - 32.0} width="64" height="64" rx="16" fill={WHITE} />
            {txt(lx, ly + 13.0, 36, 700, ACCENT, "middle", 0.0, "M".to_string())}
            <path d={rrect(x, iy, LINK_W, LINK_INFO_H, 0.0, 0.0, 20.0, 20.0)} fill={fill} />
            {txt(x + 16.0, iy + 32.0, 20, 600, ink, "start", 0.0, title.clone())}
            {txt(x + 16.0, iy + 58.0, 17, 400, if m.me { WHITE } else { MUTED }, "start", 0.0, url.clone())}
        </g>);
    }
    let tl = if with_tail { tail(x, y, m.w, m.h, m.me, fill) } else { Svgr::empty() };
    let tx = x + PAD_X;
    let text = lines_svg(&m.lines, tx, y + PAD_Y + 23.0, LH, FS, 400, ink, "start", 0.0);
    let mut ly = y + PAD_Y + m.lines.len() as f32 * LH + if m.lines.is_empty() { 0.0 } else { 12.0 };
    let mut items: Vec<Svgr> = Vec::new();
    for (k, it) in m.list.iter().enumerate() {
        items.push(txt(tx, ly + 21.0, LIST_FS, 600, ink, "start", 0.0, format!("{}.", k + 1)));
        items.push(lines_svg(it, tx + LIST_INDENT, ly + 21.0, LIST_LH, LIST_FS, 400, ink, "start", 0.0));
        ly += it.len() as f32 * LIST_LH + 10.0;
    }
    let _ = &m.text;
    fframes::svgr!(<g>
        {tl}
        <rect x={x} y={y} width={m.w} height={m.h} rx="21" fill={fill} />
        {text}
        {items}
    </g>)
}

fn compose_bar<'a>(frame: &mut Frame, ctx: &FFramesContext, msgs: &[Msg], t: f32) -> Svgr<'a> {
    // text being typed into the field, if any
    let mut typed = String::new();
    let mut busy = false;
    for m in msgs.iter().filter(|m| m.typed) {
        let (t0, t1) = (m.at - 1.35, m.at - 0.15);
        if t >= t0 && t < m.at {
            let n = m.text.chars().count();
            let k = clamp01((t - t0) / (t1 - t0));
            typed = m.text.chars().take((k * n as f32).round() as usize).collect();
            busy = k < 1.0;
        }
    }
    let lines = if typed.is_empty() { vec![] } else { wrap(frame, ctx, 22, 400, &typed, PILL_X1 - PILL_X0 - 62.0) };
    let n = lines.len().max(1) as f32;
    let h = PILL_H + (n - 1.0) * 28.0;
    let top = COMPOSE_B - h;
    let bg = fframes::svgr!(<rect x={SX} y={top - 12.0} width={SW} height={SY + SH - top + 12.0} fill={WHITE} />);
    let plus = fframes::svgr!(<g>
        <circle cx="40" cy={COMPOSE_B - 22.0} r="18" fill={GREY} />
        <path d={format!("M40 {} V{} M31 {} H49", COMPOSE_B - 31.0, COMPOSE_B - 13.0, COMPOSE_B - 22.0)} stroke={SYS} stroke-width="2.6" stroke-linecap="round" />
    </g>);
    let pill = fframes::svgr!(<rect x={PILL_X0} y={top} width={PILL_X1 - PILL_X0} height={h} rx="22" fill={WHITE} stroke="#d1d1d6" stroke-width="1.5" />);
    if lines.is_empty() {
        return fframes::svgr!(<g>
            {bg}{plus}{pill}
            {txt(PILL_X0 + 18.0, COMPOSE_B - 15.0, 22, 400, "#b1b1b6", "start", 0.0, "iMessage".to_string())}
        </g>);
    }
    let tx = PILL_X0 + 18.0;
    let by = top + 29.0;
    let last = lines.last().cloned().unwrap_or_default();
    let caret_x = tx + width_of(frame, ctx, 22, 400, &last) + 2.0;
    let caret_y = by + (n - 1.0) * 28.0;
    let caret_on = busy || (t * 2.0).fract() < 0.6;
    let caret = if caret_on {
        fframes::svgr!(<rect x={caret_x} y={caret_y - 21.0} width="2.5" height="27" rx="1" fill={BLUE} />)
    } else {
        Svgr::empty()
    };
    let (sx, sy) = (PILL_X1 - 22.0, COMPOSE_B - 22.0);
    fframes::svgr!(<g>
        {bg}{plus}{pill}
        {lines_svg(&lines, tx, by, 28.0, 22, 400, INK, "start", 0.0)}
        {caret}
        <circle cx={sx} cy={sy} r="16" fill={BLUE} />
        <path d={format!("M{sx} {} V{} M{} {} L{sx} {} L{} {}", sy + 8.0, sy - 8.0, sx - 6.5, sy - 1.5, sy - 8.0, sx + 6.5, sy - 1.5)} fill="none" stroke={WHITE} stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
    </g>)
}

fn headline<'a>(frame: &mut Frame, ctx: &FFramesContext, p: &Value) -> Svgr<'a> {
    let Some(title) = sv(p, "title") else { return Svgr::empty() };
    let x0 = 160.0;
    let max_w = 900.0;
    let ls = -2.0;
    let mut size: usize = 108;
    while size > 84 && width_of(frame, ctx, size, 700, title) + ls * title.chars().count() as f32 > max_w {
        size -= 4;
    }
    let lines = wrap(frame, ctx, size, 700, title, max_w);
    let lh = size as f32 * 1.08;
    let sub = sv(p, "subtitle").map(|s| wrap(frame, ctx, 40, 500, s, max_w)).unwrap_or_default();
    let h = lines.len() as f32 * lh + if sub.is_empty() { 0.0 } else { 30.0 + sub.len() as f32 * 52.0 };
    let y0 = 540.0 - h / 2.0;
    let space = width_of(frame, ctx, size, 700, "a a") - width_of(frame, ctx, size, 700, "aa") + ls;
    let t = frame.seconds();
    let mut words: Vec<Svgr> = Vec::new();
    let mut k = 0;
    for (li, line) in lines.iter().enumerate() {
        let by = y0 + size as f32 * 0.82 + li as f32 * lh;
        let mut x = x0;
        for w in line.split_whitespace() {
            let start = 0.25 + k as f32 * 0.11;
            let dy = spring(frame, &WORD, start, 70.0, 0.0);
            let o = clamp01((t - start) / 0.16);
            words.push(fframes::svgr!(<g opacity={o} transform={format!("translate(0 {dy})")}>
                {txt(x, by, size, 700, INK, "start", ls, w.to_string())}
            </g>));
            x += width_of(frame, ctx, size, 700, w) + ls * w.chars().count() as f32 + space;
            k += 1;
        }
    }
    let sub_start = 0.25 + k as f32 * 0.11 + 0.15;
    let sy = y0 + lines.len() as f32 * lh + 30.0 + 38.0;
    let subtitle = reveal(frame, sub_start, lines_svg(&sub, x0 + 2.0, sy, 52.0, 40, 500, MUTED, "start", 0.0));
    // optional footnote, bottom-left: a thin green rule and small muted text
    let note = match sv(p, "note") {
        Some(n) => {
            let nl = wrap(frame, ctx, 24, 500, n, 760.0);
            let nh = nl.len() as f32 * 34.0;
            let ny = 1000.0 - nh;
            reveal(frame, sub_start + 0.6, fframes::svgr!(<g>
                <rect x={x0 + 2.0} y={ny - 4.0} width="4" height={nh} rx="2" fill={ACCENT} />
                {lines_svg(&nl, x0 + 22.0, ny + 20.0, 34.0, 24, 500, MUTED, "start", 0.0)}
            </g>))
        }
        None => Svgr::empty(),
    };
    fframes::svgr!(<g>{words}{subtitle}{note}</g>)
}
