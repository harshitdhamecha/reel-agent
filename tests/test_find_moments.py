"""Run from the repo root:  python3 -I -m unittest discover -s tests"""
import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_p = os.path.join(ROOT, "skills/clip-maker/scripts/find_moments.py")
_s = importlib.util.spec_from_file_location("find_moments", _p)
fm = importlib.util.module_from_spec(_s)
_s.loader.exec_module(fm)


def seg_list():
    # 0-60 s filler, then a strong hook + payoff window at 60-85 s, then filler.
    segs = []
    t = 0.0
    for _ in range(12):
        segs.append({"start": t, "end": t + 5, "text": "and then we kind of continued with the setup"})
        t += 5
    segs += [
        {"start": 60, "end": 64, "text": "Why does nobody talk about this insane trick?"},
        {"start": 64, "end": 72, "text": "You take the light, you push it behind the subject, and you bake it."},
        {"start": 72, "end": 80, "text": "It renders four times faster on the same machine."},
        {"start": 80, "end": 85, "text": "Oh wow, that is crazy!"},
    ]
    t = 85.0
    for _ in range(12):
        segs.append({"start": t, "end": t + 5, "text": "which we then exported to the next step"})
        t += 5
    return segs


class FindMoments(unittest.TestCase):
    def write(self, obj):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(obj, f)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_best_window_is_hook_to_payoff(self):
        segs = fm.load_segments(self.write(seg_list()))
        best = fm.rank(segs, top=3)[0]
        self.assertEqual(best["start"], 60.0)
        self.assertEqual(best["end"], 85.0)
        self.assertIn("nobody", best["hook"])

    def test_whisper_cpp_format_and_offset(self):
        wc = {"transcription": [
            {"offsets": {"from": int(s["start"] * 1000), "to": int(s["end"] * 1000)}, "text": " " + s["text"]}
            for s in seg_list()]}
        segs = fm.load_segments(self.write(wc))
        best = fm.rank(segs, top=1, offset=120)[0]
        self.assertEqual((best["start"], best["end"]), (180.0, 205.0))

    def test_windows_respect_bounds_and_do_not_overlap(self):
        segs = fm.load_segments(self.write(seg_list()))
        res = fm.rank(segs, lo=15, hi=45, top=6)
        for c in res:
            self.assertGreaterEqual(c["dur"], 15)
            self.assertLessEqual(c["dur"], 45)
        for i, a in enumerate(res):
            for b in res[i + 1:]:
                self.assertTrue(a["end"] <= b["start"] or a["start"] >= b["end"])

    def test_loudness_peak_boosts_reaction_window(self):
        segs = fm.load_segments(self.write(seg_list()))
        loud = [(t / 10.0, -30.0) for t in range(0, 1450)]
        loud = [(t, -12.0 if 120 <= t <= 124 else v) for t, v in loud]  # scream late in filler
        res = fm.rank(segs, loud=loud, top=8)
        hit = [c for c in res if c["start"] <= 122 <= c["end"]]
        self.assertTrue(hit and any("loud" in r for r in hit[0]["reasons"]))

    def test_strips_bracket_tags(self):
        segs = fm.load_segments(self.write([{"start": 0, "end": 2, "text": "[Music] hello (laughs)"}]))
        self.assertEqual(segs[0][2], "hello")


if __name__ == "__main__":
    unittest.main()
