"""Run from the repo root:  python3 -I -m unittest discover -s tests"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel):
    path = os.path.join(ROOT, rel)
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


beat_plan = load("skills/reel-maker/scripts/beat_plan.py")
shortcode = load("skills/trend-scout/scripts/shortcode.py")


class ShortcodeTest(unittest.TestCase):
    def test_known_id(self):
        self.assertEqual(shortcode.shortcode("4020836893606321669"), "DfM4dn3MJ4F")

    def test_small_ids(self):
        self.assertEqual(shortcode.shortcode(1), "B")
        self.assertEqual(shortcode.shortcode(64), "BA")


class BeatPlanTest(unittest.TestCase):
    def test_fit_exact_grid(self):
        period, phase = 0.5, 1.25
        markers = [[i, phase + period * i] for i in (0, 2, 4, 8)]
        p, ph = beat_plan.fit(markers)
        self.assertAlmostEqual(p, period, places=9)
        self.assertAlmostEqual(ph, phase, places=9)

    def test_fit_needs_two_markers(self):
        with self.assertRaises(ValueError):
            beat_plan.fit([[0, 1.0]])

    def test_trims_land_on_frame_grid(self):
        # 120 BPM (0.5 s/beat), 60 fps: one beat = 30 frames.
        clips = [{"id": "a", "start": 0.0, "end": 0.4},
                 {"id": "b", "start": 0.4, "end": 1.0},
                 {"id": "c", "start": 1.0, "end": 2.0}]
        changes, total, beats = beat_plan.plan_trims(clips, [1, "1/2", 2], 0.5, 60)
        self.assertEqual(total, 105)  # 3.5 beats * 30 frames
        self.assertEqual(beats, 3.5)
        by_id = {c[0]: c for c in changes}
        self.assertEqual(by_id["a"][1:3], (24, 30))
        self.assertAlmostEqual(by_id["a"][3], -0.1)   # extend by 0.1 s
        self.assertEqual(by_id["b"][1:3], (36, 15))
        self.assertAlmostEqual(by_id["b"][3], 0.35)   # shorten
        self.assertNotIn("c", by_id)                  # already 60 frames

    def test_fractional_beats_do_not_drift(self):
        # 14 flash shots across 4 beats must sum to exactly 4 beats.
        clips = [{"id": str(i), "start": 0, "end": 0} for i in range(14)]
        _, total, beats = beat_plan.plan_trims(clips, ["4/14"] * 14, 0.49333, 60)
        self.assertEqual(beats, 4.0)
        self.assertEqual(total, round(4 * 0.49333 * 60))

    def test_markers_file_raw_objects_and_window(self):
        import json, tempfile
        raw = {"estimatedBpm": 65.2, "markers": [
            {"index": i, "sourceSeconds": 1.0 + 0.458 * i, "isDownbeat": i % 8 == 0} for i in range(0, 200, 2)]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
        try:
            m = beat_plan.load_markers(f.name, [40, 60])
            self.assertTrue(m and all(40 <= t <= 60 for _, t in m))
            p, ph = beat_plan.fit(m)
            self.assertAlmostEqual(60 / p, 60 / 0.458, places=6)   # full tempo, not estimatedBpm
            self.assertEqual(len(beat_plan.load_markers(f.name)), 100)
        finally:
            os.unlink(f.name)

    def test_markers_file_accepts_pairs(self):
        import json, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump([[0, 1.0], [2, 2.0]], f)
        try:
            self.assertEqual(beat_plan.load_markers(f.name), [[0, 1.0], [2, 2.0]])
        finally:
            os.unlink(f.name)

    def test_place_mode_cumulative_frames(self):
        # 131 BPM-ish period, 60 fps: placements must be contiguous and end on the cumulative grid.
        period = 0.458
        shots = [{"alias": "a", "beats": "1/2", "sourceIn": 3.2},
                 {"alias": "b", "beats": "1/2", "sourceIn": 0},
                 {"alias": "c", "beats": 2}]
        pl, total, beats = beat_plan.plan_place(shots, period, 60)
        self.assertEqual(beats, 3.0)
        self.assertEqual(total, round(3 * period * 60))
        self.assertEqual(pl[0]["aliasIds"], ["a"])
        self.assertEqual(pl[0]["startTime"], 0)
        self.assertAlmostEqual(pl[0]["sourceIn"], 3.2)
        for prev, cur in zip(pl, pl[1:]):
            self.assertAlmostEqual(prev["startTime"] + prev["sourceOut"] - prev["sourceIn"], cur["startTime"], places=6)
        last = pl[-1]
        self.assertAlmostEqual(last["startTime"] + last["sourceOut"] - last["sourceIn"], total / 60, places=6)

    def test_length_mismatch(self):
        with self.assertRaises(ValueError):
            beat_plan.plan_trims([{"id": "a", "start": 0, "end": 1}], [1, 1], 0.5)


if __name__ == "__main__":
    unittest.main()
