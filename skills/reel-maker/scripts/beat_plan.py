#!/usr/bin/env python3
"""Beat planner for Edits timelines.

Usage:  python3 -I beat_plan.py plan.json

plan.json (all keys optional except what each mode needs):
{
  "fps": 60,                          # = getCanvas().frameRate (new Edits projects are 60)

  # Beat grid — one of:
  "markers_file": "/path/beatMarkers.json",  # raw `beatMarkers` output saved to a file (objects with
  "window": [40, 60],                        #   index/sourceSeconds); window = source-seconds range to fit
  "markers": [[62, 26.22], [70, 29.50]],     # or [beatIndex, sourceSeconds] pairs
  "period": 0.458,                           # or seconds per beat directly

  # Trim mode — retime clips already on the timeline:
  "clips": [{"id": "5B6B94F1-...", "start": 0.0, "end": 0.1333}, ...],
  "beats": ["4/14", "4/14", 2, 1],           # target length of each clip in beats (fractions ok)

  # Place mode — compute exact placement for a fresh build (music first, then shots):
  "shots": [{"alias": "ABC-123", "beats": "1/2", "sourceIn": 3.2}, ...]
}

Prints the fitted period/BPM (and phase if markers), then:
- trim mode: one `trimClip side=end delta` per clip whose duration must change
  (positive shortens, negative extends) + the new total;
- place mode: one `addMediaPanelItemsToTimeline` argument set per shot.
Boundaries are rounded to whole frames cumulatively, so cuts never drift off the grid.

Notes: Edits markers come every 2 beat-indexes; a bar starts every 4 beat-indexes
counted from index 0. `isDownbeat` flags are noisy — trust the fitted grid.
Ignore `estimatedBpm`/`audioOnsets.bpm` (both report half tempo); use the BPM printed here.
"""
import json
import sys
from fractions import Fraction


def fit(markers):
    """Least-squares line through [beatIndex, seconds] pairs -> (period, phase)."""
    xs = [float(i) for i, _ in markers]
    ys = [float(t) for _, t in markers]
    n = len(xs)
    if n < 2:
        raise ValueError("need at least 2 markers to fit a period")
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx  # period, source time of beat index 0


def load_markers(path, window=None):
    """Read raw `beatMarkers` JSON (dict with 'markers' objects, or a bare list) -> [[index, seconds]]."""
    with open(path) as f:
        d = json.load(f)
    items = d.get("markers", []) if isinstance(d, dict) else d
    out = []
    for m in items:
        if isinstance(m, dict):
            i, t = m["index"], m["sourceSeconds"]
        else:
            i, t = m[0], m[1]
        if window is None or window[0] <= t <= window[1]:
            out.append([i, t])
    return out


def _cum_frames(beats, period, fps):
    t, tgt = Fraction(0), [0]
    for b in beats:
        t += Fraction(b) if isinstance(b, str) else Fraction(str(b))
        tgt.append(round(float(t) * period * fps))
    return tgt, float(t)


def plan_trims(clips, beats, period, fps=60):
    """Return (changes, total_frames, total_beats).

    changes: list of (clip_id, old_frames, new_frames, trim_delta_seconds).
    trim_delta > 0 shortens the clip's end, < 0 extends it.
    """
    if len(clips) != len(beats):
        raise ValueError(f"clips ({len(clips)}) and beats ({len(beats)}) differ")
    cur = [round(c["start"] * fps) for c in clips] + [round(clips[-1]["end"] * fps)]
    tgt, total_beats = _cum_frames(beats, period, fps)
    changes = []
    for i, c in enumerate(clips):
        od, nd = cur[i + 1] - cur[i], tgt[i + 1] - tgt[i]
        if od != nd:
            changes.append((c["id"], od, nd, (od - nd) / fps))
    return changes, tgt[-1], total_beats


def plan_place(shots, period, fps=60):
    """Return (placements, total_frames, total_beats) for a fresh build.

    placements: dicts ready for addMediaPanelItemsToTimeline
    {aliasIds, startTime, sourceIn, sourceOut}, frame-exact and cumulative.
    """
    tgt, total_beats = _cum_frames([s["beats"] for s in shots], period, fps)
    out = []
    for i, s in enumerate(shots):
        f0, f1 = tgt[i], tgt[i + 1]
        src_in = round(float(s.get("sourceIn", 0)) * fps) / fps
        out.append({
            "aliasIds": [s["alias"]],
            "startTime": round(f0 / fps, 6),
            "sourceIn": round(src_in, 6),
            "sourceOut": round(src_in + (f1 - f0) / fps, 6),
        })
    return out, tgt[-1], total_beats


def main(path):
    with open(path) as f:
        plan = json.load(f)
    fps = plan.get("fps", 60)
    period = plan.get("period")
    markers = plan.get("markers")
    if plan.get("markers_file"):
        markers = load_markers(plan["markers_file"], plan.get("window"))
        print(f"loaded {len(markers)} markers from {plan['markers_file']}")
    if markers:
        p, phase = fit(markers)
        resid = max(abs(t - (phase + p * i)) for i, t in markers)
        print(f"fit: period={p:.5f}s  bpm={60/p:.2f}  beat0@{phase:.3f}s  max_residual={resid*1000:.0f}ms")
        print("     beat source times: beat_k = %.3f + %.5f*k  (bar starts every 4 beat-indexes from 0)" % (phase, p))
        period = period or p
    if not period:
        sys.exit("need period, markers or markers_file")
    try:
        if plan.get("shots"):
            placements, total, beats = plan_place(plan["shots"], period, fps)
            for pl in placements:
                print("addMediaPanelItemsToTimeline " + json.dumps(pl))
            print(f"{len(placements)} shot(s); total {total} frames = {total / fps:.4f}s "
                  f"({beats:g} beats = {beats / 4:g} bars)")
        if plan.get("clips"):
            changes, total, beats = plan_trims(plan["clips"], plan["beats"], period, fps)
            for cid, od, nd, delta in changes:
                print(f"{cid}  {od} -> {nd} frames  trimClip(side=end, delta={delta:.6f})")
            print(f"{len(changes)} clip(s) to trim; total {total} frames = {total / fps:.4f}s "
                  f"({beats:g} beats = {beats / 4:g} bars)")
    except ValueError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
