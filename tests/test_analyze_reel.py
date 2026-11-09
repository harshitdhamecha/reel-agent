"""Run from the repo root:  python3 -I -m unittest discover -s tests

Builds a synthetic reel with ffmpeg (colour/noise segments with known cut times, a 120 BPM click
track and a 1 s fade-out) and checks analyze_reel.py measures it. Skipped if ffmpeg is missing.
"""
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "analyze_reel", os.path.join(ROOT, "skills/style-coach/scripts/analyze_reel.py"))
ar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ar)

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
FPS = 60
# segment lengths in seconds: 4 flashes (0.25 s = ½ beat @120) then 1-beat and 2-beat shots, 2 s hold
SEGS = [0.25, 0.25, 0.25, 0.25, 1.0, 0.5, 0.5, 1.0, 2.0]


def make_reel(path):
    # Every segment = testsrc2 with a different transform, so normalised correlation sees a hard cut.
    looks = ["null", "hflip", "vflip", "negate", "edgedetect", "hflip,vflip", "negate,hflip",
             "vflip,negate", "transpose=2,scale=270:480"]
    inputs, labels = [], []
    for i, (fx, d) in enumerate(zip(looks, SEGS)):
        inputs += ["-f", "lavfi", "-i", f"testsrc2=size=270x480:rate={FPS}:duration={d}"]
        labels.append(f"[{i}:v]{fx},format=yuv420p,setsar=1[v{i}]")
    total = sum(SEGS)
    n = len(SEGS)
    # 120 BPM clicks: 5 ms 1 kHz burst every 0.5 s, then a 1 s fade-out at the end
    click = (f"aevalsrc='if(lt(mod(t\\,0.5)\\,0.03)\\,0.8*sin(2*PI*1000*t)\\,0.05*sin(2*PI*220*t))'"
             f":s=44100:d={total}")
    inputs += ["-f", "lavfi", "-i", click]
    fc = ";".join(labels) + ";" + "".join(f"[v{i}]" for i in range(n)) + \
        f"concat=n={n}:v=1:a=0[v];[{n}:a]afade=t=out:st={total - 1}:d=1[a]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fc,
                    "-map", "[v]", "-map", "[a]", "-pix_fmt", "yuv420p", path], check=True)


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class AnalyzeReelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.path = os.path.join(cls.tmp, "synthetic.mp4")
        make_reel(cls.path)
        cls.r = ar.analyze(cls.path, frames_dir=os.path.join(cls.tmp, "frames"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_duration_and_audio(self):
        self.assertAlmostEqual(self.r["duration"], sum(SEGS), delta=0.1)
        self.assertTrue(self.r["has_audio"])

    def test_cuts_match_known_times(self):
        want, t = [], 0.0
        for d in SEGS[:-1]:
            t += d
            want.append(t)
        got = self.r["cuts"]
        self.assertEqual(len(got), len(want), got)
        for g, w in zip(got, want):
            self.assertLessEqual(abs(g - w), 1.5 / FPS)

    def test_flash_burst_opener(self):
        b = self.r["flash_bursts"][0]
        self.assertEqual(b["start"], 0.0)
        self.assertEqual(b["shots"], 4)

    def test_tempo_and_grid(self):
        a = self.r["audio"]
        self.assertAlmostEqual(a["bpm"], 120, delta=3)
        self.assertAlmostEqual(a["bpm_from_cuts"], 120, delta=1)
        self.assertEqual(a["cuts_off_grid"], [])
        self.assertEqual(self.r["structure_beats"]["opener_burst_beats"], 2.0)
        self.assertEqual(self.r["structure_beats"]["shots_after_opener"], [2.0, 1.0, 1.0, 2.0, 4.0])

    def test_fade_detected(self):
        self.assertGreater(self.r["audio"]["fade_out_s"], 0.4)

    def test_frames_written(self):
        for f in ("first.jpg", "sheet.jpg"):
            self.assertTrue(os.path.getsize(os.path.join(self.tmp, "frames", f)) > 1000)


class GridUnitTest(unittest.TestCase):
    def test_label_grid_recovers_tempo_and_flags_strobe(self):
        beat = 60 / 121.6
        cuts = [round(2 + k * beat, 3) for k in range(12)] + [5.1]   # 5.1 = in-shot strobe
        g = ar.label_grid(sorted(cuts), 124.0, 60)
        self.assertAlmostEqual(g["bpm"], 121.6, delta=0.3)
        self.assertEqual(g["off_grid"], [5.1])


if __name__ == "__main__":
    unittest.main()
