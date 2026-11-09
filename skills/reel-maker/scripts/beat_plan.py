#!/usr/bin/env python3
"""Beat planner for Edits timelines.

Usage:  python3 -I beat_plan.py plan.json

plan.json:
{
  "fps": 60,
  "markers": [[62, 26.22], [70, 29.50], [86, 36.76]],   # optional: [beatIndex, sourceSeconds] from `beatMarkers`
  "period": 0.493333,                                   # optional if markers given (seconds per beat)
  "clips": [                                            # main-track clips in order, current timing
    {"id": "5B6B94F1-...", "start": 0.0,   "end": 0.1333},
    {"id": "BED7E582-...", "start": 0.1333, "end": 0.2667}
  ],
  "beats": ["4/14", "4/14", 2, 1]                        # target length of each clip in beats (fractions ok)
}

Prints: fitted period/BPM (and phase if markers), then one line per clip whose
duration must change, with the `trimClip side=end delta` to apply (positive
shortens, negative extends), then the new total length. Boundaries are rounded
to whole frames cumulatively, so cuts never drift off the grid.
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


def plan_trims(clips, beats, period, fps=60):
    """Return (changes, total_frames, total_beats).

    changes: list of (clip_id, old_frames, new_frames, trim_delta_seconds).
    trim_delta > 0 shortens the clip's end, < 0 extends it.
    """
    if len(clips) != len(beats):
        raise ValueError(f"clips ({len(clips)}) and beats ({len(beats)}) differ")
    cur = [round(c["start"] * fps) for c in clips] + [round(clips[-1]["end"] * fps)]
    t, tgt = Fraction(0), [0]
    for b in beats:
        t += Fraction(b) if isinstance(b, str) else Fraction(str(b))
        tgt.append(round(float(t) * period * fps))
    changes = []
    for i, c in enumerate(clips):
        od, nd = cur[i + 1] - cur[i], tgt[i + 1] - tgt[i]
        if od != nd:
            changes.append((c["id"], od, nd, (od - nd) / fps))
    return changes, tgt[-1], float(t)


def main(path):
    with open(path) as f:
        plan = json.load(f)
    fps = plan.get("fps", 60)
    period = plan.get("period")
    if plan.get("markers"):
        p, phase = fit(plan["markers"])
        resid = max(abs(t - (phase + p * i)) for i, t in plan["markers"])
        print(f"fit: period={p:.5f}s  bpm={60/p:.2f}  beat0@{phase:.3f}s  max_residual={resid*1000:.0f}ms")
        print("     downbeat source times: beat_k = %.3f + %.5f*k" % (phase, p))
        period = period or p
    if not period:
        sys.exit("need period or markers")
    try:
        changes, total, beats = plan_trims(plan["clips"], plan["beats"], period, fps)
    except ValueError as e:
        sys.exit(str(e))
    for cid, od, nd, delta in changes:
        print(f"{cid}  {od} -> {nd} frames  trimClip(side=end, delta={delta:.6f})")
    print(f"{len(changes)} clip(s) to trim; total {total} frames = {total / fps:.4f}s "
          f"({beats:g} beats = {beats / 4:g} bars)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
