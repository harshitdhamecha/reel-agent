import importlib.util
import pathlib
import unittest

P = pathlib.Path(__file__).resolve().parents[1] / "skills/clip-maker/scripts/stream_moments.py"
spec = importlib.util.spec_from_file_location("stream_moments", P)
sm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sm)


def info():
    hm = [{"start_time": i * 100, "end_time": (i + 1) * 100, "value": 0.1} for i in range(100)]
    hm[30]["value"] = 1.0   # 3000-3100, no comments there
    hm[77]["value"] = 0.6   # 7700-7800, overlaps a comment
    return {
        "id": "x", "duration": 10000, "heatmap": hm,
        "chapters": [{"start_time": 0, "end_time": 5000, "title": "A"}, {"start_time": 5000, "end_time": 10000, "title": "B"}],
        "comments": [
            {"text": "2:08:20 the switch is hilarious", "like_count": 170},  # 7700
            {"text": "2:08:40 lol", "like_count": 0},                         # 7720 -> same cluster
            {"text": "0:00 intro 1:00 a 2:00 b 3:00 c", "like_count": 999},  # chapter list, skipped
            {"text": "12:61 not a time", "like_count": 50},
            {"text": "9:59:59 past the end", "like_count": 50},
            {"text": "5:00 ok", "like_count": 0},
        ],
    }


class T(unittest.TestCase):
    def test_comment_points_skip_lists_and_invalid(self):
        pts = sm.comment_points(info()["comments"], 10000)
        self.assertEqual(sorted(p[0] for p in pts), [300, 7700, 7720])

    def test_rank_merges_and_boosts(self):
        r = sm.rank(info(), top=5)
        w = r["windows"]
        self.assertEqual(w[0]["chapter"], "B")
        self.assertIn("hilarious", w[0]["hook_idea"])
        self.assertTrue(any("most-replayed" in s for s in w[0]["signals"]))
        self.assertEqual(w[0]["start"], 7680)
        self.assertEqual(w[0]["end"], 7760)
        self.assertEqual(w[0]["section"], "*2:08:00-2:09:20")
        coarse = [x for x in w if x["hook_idea"] is None]
        self.assertEqual(len(coarse), 1)
        self.assertEqual(coarse[0]["chapter"], "A")

    def test_no_heatmap_ok(self):
        i = info(); i["heatmap"] = None
        self.assertFalse(sm.rank(i)["has_heatmap"])


class Chat(unittest.TestCase):
    def test_chat_peaks_and_rank(self):
        import json
        lines = []
        for t in range(0, 600):
            n = 10 if 300 <= t < 330 else 1
            lines += [json.dumps({"replayChatItemAction": {"videoOffsetTimeMsec": str(t * 1000)}})] * n
        lines.append("garbage")
        peaks = sm.chat_peaks(lines)
        self.assertEqual(peaks[0][0], 300)
        r = sm.rank({"duration": 600, "comments": [], "heatmap": None}, chat=peaks)
        self.assertIn("chat spike", r["windows"][0]["signals"][0])
        self.assertEqual(r["chat_peaks"], 1)


if __name__ == "__main__":
    unittest.main()
