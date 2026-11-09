# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Turn film.toml into normalized intermediates and build/plan.json for the fframes renderer.

    uv run prep.py [film.toml]

Every video source becomes a constant 30 fps H.264 file trimmed to its segment (speed applied,
padded with its last frame if the source is short). Every audio source becomes a 48 kHz stereo
wav, loudness-normalised with ffmpeg loudnorm. Results are cached by a key of the ffmpeg command
and the source's size/mtime, so re-running after an edit only redoes what changed.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

FPS = 30
W, H = 1920, 1080
PANEL_W = 1056  # clip width when a timeline panel takes the right 45%
SPLIT_W = 958  # each split side; 4 px gap in the middle
VOICE_LUFS = -16.0
MUSIC_LUFS = -16.0

HERE = Path(__file__).resolve().parent


def die(msg):
    print(f"prep: {msg}", file=sys.stderr)
    sys.exit(1)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(map(str, cmd)), file=sys.stderr)
        print(r.stderr[-3000:], file=sys.stderr)
        die("ffmpeg failed")
    return r.stdout


def probe(path):
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)])
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"].get("duration") or 0)
    w = h = 0
    if v:
        w, h = int(v["width"]), int(v["height"])
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        rot = int(v.get("tags", {}).get("rotate", rot))
        if abs(rot) % 180 == 90:
            w, h = h, w
    return {"w": w, "h": h, "dur": dur, "audio": a is not None}


class Prep:
    def __init__(self, film_path):
        self.film = Path(film_path).resolve()
        self.base = self.film.parent
        self.build = HERE / "build"
        self.media = self.build / "media"
        self.media.mkdir(parents=True, exist_ok=True)
        self.used = set()
        self.n_built = 0

    def src(self, p):
        path = (self.base / p).resolve() if not os.path.isabs(p) else Path(p)
        if not path.exists():
            die(f"missing source: {p} (resolved {path})")
        return path

    def cached(self, name, cmd, sources):
        """Run ffmpeg cmd unless its output already exists. Files are named by a hash of the
        command and the sources' size/mtime, so reordering segments rebuilds nothing; `name`
        only picks the extension and a readable prefix."""
        key_src = [str(c) for c in cmd] + [f"{s}:{s.stat().st_size}:{s.stat().st_mtime}" for s in sources]
        key = hashlib.sha1("\n".join(key_src).encode()).hexdigest()[:12]
        stem, ext = os.path.splitext(name)
        real = f"{stem.split('_', 1)[-1] if '_' in stem else 'v'}_{key}{ext}"
        out = self.media / real
        self.used.add(real)
        if out.exists():
            return real
        print(f"  build {real}", flush=True)
        tmp = self.media / f"tmp_{real}"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + [str(c) for c in cmd] + [str(tmp)])
        tmp.rename(out)
        self.n_built += 1
        return real

    # ---------------------------------------------------------------- video
    def fit_filter(self, info, tw, th):
        """Scale to cover tw x th; a source much taller than the target is shown at full height
        over a blurred, darkened, scaled-up copy of itself."""
        src_aspect = info["w"] / max(1, info["h"])
        if src_aspect < 0.6 * (tw / th):
            return (
                f"split[a][b];"
                f"[a]scale={tw // 4}:{th // 4}:force_original_aspect_ratio=increase,crop={tw // 4}:{th // 4},"
                f"boxblur=10:2,colorchannelmixer=rr=0.5:gg=0.5:bb=0.5,scale={tw}:{th},setsar=1[bg];"
                f"[b]scale=-2:{th},setsar=1[fg];[bg][fg]overlay=(W-w)/2:0"
            )
        return f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},setsar=1"

    def venc(self):
        return ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-g", "30", "-pix_fmt", "yuv420p"]

    def video(self, name, file, t_in, length, tw, th, speed=1.0, mode="cover", src_max=None):
        path = self.src(file)
        info = probe(path)
        if mode == "screen":
            # long side 1920, keep aspect; Rust fits it into the screen frame
            if info["w"] >= info["h"]:
                sw, sh = 1920, round(1920 * info["h"] / info["w"] / 2) * 2
            else:
                sh, sw = 1920, round(1920 * info["w"] / info["h"] / 2) * 2
            fit = f"scale={sw}:{sh},setsar=1"
            tw, th = sw, sh
        else:
            fit = self.fit_filter(info, tw, th)
        src_len = length * speed
        slack = 0.5
        if src_max is not None and src_len > src_max:   # hold the last frame instead of reading past `out`
            src_len, slack = src_max, 0.0
        vf = f"[0:v]setpts=(PTS-STARTPTS)/{speed},fps={FPS},{fit},tpad=stop_mode=clone:stop_duration={length + 1}[v]"
        cmd = ["-ss", f"{t_in:.3f}", "-t", f"{src_len + slack:.3f}", "-i", path, "-filter_complex", vf, "-map", "[v]",
               "-t", f"{length:.4f}"] + self.venc()
        return self.cached(name, cmd, [path]), tw, th

    def split_video(self, name, seg, length):
        inputs, chains, sources = [], [], []
        idx = 0
        for side in ("left", "right"):
            s = seg.get(side) or die(f"split needs `{side}`")
            path = self.src(s["file"])
            sources.append(path)
            info = probe(path)
            pieces = sorted(self.split_pieces(s), key=lambda p: p["at"])
            labels = []
            for k, p in enumerate(pieces):
                t0 = 0.0 if k == 0 else p["at"]
                t1 = pieces[k + 1]["at"] if k + 1 < len(pieces) else length
                seg_len = max(1.0 / FPS, t1 - t0)
                src0 = p["in"] - (p["at"] - t0)
                pad = 0.0
                if src0 < 0:
                    pad, src0 = -src0, 0.0
                inputs += ["-ss", f"{src0:.3f}", "-t", f"{seg_len + 0.5:.3f}", "-i", path]
                lab = f"p{idx}"
                startpad = f"tpad=start_mode=clone:start_duration={pad:.3f}," if pad > 0 else ""
                chains.append(
                    f"[{idx}:v]setpts=PTS-STARTPTS,fps={FPS},{startpad}tpad=stop_mode=clone:stop_duration={seg_len + 1:.3f},"
                    f"trim=duration={seg_len:.4f},setpts=PTS-STARTPTS[{lab}]"
                )
                labels.append(f"[{lab}]")
                idx += 1
            fit = self.fit_filter(info, SPLIT_W, H)
            chains.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0,{fit}[{side}]")
        chains.append(f"color=c=0x0e0e0e:s={W}x{H}:r={FPS}:d={length + 1:.3f}[bg]")
        chains.append(f"[bg][left]overlay=0:0:shortest=0[t];[t][right]overlay={W - SPLIT_W}:0,trim=duration={length:.4f}[v]")
        cmd = inputs + ["-filter_complex", ";".join(chains), "-map", "[v]", "-t", f"{length:.4f}"] + self.venc()
        return self.cached(name, cmd, sources)

    @staticmethod
    def split_pieces(side):
        if side.get("lines"):
            return [{"in": float(p["in"]), "out": float(p["out"]), "at": float(p.get("at", 0))} for p in side["lines"]]
        return [{"in": float(side["in"]), "out": float(side["out"]), "at": float(side.get("audio_at", 0))}]

    # ---------------------------------------------------------------- audio
    def audio(self, name, file, t_in=None, t_out=None, lufs=VOICE_LUFS, normalize=True):
        path = self.src(file)
        cmd = []
        if t_in is not None:
            cmd += ["-ss", f"{t_in:.3f}"]
        if t_out is not None:
            cmd += ["-t", f"{t_out - (t_in or 0):.3f}"]
        cmd += ["-i", path, "-vn"]
        af = f"loudnorm=I={lufs}:TP=-2:LRA=11,aresample=48000" if normalize else "aresample=48000"
        cmd += ["-af", af, "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le"]
        real = self.cached(name, cmd, [path])
        return real, probe(self.media / real)["dur"]

    def has_audio(self, file):
        return probe(self.src(file))["audio"]

    # ---------------------------------------------------------------- plan
    def make(self):
        film = tomllib.loads(self.film.read_text())
        segs = film.get("seg") or die("film.toml has no [[seg]] entries")
        plan_segs, tracks = [], []
        end = 0  # frame where the previous segment ends
        dips = []
        for i, seg in enumerate(segs):
            kind = seg.get("kind") or die(f"seg {i}: missing kind")
            tag = f"s{i:02d}"
            out = {"kind": kind, "name": f"{tag}_{kind}" + (f"_{seg['style']}" if seg.get("style") else ""), "params": seg}
            print(f"[{i:02d}] {kind} {seg.get('style', '')} {seg.get('file', '')}", flush=True)
            local_audio = []  # (file, at_within_segment, gain_db, voice)

            def vos(key, voice, default_gain):
                ends = []
                for j, v in enumerate(seg.get(key, []) or []):
                    norm = key == "vo"
                    nm = f"{tag}_{key}{j}.wav"
                    nm, d = self.audio(nm, v["file"], normalize=norm)
                    at = float(v.get("at", 0))
                    local_audio.append((nm, at, float(v.get("gain_db", default_gain)), voice))
                    ends.append(at + d)
                return ends

            vo_ends = vos("vo", True, 0.0)
            vos("sfx", False, -10.0)

            if kind in ("clip", "broll"):
                t_in = float(seg.get("in", 0))
                if "out" in seg:
                    t_out = float(seg["out"])
                else:
                    t_out = probe(self.src(seg["file"]))["dur"]
                dur = float(seg.get("dur", t_out - t_in))
                panel = seg.get("panel")
                tw = PANEL_W if panel else W
                vname, vw, vh = self.video(f"{tag}_clip.mp4", seg["file"], t_in, dur, tw, H)
                out.update(video=vname, vw=vw, vh=vh)
                own = kind == "clip" or seg.get("audio", False)
                if own and self.has_audio(seg["file"]):
                    nm = f"{tag}_a.wav"
                    nm, _ = self.audio(nm, seg["file"], t_in, min(t_out, t_in + dur))
                    local_audio.append((nm, 0.0, float(seg.get("gain_db", 0)), True))
                if panel:
                    panel = dict(panel)
                    panel["blocks"] = self.spread(panel.get("blocks", []), dur)
                    out["params"] = {**seg, "panel": panel}
            elif kind == "split":
                dur = float(seg.get("dur") or die(f"seg {i}: split needs dur"))
                vname = self.split_video(f"{tag}_split.mp4", seg, dur)
                out.update(video=vname, vw=W, vh=H)
                for side in ("left", "right"):
                    s = seg[side]
                    if not self.has_audio(s["file"]):
                        continue
                    for k, p in enumerate(self.split_pieces(s)):
                        nm = f"{tag}_{side}{k}.wav"
                        nm, _ = self.audio(nm, s["file"], p["in"], p["out"])
                        local_audio.append((nm, p["at"], float(s.get("gain_db", 0)), True))
            elif kind == "screen":
                t_in = float(seg.get("in", 0))
                speed = float(seg.get("speed", 1.0))
                t_out = float(seg["out"]) if "out" in seg else probe(self.src(seg["file"]))["dur"]
                dur = float(seg.get("dur", (t_out - t_in) / speed))
                vname, vw, vh = self.video(f"{tag}_screen.mp4", seg["file"], t_in, dur, W, H, speed=speed, mode="screen",
                                          src_max=t_out - t_in)
                out.update(video=vname, vw=vw, vh=vh)
            elif kind == "card":
                style = seg.get("style") or die(f"seg {i}: card needs style")
                if "dur" in seg:
                    dur = float(seg["dur"])
                elif vo_ends:
                    dur = max(vo_ends) + 0.6
                else:
                    dur = {"section": 3.0, "credits": 6.0}.get(style, 4.0)
                p = dict(seg)
                if style == "image":
                    src = self.src(seg["file"])
                    nm = f"{tag}{src.suffix.lower()}"
                    shutil.copyfile(src, self.media / nm)
                    self.used.add(nm)
                    p["image"] = nm
                if style == "bullets":
                    items = [x if isinstance(x, dict) else {"text": x} for x in seg.get("items", [])]
                    if len(items) > 6:
                        die(f"seg {i}: bullets take at most 6 items")
                    for it in items:
                        it.setdefault("check", seg.get("check", False))
                    p["items"] = self.spread(items, dur)
                if style == "timeline":
                    p["blocks"] = self.spread(seg.get("blocks", []), dur)
                if style == "credits":
                    p.setdefault("url", "https://mainstreet-ai-five.vercel.app")
                out["params"] = p
                if style == "section" and i > 0:
                    dips.append(None)  # filled with the start frame below
            else:
                die(f"seg {i}: unknown kind {kind}")

            frames = max(1, round(dur * FPS))
            fade = 0 if i == 0 else round(float(seg.get("fade", 0)) * FPS)
            fade = min(fade, frames - 1)
            start = end - fade
            end = start + frames
            out.update(frames=frames, fade_frames=fade, start_frame=start)
            if dips and dips[-1] is None:
                dips[-1] = start
            for nm, at, gain, voice in local_audio:
                tracks.append({"file": nm, "at": start / FPS + at, "gain_db": gain, "voice": voice,
                               "fade_in": fade / FPS if at == 0 else 0.0})
            plan_segs.append(out)

        music = film.get("music")
        if music:
            mname, _ = self.audio("m_music.wav", music["file"], lufs=MUSIC_LUFS)
            tracks.append({"file": mname, "at": 0.0, "gain_db": float(music.get("gain_db", -20)),
                           "voice": False, "music": True, "end": end / FPS})
        plan = {"source": str(self.film), "fps": FPS, "total_frames": end, "segments": plan_segs, "audio": tracks,
                "dips": dips, "master_gain_db": float(film.get("master_gain_db", 2.0))}
        (self.build / "plan.json").write_text(json.dumps(plan, indent=1))
        # drop intermediates no segment uses any more (read_folder loads the whole folder)
        for f in self.media.iterdir():
            if f.name not in self.used:
                f.unlink()
        print(f"plan: {len(plan_segs)} segments, {end / FPS:.2f} s ({end} frames), {len(tracks)} audio tracks, "
              f"{self.n_built} files rebuilt -> {self.build / 'plan.json'}")

    @staticmethod
    def spread(items, dur):
        """Give items without `at` evenly spread reveal times."""
        items = [dict(x) for x in items]
        n = len(items)
        if n == 0:
            return items
        t0, t1 = 0.5, max(0.6, dur - 2.0)
        for k, it in enumerate(items):
            if "at" not in it:
                it["at"] = t0 + (t1 - t0) * k / max(1, n - 1) if n > 1 else t0
        return items


if __name__ == "__main__":
    film = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FILM", "film.toml")
    Prep(film).make()
