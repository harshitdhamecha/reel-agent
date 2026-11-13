#!/usr/bin/env python3
"""Rank clip-worthy moments in a long video from its transcript (+ optional loudness).

Usage:
  find_moments.py <transcript.json> [--audio <media>] [--loudness <lufs.json>]
                  [--min 15] [--max 45] [--top 8] [--offset 0]

Transcript formats accepted:
  - whisper.cpp `-oj` / `-ojf`: {"transcription":[{"offsets":{"from":ms,"to":ms},"text":...}, ...]}
  - generic segment list: [{"start":s,"end":s,"text":...}, ...] or {"segments":[...]}
--audio runs ffmpeg ebur128 to get momentary loudness (reaction/scream peaks).
--loudness takes a precomputed [[t_seconds, lufs], ...] list instead.
--offset is added to every output time (use the --download-sections start so times map to the VOD).

Output (stdout): JSON list ranked by score, each
  {start, end, dur, score, hook, payoff, text, reasons}
Claude makes the final pick; this only narrows a long transcript to candidates.
"""
import json
import re
import subprocess
import sys

HOOK_WORDS = {
    "never", "secret", "why", "how", "biggest", "worst", "best", "insane", "crazy", "wait",
    "bro", "nobody", "everyone", "actually", "truth", "mistake", "stop", "look", "watch",
    "imagine", "seriously", "literally", "first", "only", "hack", "trick", "wrong",
}
REACTION_WORDS = {
    "oh", "wow", "no", "yes", "what", "lets", "let's", "go", "omg", "god", "bro", "dude",
    "insane", "crazy", "unbelievable", "haha", "lol", "damn", "holy", "yo",
}
CONNECTIVES = {
    "and", "but", "so", "because", "which", "that", "then", "also", "or", "though",
    "he", "she", "it", "they", "this", "those", "these", "him", "her", "them",
}


def load_segments(path):
    with open(path) as f:
        d = json.load(f)
    segs = []
    if isinstance(d, dict) and "transcription" in d:
        for s in d["transcription"]:
            o = s.get("offsets", {})
            segs.append((o.get("from", 0) / 1000.0, o.get("to", 0) / 1000.0, s.get("text", "")))
    else:
        items = d.get("segments", d) if isinstance(d, dict) else d
        for s in items:
            segs.append((float(s["start"]), float(s["end"]), s.get("text", "")))
    out = []
    for a, b, t in segs:
        t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", t)  # drop [Music], (laughs) tags
        t = re.sub(r"\s+", " ", t).strip()
        if t and b > a:
            out.append((a, b, t))
    return out


def ebur128(media):
    """Momentary loudness [(t, lufs)] via ffmpeg ebur128 (one line per 100 ms)."""
    p = subprocess.run(
        ["ffmpeg", "-nostats", "-hide_banner", "-i", media, "-vn", "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    pts = []
    for m in re.finditer(r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(-?[\d.]+|-inf)", p.stderr):
        if m.group(2) != "-inf":
            pts.append((float(m.group(1)), float(m.group(2))))
    return pts


def words(t):
    return re.findall(r"[a-zA-Z']+", t.lower())


def hook_score(text):
    w = words(text)
    s = 0.0
    if "?" in text:
        s += 1.0
    if re.search(r"\d", text):
        s += 0.5
    s += 0.6 * min(2, sum(1 for x in w if x in HOOK_WORDS))
    if "you" in w or "your" in w:
        s += 0.4
    if 3 <= len(w) <= 14:
        s += 0.5
    if w and w[0] in CONNECTIVES:
        s -= 1.5
    return s


def payoff_score(text):
    w = words(text)
    s = 0.0
    if re.search(r"[.!?]\s*$", text):
        s += 0.8
    if "!" in text:
        s += 0.5
    s += 0.4 * min(3, sum(1 for x in w if x in REACTION_WORDS))
    return s


def rank(segs, loud=None, lo=15.0, hi=45.0, top=8, offset=0.0):
    base = None
    if loud:
        vals = sorted(v for _, v in loud)
        base = vals[len(vals) // 2]
    cands = []
    n = len(segs)
    for i in range(n):
        for j in range(i, n):
            a, b = segs[i][0], segs[j][1]
            dur = b - a
            if dur > hi:
                break
            if dur < lo:
                continue
            first, last = segs[i][2], segs[j][2]
            body = " ".join(s[2] for s in segs[i:j + 1])
            h, p = hook_score(first), payoff_score(last)
            reasons = []
            score = 1.5 * h + 1.2 * p
            if h >= 1.5:
                reasons.append("strong hook")
            if not re.search(r"[.!?]\s*$", last):
                score -= 1.0
                reasons.append("ends mid-sentence")
            wps = len(words(body)) / dur
            score += min(1.0, max(0.0, (wps - 1.8) / 1.5))  # energetic delivery
            if loud:
                win = [v for t, v in loud if a <= t <= b]
                peaks = sum(1 for v in win if v > base + 8)
                tail = [v for t, v in loud if b - dur / 3 <= t <= b]
                if peaks:
                    score += min(1.5, peaks / 10.0)
                    reasons.append(f"{peaks} loud moments")
                if tail and max(tail) > base + 10:
                    score += 0.7
                    reasons.append("reaction near the end")
            # prefer ~20-35 s
            score -= 0.03 * max(0.0, abs(dur - 27) - 8)
            cands.append({
                "start": round(a + offset, 2), "end": round(b + offset, 2), "dur": round(dur, 2),
                "score": round(score, 2), "hook": first, "payoff": last,
                "text": body[:400], "reasons": reasons,
            })
    cands.sort(key=lambda c: -c["score"])
    picked = []
    for c in cands:
        if all(c["end"] <= q["start"] or c["start"] >= q["end"] for q in picked):
            picked.append(c)
        if len(picked) >= top:
            break
    return picked


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = argv[0]
    opts = {"--min": 15.0, "--max": 45.0, "--top": 8, "--offset": 0.0}
    audio = loudf = None
    i = 1
    while i < len(argv):
        k = argv[i]
        v = argv[i + 1] if i + 1 < len(argv) else None
        if k == "--audio":
            audio = v
        elif k == "--loudness":
            loudf = v
        elif k in opts:
            opts[k] = type(opts[k])(v)
        else:
            print(f"unknown option {k}", file=sys.stderr)
            return 2
        i += 2
    segs = load_segments(path)
    loud = None
    if loudf:
        with open(loudf) as f:
            loud = [tuple(x) for x in json.load(f)]
    elif audio:
        loud = ebur128(audio)
    res = rank(segs, loud, opts["--min"], opts["--max"], opts["--top"], opts["--offset"])
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
