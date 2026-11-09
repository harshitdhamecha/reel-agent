---
name: style-coach
description: Train the reel agent on a user's own taste. Use when the user says "learn my style", "train it on my reels", gives reels they made or love as references, answers style questions, or after any reel feedback ("no zoom on photos", "caption too salesy", "I posted v3"). Measures reference reels (cuts, beat structure, tempo, grade, caption, fade), runs a short interview, and writes/merges ~/.claude/reel-agent/style.md that reel-maker reads before every reel.
---

# style-coach

Turns "what I like" into a style profile reel-maker follows: `~/.claude/reel-agent/style.md`.
Order of authority: **what the user said** > **feedback on real reels** > **measured from reference reels** > `reel-maker/style.example.md` defaults.

Run modes:
- **learn** — user gives 1–10 reels (their own exports, or reels they love saved locally) → measure → interview → write profile.
- **interview only** — no reels yet → 6 questions → profile on top of the example defaults.
- **feedback** — called by reel-maker after each round of feedback or when a reel is posted → update rules.

## 1. Measure reference reels
For each file (MP4/MOV, local path; Edits can only read `~/Movies`, the script can read anywhere):

```
python3 -I "<this skill's folder>/scripts/analyze_reel.py" <reel.mp4> --brief --frames <scratch>/<name>
```
JSON out (ffmpeg only, no Edits needed):
- `duration`, `fps`, `has_audio`
- `cuts` (normalised frame correlation — brightness flicker ignored), `shot_count`, `shot_len`
- `flash_bursts` — runs of ≥3 shots < 0.3 s (the "flash montage" opener when it starts at 0)
- `audio.bpm` (onset autocorrelation, 90–180 range), `audio.bpm_from_cuts` (half-beat grid fitted to the cuts — more precise when the reel is cut on beat), `audio.beats`, `audio.cuts_on_half_beat_grid`, `audio.cuts_off_grid` (in-shot strobes/flashes or off-beat cuts), `audio.cut_on_onset_ratio` vs `audio.random_baseline_ratio` (on-beat only means something if clearly above baseline), `audio.fade_out_s`
- `structure_beats` — `opener_burst_beats` + `shots_after_opener` in beats (e.g. `[2,2,2,1,1,…,4]`) — the reel's skeleton
- `look` — `luma_mean` (0–255), `sat_mean`, `warmth_mean` (V−U chroma; > 0 warmer), `night_share` (fraction of time with luma < 70)
- `frames/first.jpg` (hook / thumbnail) and `frames/sheet.jpg` (middle frame of every shot)

Then **Read `first.jpg` and `sheet.jpg`** and note: caption text, font look (serif/sans, weight), position (upper/middle/lower), static vs changing between shots, emoji use; hook type (prettiest still, action, face, text); content mix (people vs scenery, POV, food, night); B&W or other bridges; anything repeated across reels.

Cross-checks (optional, if the Edits MCP is connected): `detectCuts {id:"", path, start:0, duration, sensitivity:0.5}` — precise in flash montages but over-triggers on stage lights/strobes (one trial: 56 cuts vs 35 real); `audioOnsets` for tempo (its `bpm` is half-tempo — double it). Song identity can't be measured: ask, or read the reel's caption/metadata.

Known limits: two consecutive near-identical shots can merge into one; dark club footage with strobes yields false cuts (they land in `cuts_off_grid`); `fade_out_s` slightly under-reads gentle fades.

Measured on a known reel (13.8 s, 28 beats @ 121.6 BPM, 14-shot flash opener, 1.5 s fade): 27.9 beats @ 121.4 BPM, 13 opener shots in 4.0 beats, structure `[4 | 2,2,2,1,…,4]` exact, fade 1.05 s, 4 strobe cuts flagged off-grid.

## 2. Interview (≤ 6 questions, one round)
Use multiple choice (AskUserQuestion if available). Skip any question the reels already answered clearly; say what you measured instead ("your 3 reels all open with a flash montage — keeping that").
1. **Vibe** — energetic party / calm aesthetic / cinematic story / funny-candid
2. **Caption** — recap ("Goa diaries") / invitation ("Goa together?") / one-word or place / no text
3. **Music** — trending international hooks / regional classics (e.g. Bollywood) / I'll pick each time
4. **Camera moves on photos** — none (static) / subtle zoom / anything goes
5. **People vs scenery** — mostly scenery & vibe / candid people ok / posed group shots welcome
6. **Length** — 7–10 s / 11–15 s / 15–30 s

## 3. Write / merge the profile
- Path: `~/.claude/reel-agent/style.md` (create the folder). If it doesn't exist, start from `reel-maker/style.example.md`'s **section layout** (Reference reel · Music · Caption · Structure & pacing · Visual · Working style) but replace its content with this user's rules.
- **Every rule carries its evidence in brackets**:
  `(user said, 2026-11-09)` · `(feedback on v3, 2026-11-09)` · `(measured: 3/3 reels)` · `(measured: 1 reel — weak)` · `(default, unconfirmed)`
- Measured rules: write numbers the build can use — length in s and beats, BPM range, opener shots/beats, beats per shot by section, grade warmth sign, caption position as y≈0.2/0.5/0.8.
- Authority: never let a measured rule overwrite a `user said` or `feedback` rule. If they conflict, keep the user's rule and add "(reference reels differ: …)".
- If the profile already exists: show the **diff** (added / changed / removed lines) and ask once before writing changes to user-stated rules. Measured/default additions can be written directly.
- Keep it short (≤ 60 lines). Merge, don't append duplicates.

## 4. Feedback loop (called by reel-maker)
After each round of feedback on a reel, and when the user says a version was posted:
1. Turn each piece of feedback into a rule **in the user's words** + why: "No camera moves on photos — 'I don't like that panning' (feedback on v4, 2026-11-07)".
2. If it contradicts an existing rule, **revise that rule in place** (keep the history in one clause: "was: animated captions; rejected v8") — never keep both.
3. Approval is evidence too: "kept" / "posted" → mark the rule `(confirmed: posted v9)`; set the posted reel as **Reference reel** with its numbers (length, beats, BPM, song + section, opener, caption, fade) — run `analyze_reel.py` on the export to fill them.
4. Mechanics (tool quirks) don't belong here — they go in reel-maker's SKILL.md.
5. Tell the user in one line what was learned: "Saved: no zoom on photos; recap captions."

## Privacy
The profile is personal: it stays in `~/.claude/reel-agent/` and is git-ignored in this repo. Don't copy footage or frames into the repo.
