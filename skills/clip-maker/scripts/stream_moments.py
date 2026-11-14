#!/usr/bin/env python3
"""Rank the best moments of a long YouTube VOD *without downloading it*.

Uses what viewers already marked:
  * heatmap   - YouTube "Most replayed" curve (100 bins over the video)
  * comments  - timestamps people type in top comments ("7:43:08 the switch from 😂 to 🤨"),
                weighted by likes; comments with >2 timestamps are chapter lists and skipped
  * chat      - live-chat replay spikes (--chat), the only signal on a stream that just ended
  * chapters  - only used to label windows

Usage:
  stream_moments.py <youtube-url> [--top 10] [--comments 400] [--pad-before 20] [--pad-after 40]
  stream_moments.py --info vod.info.json   # reuse a `yt-dlp -J --write-comments` dump

Prints JSON: windows sorted by score, each with start/end, a yt-dlp
`--download-sections` string, signals and the best comment as a hook idea.
Then download only those windows at 1080p and run the normal clip-maker flow.
"""
import argparse
import json
import math
import re
import subprocess
import sys

NAV = re.compile(r"(start|starts|started|begin|begins|skip|from here|se shuru|yaha se|here)\b", re.I)
TS = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])")


def hms(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def fetch_info(url, max_comments):
    cmd = ["yt-dlp", "--skip-download", "-J", "--write-comments",
           "--extractor-args", f"youtube:comment_sort=top;max_comments={max_comments},{max_comments},0,0", url]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def comment_points(comments, duration):
    """-> list of (t_seconds, weight, likes, text) from comments with 1-2 timestamps."""
    pts = []
    for c in comments or []:
        text = c.get("text") or ""
        ms = list(TS.finditer(text))
        if not 1 <= len(ms) <= 2:
            continue
        likes = c.get("like_count") or 0
        for m in ms:
            h, mi, s = m.groups()
            if int(s) > 59 or (h and int(mi) > 59):
                continue
            t = int(h or 0) * 3600 + int(mi) * 60 + int(s)
            if duration and t >= duration:
                continue
            w = 1.0 + 2.0 * math.log2(1 + likes / 10.0)
            if NAV.search(text):  # "match starts from here" = navigation, not a moment
                w *= 0.15
            pts.append((t, w, likes, " ".join(text.split())[:120]))
    return pts


def heatmap_peaks(heatmap, min_value=0.3):
    """Local maxima of the replay curve above min_value -> (start, end, value)."""
    hm = heatmap or []
    peaks = []
    for i, p in enumerate(hm):
        v = p.get("value", 0)
        if v < min_value:
            continue
        left = hm[i - 1]["value"] if i > 0 else -1
        right = hm[i + 1]["value"] if i + 1 < len(hm) else -1
        if v >= left and v >= right:
            peaks.append((p["start_time"], p["end_time"], v))
    return peaks


def chat_peaks(lines, bin_s=30, min_ratio=1.5, top=15):
    """Live-chat replay lines (yt-dlp `--write-subs --sub-langs live_chat`) -> [(t, ratio)].
    Bins messages per bin_s seconds; returns bins at >= min_ratio x the median rate."""
    import statistics
    bins = {}
    for line in lines:
        try:
            a = json.loads(line).get("replayChatItemAction", {})
            t = int(a.get("videoOffsetTimeMsec", -1)) // 1000
        except (ValueError, AttributeError):
            continue
        if t >= 0:
            bins[t // bin_s] = bins.get(t // bin_s, 0) + 1
    if len(bins) < 5:
        return []
    med = statistics.median(bins.values()) or 1
    peaks = [(k * bin_s, n / med) for k, n in bins.items() if n / med >= min_ratio]
    return sorted(peaks, key=lambda p: -p[1])[:top]


def chapter_at(chapters, t):
    for ch in chapters or []:
        if ch.get("start_time", 0) <= t < ch.get("end_time", 1e12):
            return ch.get("title")
    return None


def rank(info, top=10, pad_before=20, pad_after=40, min_heat=0.3, chat=None):
    duration = info.get("duration") or 0
    windows = []  # dicts with t (anchor), score, signals

    # comment clusters: merge points within 45 s
    pts = sorted(comment_points(info.get("comments"), duration))
    cluster = []
    def flush():
        if not cluster:
            return
        best = max(cluster, key=lambda p: p[2])
        windows.append({"anchor": best[0], "first": cluster[0][0], "last": cluster[-1][0],
                        "score": sum(p[1] for p in cluster),
                        "signals": [f"{len(cluster)} timestamp comment(s), top {best[2]} likes"],
                        "hook_idea": best[3]})
    for p in pts:
        if cluster and p[0] - cluster[-1][0] > 45:
            flush()
            cluster = []
        cluster.append(p)
    flush()

    # heatmap peaks: boost overlapping comment windows, else add a coarse window
    for s, e, v in heatmap_peaks(info.get("heatmap"), min_heat):
        hit = [w for w in windows if s - 30 <= w["anchor"] <= e + 30]
        if hit:
            for w in hit:
                w["score"] += 10 * v
                w["signals"].append(f"most-replayed peak {v:.2f}")
        else:
            windows.append({"anchor": (s + e) / 2, "first": s, "last": e, "score": 10 * v,
                            "signals": [f"most-replayed peak {v:.2f} (coarse {int(e - s)} s bin: transcribe it to find the exact moment)"],
                            "hook_idea": None})

    # chat spikes: freshest signal (exists the minute the stream ends)
    for t, ratio in chat or []:
        hit = [w for w in windows if t - 45 <= w["anchor"] <= t + 75]
        if hit:
            for w in hit:
                w["score"] += 4 * ratio
                w["signals"].append(f"chat spike {ratio:.1f}x")
        else:
            # chat reacts ~10-30 s after the moment: anchor a bit earlier
            windows.append({"anchor": t, "first": max(0, t - 20), "last": t + 30, "score": 4 * ratio,
                            "signals": [f"chat spike {ratio:.1f}x"], "hook_idea": None})

    out = []
    for w in sorted(windows, key=lambda w: -w["score"])[:top]:
        start = max(0, min(w["first"], w["anchor"]) - pad_before)
        end = max(w["last"], w["anchor"]) + pad_after
        if duration:
            end = min(end, duration)
        out.append({"start": round(start), "end": round(end),
                    "section": f"*{hms(start)}-{hms(end)}",
                    "score": round(w["score"], 1), "chapter": chapter_at(info.get("chapters"), w["anchor"]),
                    "signals": w["signals"], "hook_idea": w["hook_idea"]})
    return {"id": info.get("id"), "title": info.get("title"), "channel": info.get("channel"),
            "duration": duration, "views": info.get("view_count"),
            "has_heatmap": bool(info.get("heatmap")), "comments_read": len(info.get("comments") or []),
            "chat_peaks": len(chat or []),
            "windows": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?")
    ap.add_argument("--info", help="existing yt-dlp info JSON (with comments)")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--comments", type=int, default=400)
    ap.add_argument("--pad-before", type=float, default=20)
    ap.add_argument("--pad-after", type=float, default=40)
    ap.add_argument("--min-heat", type=float, default=0.3)
    ap.add_argument("--chat", help="live chat replay file (*.live_chat.json) for chat-spike moments")
    a = ap.parse_args(argv)
    if not a.url and not a.info:
        ap.error("give a URL or --info")
    info = json.load(open(a.info)) if a.info else fetch_info(a.url, a.comments)
    chat = chat_peaks(open(a.chat, errors="ignore")) if a.chat else None
    json.dump(rank(info, a.top, a.pad_before, a.pad_after, a.min_heat, chat), sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
