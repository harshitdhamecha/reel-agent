---
name: reel-maker
description: Build short-form vertical reels (Instagram Reels / YouTube Shorts / TikTok) from a folder of videos and photos plus a one-line brief like "goa reel" or "wedding recap". Use when the user gives footage and asks for a reel/short/social video, asks to change a song/caption/cut on an existing reel, or says "make a reel". Drives Meta's Edits app on macOS through the metapilot-native MCP server, applies the user's learned style (style.md) and current trends (trend-scout skill).
---

# reel-maker

Input: a footage folder + a brief. Output: a beat-synced, verified 1080×1920 MP4 and an Edits project the user can publish from.

**Style profile first.** If `~/.claude/reel-agent/style.md` doesn't exist:
`mkdir -p ~/.claude/reel-agent && cp "<this skill's folder>/style.example.md" ~/.claude/reel-agent/style.md`, tell the user in one line that you're starting from the example profile, then read it. This file holds the how; the profile holds the taste. User data lives in `~/.claude/reel-agent/` so plugin updates never overwrite it.
For what's trending, use the `trend-scout` skill and its notes in `~/.claude/reel-agent/trends/` — don't re-research per reel.

## Prerequisites
| Need | Required? | Without it |
|---|---|---|
| macOS + **Meta Edits** desktop app, running | yes | Can't build. Offer a shot list + beat plan the user can apply by hand. |
| **metapilot-native** MCP server (third-party bridge into Edits, default `http://127.0.0.1:19501/mcp`) | yes | Same as above. Check with `claude mcp list`. |
| Xcode command-line tools (`swiftc`) | recommended | Use `ffmpeg` for frame grabs, or `captureSourceFrames` after import. |
| `ffmpeg`, Python 3 | optional | Swift helpers + Edits analysis tools cover most needs. |

metapilot-native is not made by Meta or Anthropic. Its tool names and behaviour can change between versions — read the live tool list rather than trusting this file blindly. Notes below were verified against the Edits build available in Nov 2026.

## 0. Setup (every session)
- Edits tools are deferred and **the tool set follows the app screen**: home-screen tools (`projects`, `newProject`, `openProject`, `duplicateProject`, `renameProject`) vs editor tools (everything else, including `closeProject`, `saveProject`, `setTitle`). **Home-only tools are not listed at all while the editor is open** (a ToolSearch finds nothing). After switching screens, reload the tools you need with one `ToolSearch select:` call.
- **First call: `appState`, read only `.screen`** (the output is huge). If it is `editor`, a project is already open — check `title`, **don't edit it**, `closeProject`, then reload the home tools.
- Compile the Swift helpers once into the session scratch dir (`$SCRATCH`), using absolute paths to this skill's folder (`$SKILL`):
  `swiftc -O "$SKILL/scripts/contact_sheet.swift" -o "$SCRATCH/bin/contact_sheet"` (same for `photo_grid.swift`, `probe.swift`). Deprecation warnings are harmless. Don't name a binary the same as an existing directory.
- **Edits is sandboxed: it can't read `~/Downloads` (and may not read other folders).** Copy footage to `~/Movies/<project>/` (originals untouched) and import from there.
- If the user isn't available (unattended run), take the conservative choice on every judgement call (leave it out / keep the default) and list it under **Flagged** in the hand-off.

## 1. Intake & footage pass
| Helper | Usage | Output |
|---|---|---|
| `contact_sheet` | `contact_sheet <outDir> <videos…>` | one `<name>.jpg` frame grid per video |
| `photo_grid` | `photo_grid <out.jpg> <images…>` | one grid of all photos |
| `probe` | `probe <file>` | one line per track (type, natural size, transform, fps) + duration. Landscape = width > height *after* the transform; no `soun` line = no audio. iPhone files also list several `meta` tracks — ignore. |

1. List the folder; `mdls -name kMDItemContentCreationDate -name kMDItemDurationSeconds` each file for dates/durations. For orientation trust `probe` (natural size + transform) over `mdls` pixel sizes.
2. `contact_sheet` + `photo_grid`; read the sheets. Tag each: subject, day/night, orientation, sharp windows, motion.
3. **Flag, don't silently drop**: strays (screenshots), files from other dates/trips, near-duplicates, posed group shots (if the profile says to ask). Ask only if it changes the plan; if no one can answer, leave it out and flag it.
4. If footage is thin for the planned structure, list the exact missing shots ("scooter POV, waves, food, pool") — users happily supply specific shots when asked.

## 2. Plan
- Shot list in the structure from the style profile. Lengths in **beats**, not seconds. Flash-montage shots: ≈¼–½ beat each — the shot count follows from the BPM.
- First frame = prettiest still (it becomes the thumbnail). Pick sharp windows for every shot (`captureSourceFrames`).
- Song: 2–3 licensed candidates (step 3). Caption per the style profile.
- Show the plan in a few lines and proceed unless the user objects.

## 3. Project + music first
- **Version hygiene:** new reel → `newProject` (opens the editor directly) → `setTitle "<Name> v1 (what)"` (editor tool; `renameProject` is for the home screen and may not update an open project's title). New version → `saveProject` → `closeProject` → `duplicateProject` → `renameProject` → `openProject`. Never overwrite a version the user has seen. A duplicate keeps the old song — delete it if the song changes.
- New projects are **1440×2560 @ 60 fps**; read `getCanvas().frameRate` and use it as `fps` everywhere below.
- Song search: `searchMusic` / `listMusicTracks {query, tab:"", license:"any"}`; `getMusicTrackDetails` gives `highlights` (popular segments). Use tracks with `importPath:"obfuscatedWindow"` (licensed). `fullFile` (royalty-free) downloads may fail (DownloadError 3) and `addMusicTrack` can silently add nothing. The "Trending" tab is mostly unlicensed creator "Original audio" — avoid.
- `addSongToComposition {track:<track id>, audioAssetId:<same id for library tracks>}` → song element with **beat data**. It arrives as a **90 s window from source 0 s**, and `beatMarkers` covers only that visible window. To use a later highlight, `slipClip` the song first, then re-read `beatMarkers`. `slipClip` quantises to project frames silently.
- `beatMarkers` returns a large object (`{estimatedBpm, markers:[{index, sourceSeconds, timelineSeconds, isDownbeat, strength, …}], beats:[…]}`, often >50 KB, so it gets saved to a file). Markers come every 2 beat-indexes and only on the first-added song element.
  - **Ignore `estimatedBpm`** (and `audioOnsets.bpm`) — both report half tempo. Use the BPM from `beat_plan.py`.
  - `isDownbeat` flags are noisy. Trust the fitted grid: a bar starts every 4 beat-indexes counted from index 0.
  - Prefer a bar start near a highlight where marker spacing is steady (vocal breaks give irregular markers; check `max_residual`).
- `python3 -I "$SKILL/scripts/beat_plan.py" plan.json` with `"markers_file": "<saved beatMarkers file>", "window": [lo, hi]` → period/BPM, phase, residual. Then `slipClip` the song so its in-point is the chosen bar start (timeline 0 = beat).

## 4. Place shots (exact times, no retrimming)
- Import with `importToMediaPanel`, **one file at a time** (parallel imports race). Photos (jpg/HEIC) work.
- Put the shot list in the same plan file as `"shots": [{"alias", "beats", "sourceIn"}]` → `beat_plan.py` prints one `addMediaPanelItemsToTimeline {aliasIds, startTime, sourceIn, sourceOut}` per shot, frame-exact and cumulative. Each lands on its own overlay track.
- Then `convertToMain` in timeline order (first one alone; the rest can go in parallel). **Expect `ok:false … "convert moved start to X, expected Y; rollback also failed: trackNotFound"` on nearly every call after the first two** — if X equals the planned start, it worked. Always confirm with `clips`.
- Retiming an existing timeline instead: `"clips"` (from `clips`) + `"beats"` → `trimClip side=end delta` per clip (positive shortens, negative extends).
- Insert into an existing timeline: place at the end, `convertToMain`, then `reorderClip {id, position}` (0-based). Remove: `selectById` (addToSelection for more) → `delete`.
- Run `frameSheet` now, **before grading**, to catch letterboxing once:
  - Landscape video → `autoReframe {ids, subject:"center", motion:"static", wideShotPolicy:"crop"}` (`largestFace` misfires in dark footage).
  - Landscape/square photos → `setTransform {fitMode:"fill", focusX, focusY, allowBeyondCanvas:true, keyframes:"clear"}`, or manual `scale`/`x`/`y`. Avoid keyframed pans unless the style profile says otherwise.
- Mute every video clip with `setVolume 0` per clip (`muteTrack` takes an element id, not a track).
- Grade per clip with `applyFilter` (adjustment layers reject filters). Use the grade in the style profile; if its filter ids aren't in `listFilters`, pick the nearest and note it.

## 5. Finish the music + caption
- Make the total a whole number of bars; trim the song and caption to the exact end; `setFade {fadeIn:0, fadeOut:1.5}`.
- **Audio clips can self-extend after ripple edits** — re-check (`elements` with a range past the end) after every structural change.
- **Claude can't hear.** Pick songs by data (the style profile's "How to shortlist songs" and trend-scout's song signals); the user judges by ear.
- Fallback if the library is unavailable: free no-attribution libraries (e.g. Mixkit); avoid tracks marked "Content ID registered".
- Caption — follow the style profile (text, preset, size, position, animation). Default: `addText {text, atSeconds:0, duration:<total>}` → `selectTool textPresets` → `applyTextPreset {id, name}` → `setTextStyle {size, bold:false, color:"#FFFFFF", alignment:"center"}` → `setTextPosition {x:0.5, y:0.22}` → `setTextAnimation {animation:"none"}`. If the preset isn't in `listTextPresets`, pick the nearest.
- Check it never sits on faces or a busy bright area: fix the shot's framing; if the shot can't be reframed (already 9:16), pick another source window or swap the shot. Keep text out of the bottom ~15 % and the right-edge UI.

## 6. Check (before export)
- `state` → clipBoundaries on the beat grid; `elements {rangeStart:<total>, rangeEnd:<total+5>}` → nothing past the end.
- `frameSheet {id:"", path:"", times:...}` across every section + `captureFrame` close-ups: letterboxed photos/landscape clips, blur, caption collisions, first frame.

## 7. Export & verify
- `setExportSettings {aspectRatio:"nineBySixteen", resolutionType:"HD", quality:"High", dynamicRange:"SDR", frameRate:30}` (all fields required; without aspectRatio the export can come out in the wrong shape). **Output is HEVC and follows the project frame rate (60 fps)** — `frameRate` is not honoured and `codec:"h264"` errors ("export pipeline is HEVC-only"). Instagram accepts HEVC.
- **Export every attempt to a new filename** (`<name>-vN-tryM.mp4`): `audioOnsets`/`audioLevels` cache results by path, so re-exporting to the same path silently re-measures the old file.
- `export {path}` → `wait` ~25 s → `exportStatus`.
- Verify: probe (1080×1920, duration, fps); `audioLevels` with `hop` ≤ 0.25 (music present; fade drops ~15–20 dB over the last second); `frameSheet` with `path`.
- **Beat-sync correction:** the Edits marker grid can sit ~25–30 ms *late* versus the audible hits. Compute the median signed offset between cut times and the nearest `audioOnsets` hit; if |median| > ½ frame, `slipClip` the song by that amount (rounded to a frame) and re-export to a new filename. Target: cuts ≤ 1 frame (17 ms at 60 fps) from onsets. Compare against a random-cut baseline (dense onsets make random cuts land "close" ~20 % of the time) so "on beat" means something.

## 8. Hand-off
Short: file path, project name, what changed, what to check by ear, and a **Flagged** list (skipped files, judgement calls made without the user). Remind: publish from Edits, or add the same song inside Instagram so the reel joins the song's audio page.

## Learning the user's style
- After every round of feedback, and when the user says a version was posted, **run the style-coach skill in feedback mode**: it records the taste in `~/.claude/reel-agent/style.md` (in the user's words, with evidence; contradicted rules are revised, not duplicated) and, for a posted reel, measures the export with `analyze_reel.py` to set it as the reference reel. Mechanics (tool quirks) go in this file's relevant section.
- New user with reels they already made or love? Suggest style-coach's **learn** mode before the first build.
- Treat style.md as defaults, not laws: when footage or a brief pulls another way, propose the change in one line.

## Generic playbook (rules of thumb from creator/vendor blogs, 2026)
- Hook lands in the first 1–1.5 s; many viewers leave by 3 s. Open on the best visual.
- Shortest length that works (often 7–15 s for montage reels). End so it loops into frame 1.
- Cut on beats; one consistent grade; mostly hard cuts.
- Ranking (per Instagram's public statements): watch time, then sends/shares, likes, saves. 9:16, 1080×1920; HEVC or H.264 both upload fine (Edits exports HEVC).
Sources: later.com/blog/instagram-reels-algorithm · opus.pro/blog/ideal-instagram-reels-length · inro.social/blog/instagram-reels-3-second-hook-leads · bundle.social/tools/safe-zone-checker
