# Example style profile — "beach-trip recap montage"

This is an **example**, learned from one real user over 9 versions of a Goa (India) beach-trip reel that was posted.
On first use, reel-maker copies it to `~/.claude/reel-agent/style.md` (personal, outside the plugin) and lets the user's feedback overwrite it.

## Reference reel
13.8 s · 28 beats (7 bars) at ~122 BPM · licensed dance track ("Jamaican (Bam Bam)" by HUGEL & SOLTO) starting on a downbeat inside its popular section ·
flash-montage opener · one static caption "<Place> diaries" + 🌴 🍹 🌅 🪩 · 1.5 s music fade-out.

## Music
- **A real, recognisable song** from the Edits licensed library. Royalty-free stock was rejected ("why can't we use some real song?").
- Judge a track by whether it "does justice to start and end": a strong hit on frame 1 and a resolved ending. An upbeat dance track beat a nostalgic Bollywood classic that "felt incomplete".
- Start on a downbeat at/near the track's popular segment (`highlights`), end on a full bar, fade out ~1.5 s.
- Offer 2–3 candidates; build one; keep each song version as its own project so the user can flip back.
- **The user does the hearing.** Claude shortlists by data; the user judges by ear.

### How to shortlist songs
1. **Trend signal** — the song on top-performing reels in the niche (trend-scout). Prefer songs used by ≥2 well-performing reels, by the niche's leading creator, or with a rising reel count on their audio page.
2. **Place/occasion classic** — a song the audience already ties to the destination or event. Instant recognition.
3. **Licensed + usable** — exists in the Edits library as licensed (`obfuscatedWindow`); has `highlights`; steady `beatMarkers` in that section; ~115–135 BPM suits 1-beat cuts of 0.45–0.5 s.
4. **Pitch each in one line** — why it fits (trend / place / energy), BPM, which section — build the strongest, let the user listen. Don't argue taste.

## Caption
- **One static caption for the whole reel.** No entrance animation, no per-section captions (rejected: "days like this / nights like that", stamp/typewriter effects).
- Thin serif preset (Edits `SUNDAY MORNING`), white, size ~40, centred, y ≈ 0.22 (upper area, clear of faces and the Reels UI).
- Two lines: `<Place> diaries` + an emoji row.
- **Recap tone, not invitation** for a trip already taken ("<Place> together?" felt wrong). **No dates** — footage mixed months.

## Structure & pacing (11–14 s)
1. **Flash montage, first 4 beats:** ~14 shots, day + night mixed. Frame 1 = the prettiest still — it is the thumbnail.
2. **Arrival** (plane window) 2 beats → **road POV** (scooter/car) 2 beats → **scenic** 1–2 beats.
3. **Golden hour** stills/clips, 1 beat each → blue hour.
4. **Night-in** beat → a black-and-white bridge shot (day→night).
5. **Night** cuts, 1 beat each.
6. **Ending hold** 4 beats on a warm wide shot, under the fade.
- Every cut frame-exact on the song's beat grid.

## Visual
- **No camera moves on photos** (a Ken Burns pan was rejected). Static fill/crop only.
- Posed group selfies were cut; prefer vibe/scenery/candid shots. Ask before featuring a posed group shot.
- Grade: day → warm LUT (`lut_spark13`, 0.35–0.5); night → light pop (`color_wide_lut24`, 0.35); photos natural.
- Mixing footage from other trips is fine as long as nothing claims a date.

## Working style
- Research/trend-watching should need zero manual effort from the user; they will supply specific shots when asked.
- Duplicate the project before every new version; name `vN (what changed)`.
- Short hand-offs: what changed, file path, what to check by ear.
