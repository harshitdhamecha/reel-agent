#!/usr/bin/env python3
"""Measure a finished reel's style with ffmpeg only (no Edits needed). Prints JSON.

usage: analyze_reel.py <video> [--threshold 0.7] [--frames OUT_DIR]

Measures:
  duration, fps, size, audio presence
  cuts (normalised frame correlation; brightness flicker ignored) -> shot lengths, flash bursts (runs of >=3 shots < 0.3 s)
  per-shot look: luma (YAVG 0-255), saturation (SATAVG), warmth (VAVG-UAVG; >0 = warmer/redder)
  audio: tempo (BPM from onset autocorrelation, 90-180 range), onsets, cut-on-beat ratio vs a
         random-cut baseline, fade-out length at the end
  --frames: writes first.jpg (the hook/thumbnail) and sheet.jpg (one frame per shot) for a human/Claude to read
            the caption, hook and content mix.

Pure standard library + ffmpeg/ffprobe on PATH. Run with python3 -I.
"""
import argparse
import json
import math
import os
import random
import re
import shutil
import statistics
import subprocess
import sys

SR = 22050          # analysis sample rate
HOP = 512           # onset hop (~23 ms)
WIN = 1024
FLASH_MAX = 0.3     # a shot shorter than this is a "flash" (~½ beat at 100 BPM)


def run(cmd, binary=False):
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode(errors="replace")[-400:])
    return p.stdout if binary else p.stdout.decode(errors="replace")


def probe(path):
    j = json.loads(run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,width,height,avg_frame_rate",
                        "-of", "json", path]))
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    num, _, den = (v.get("avg_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    return {
        "duration": round(float(j["format"]["duration"]), 3),
        "width": v.get("width"), "height": v.get("height"), "fps": round(fps, 3),
        "has_audio": any(s["codec_type"] == "audio" for s in j["streams"]),
    }


def frame_stats(path):
    """Per-frame look (signalstats) at reduced size."""
    out = run(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf",
               "scale=180:-2,signalstats,metadata=print:file=-", "-f", "null", "-"])
    frames, cur = [], None
    for line in out.splitlines():
        m = re.match(r"frame:\d+\s+pts:\d+\s+pts_time:([\d.]+)", line)
        if m:
            cur = {"t": float(m.group(1))}
            frames.append(cur)
            continue
        m = re.match(r"lavfi\.(\w+(?:\.\w+)?)=([-\d.]+)", line)
        if m and cur is not None:
            cur[m.group(1)] = float(m.group(2))
    return frames


def thumbs(path, w=18, h=32):
    """Tiny grayscale frames, each normalised to zero mean / unit variance (removes brightness flicker)."""
    raw = run(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", f"scale={w}:{h},format=gray",
               "-f", "rawvideo", "-"], binary=True)
    n, size = len(raw) // (w * h), w * h
    out = []
    for i in range(n):
        v = raw[i * size:(i + 1) * size]
        m = sum(v) / size
        sd = math.sqrt(sum((x - m) ** 2 for x in v) / size) or 1.0
        out.append([(x - m) / sd for x in v])
    return out


def _corr(a, b):
    return sum(x * y for x, y in zip(a, b)) / len(a)


def detect_cuts(path, fps, threshold=0.7):
    """Hard cuts by normalised correlation of consecutive frames, with a persistence check:
    the new picture must still differ from the old one 2 frames later (rejects 1-frame flashes).
    Strobe lights / glow sticks in dark clubs can still trigger; see grid labelling."""
    fr = thumbs(path)
    cuts = []
    for i in range(1, len(fr) - 2):
        c01, c02, c12 = _corr(fr[i - 1], fr[i]), _corr(fr[i - 1], fr[i + 2]), _corr(fr[i], fr[i + 2])
        if c01 < threshold and c02 < threshold and c12 > c02:
            if not cuts or i - cuts[-1] > 2:
                cuts.append(i)
    return [round(i / fps, 3) for i in cuts]


def label_grid(cuts, bpm, fps, skip_until=0.0):
    """Fit a half-beat grid to the cuts (phase + period refined by least squares), label each
    cut on/off grid (±2 frames). Returns the refined BPM too — cuts are frame-exact, so this is
    usually more precise than the audio estimate."""
    if not bpm or not cuts:
        return None
    tol = 2.0 / fps + 0.004
    pool = [c for c in cuts if c >= skip_until] or cuts

    def on(ph, half):
        return [c for c in cuts if abs((c - ph) / half - round((c - ph) / half)) * half <= tol]

    # the audio BPM is only ~±2 % right; search tempi around it for the grid that explains most cuts
    best = (-1, 0.0, 0.0)
    for step in range(-40, 41):
        b = bpm * (1 + step / 1000)
        h = 60.0 / b / 2
        for ph in pool:
            n = len(on(ph, h))
            if n > best[0]:
                best = (n, ph, h)
    _, ph, half = best
    for _ in range(4):
        pts = [(round((c - ph) / half), c) for c in on(ph, half)]
        if len(pts) < 3:
            break
        n = len(pts)
        mk = sum(k for k, _ in pts) / n
        mc = sum(c for _, c in pts) / n
        var = sum((k - mk) ** 2 for k, _ in pts)
        if not var:
            break
        half = sum((k - mk) * (c - mc) for k, c in pts) / var
        ph = mc - half * mk
    on_grid = on(ph, half)
    return {"phase_s": round(ph, 3), "bpm": round(60.0 / (2 * half), 2), "on_grid": on_grid,
            "off_grid": [c for c in cuts if c not in on_grid]}


def shots_from(cuts, duration, frames):
    bounds = [0.0] + cuts + [duration]
    shots = []
    for a, b in zip(bounds, bounds[1:]):
        fs = [f for f in frames if a <= f["t"] < b]
        if fs:
            y = statistics.mean(f.get("signalstats.YAVG", 0) for f in fs)
            s = statistics.mean(f.get("signalstats.SATAVG", 0) for f in fs)
            w = statistics.mean(f.get("signalstats.VAVG", 128) - f.get("signalstats.UAVG", 128) for f in fs)
        else:
            y = s = w = None
        shots.append({"start": round(a, 3), "len": round(b - a, 3),
                      "luma": None if y is None else round(y, 1),
                      "sat": None if s is None else round(s, 1),
                      "warmth": None if w is None else round(w, 1)})
    return shots


def flash_bursts(shots):
    bursts, run_ = [], []
    for sh in shots:
        if sh["len"] < FLASH_MAX:
            run_.append(sh)
        else:
            if len(run_) >= 3:
                bursts.append(run_)
            run_ = []
    if len(run_) >= 3:
        bursts.append(run_)
    return [{"start": b[0]["start"], "end": round(b[-1]["start"] + b[-1]["len"], 3),
             "shots": len(b), "avg_len": round(statistics.mean(x["len"] for x in b), 3)} for b in bursts]


def load_audio(path):
    raw = run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR),
               "-f", "s16le", "-"], binary=True)
    import array
    a = array.array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder == "big":
        a.byteswap()
    return a


def onset_envelope(samples):
    """Spectral-flux-like envelope from band energies (cheap: log-energy rise per hop)."""
    n = (len(samples) - WIN) // HOP
    env, prev, rms = [], None, []
    for i in range(max(n, 0)):
        seg = samples[i * HOP: i * HOP + WIN]
        e = sum(x * x for x in seg) / WIN
        rms.append(math.sqrt(e))
        le = math.log(e + 1e-9)
        env.append(max(0.0, le - prev) if prev is not None else 0.0)
        prev = le
    return env, rms


def pick_onsets(env):
    if not env:
        return []
    mu, sd = statistics.mean(env), statistics.pstdev(env)
    thr = mu + 1.0 * sd
    out = []
    for i in range(1, len(env) - 1):
        if env[i] > thr and env[i] >= env[i - 1] and env[i] >= env[i + 1]:
            t = (i * HOP + WIN / 2) / SR
            if not out or t - out[-1] > 0.1:
                out.append(round(t, 3))
    return out


def tempo(env, lo=90, hi=180):
    """BPM by autocorrelation of the onset envelope, searched in [lo, hi] (avoids half-tempo)."""
    if len(env) < 50:
        return None
    mu = statistics.mean(env)
    x = [v - mu for v in env]
    hop_s = HOP / SR
    best, best_lag = -1e18, None
    for lag in range(int(60 / hi / hop_s), int(60 / lo / hop_s) + 2):
        r = sum(x[i] * x[i + lag] for i in range(len(x) - lag))
        # also reward the 2x lag (bar-level consistency) a little
        if 2 * lag < len(x):
            r += 0.5 * sum(x[i] * x[i + 2 * lag] for i in range(len(x) - 2 * lag))
        if r > best:
            best, best_lag = r, lag
    if not best_lag:
        return None
    # parabolic refinement
    return round(60 / (best_lag * hop_s), 1)


def near_ratio(cuts, onsets, tol):
    if not cuts or not onsets:
        return None
    hits = sum(1 for c in cuts if min(abs(c - o) for o in onsets) <= tol)
    return round(hits / len(cuts), 3)


def fade_out(rms, duration):
    """Length of the closing fade: time from the last 0.25 s window that is within 1 dB of the
    reel's median level to the end (0 if the reel ends at full level)."""
    if not rms:
        return None
    hop_s = HOP / SR
    w = max(1, int(0.25 / hop_s))
    db = [20 * math.log10(statistics.mean(rms[i:i + w]) + 1e-9) for i in range(0, len(rms) - w + 1, w)]
    if len(db) < 4:
        return 0.0
    med = statistics.median(db)
    last = max(i for i, d in enumerate(db) if d >= med - 1)
    tail = duration - (last + 1) * w * hop_s
    return round(max(0.0, tail), 2) if db[-1] < med - 6 else 0.0


def write_frames(path, shots, out_dir, fps):
    """first.jpg = frame 0 (the hook / thumbnail); sheet.jpg = the middle frame of every shot, in order."""
    os.makedirs(out_dir, exist_ok=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", path, "-frames:v", "1",
         "-vf", "scale=540:-2", os.path.join(out_dir, "first.jpg")])
    idx = sorted({int(round((sh["start"] + sh["len"] / 2) * fps)) for sh in shots})
    sel = "+".join(f"eq(n\\,{i})" for i in idx) or "eq(n\\,0)"
    cols = min(10, max(1, len(idx)))
    rows = max(1, math.ceil(len(idx) / cols))
    run(["ffmpeg", "-v", "error", "-y", "-i", path, "-an", "-vf",
         f"select='{sel}',scale=160:-2,tile={cols}x{rows}", "-frames:v", "1",
         os.path.join(out_dir, "sheet.jpg")])


def analyze(path, threshold=0.7, frames_dir=None, seed=7):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg/ffprobe not found on PATH")
    info = probe(path)
    frames = frame_stats(path)
    cuts = detect_cuts(path, info["fps"], threshold)
    shots = shots_from(cuts, info["duration"], frames)
    lens = [s["len"] for s in shots]
    res = dict(info)
    res.update({
        "cuts": cuts,
        "shot_count": len(shots),
        "shot_len": {"median": round(statistics.median(lens), 3), "min": min(lens), "max": max(lens)},
        "flash_bursts": flash_bursts(shots),
        "first_flash_burst_shots": (flash_bursts(shots) or [{"shots": 0}])[0]["shots"],
        "shots": shots,
        "look": {
            "luma_mean": round(statistics.mean(s["luma"] for s in shots if s["luma"] is not None), 1),
            "sat_mean": round(statistics.mean(s["sat"] for s in shots if s["sat"] is not None), 1),
            "warmth_mean": round(statistics.mean(s["warmth"] for s in shots if s["warmth"] is not None), 1),
            "night_share": round(sum(s["len"] for s in shots if s["luma"] is not None and s["luma"] < 70)
                                 / info["duration"], 2),
        },
    })
    if info["has_audio"]:
        samples = load_audio(path)
        env, rms = onset_envelope(samples)
        onsets = pick_onsets(env)
        bpm = tempo(env)
        tol = 1.0 / info["fps"] + 0.012
        rnd = random.Random(seed)
        base = [near_ratio([rnd.uniform(0, info["duration"]) for _ in cuts], onsets, tol) or 0
                for _ in range(200)] if cuts else []
        res["audio"] = {
            "bpm": bpm,
            "beats": round(info["duration"] * bpm / 60, 1) if bpm else None,
            "onsets": onsets,
            "cut_on_onset_ratio": near_ratio(cuts, onsets, tol),
            "random_baseline_ratio": round(statistics.mean(base), 3) if base else None,
            "tolerance_s": round(tol, 3),
            "fade_out_s": fade_out(rms, info["duration"]),
        }
        bursts = res["flash_bursts"]
        grid = label_grid(cuts, bpm, info["fps"], skip_until=bursts[0]["end"] if bursts else 0.0)
        if grid:
            res["audio"]["bpm_from_cuts"] = grid["bpm"]
            res["audio"]["beats"] = round(info["duration"] * grid["bpm"] / 60, 1)
            res["audio"]["cuts_on_half_beat_grid"] = len(grid["on_grid"])
            res["audio"]["cuts_off_grid"] = grid["off_grid"]  # in-shot flashes/strobes, or off-beat cuts
            beat = 60.0 / grid["bpm"]
            start = bursts[0]["end"] if bursts and bursts[0]["start"] < 0.5 else 0.0
            marks = [start] + [c for c in grid["on_grid"] if c > start + 0.05] + [info["duration"]]
            res["structure_beats"] = {
                "opener_burst_beats": round(start / beat * 2) / 2 if start else 0,
                "shots_after_opener": [round((b - a) / beat * 2) / 2 for a, b in zip(marks, marks[1:])],
            }
    else:
        res["audio"] = None
    if frames_dir:
        write_frames(path, shots, frames_dir, info["fps"])
        res["frames_dir"] = frames_dir
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--threshold", type=float, default=0.7, help="cut if frame correlation drops below this (higher = more cuts)")
    ap.add_argument("--frames", help="directory for first.jpg + sheet.jpg")
    ap.add_argument("--brief", action="store_true", help="omit per-shot and onset lists")
    a = ap.parse_args()
    r = analyze(a.video, a.threshold, a.frames)
    if a.brief:
        r.pop("shots", None)
        if r.get("audio"):
            r["audio"].pop("onsets", None)
    print(json.dumps(r, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
