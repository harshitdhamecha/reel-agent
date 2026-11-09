---
name: reel-maker
description: Build short-form vertical reels (Instagram Reels / YouTube Shorts / TikTok) from a folder of videos and photos plus a one-line brief like "goa reel" or "wedding recap". Use when the user gives footage and asks for a reel/short/social video, asks to change a song/caption/cut on an existing reel, or says "make a reel". Drives Meta's Edits app on macOS through the metapilot-native MCP server, applies the user's learned style (style.md) and current trends (trend-scout skill).
---

# reel-maker

Input: a footage folder + a brief. Output: a beat-synced, verified 1080×1920 MP4 and an Edits project the user can publish from.

**Before planning, read the user's style profile at `~/.claude/reel-agent/style.md`. If it doesn't exist, read `style.example.md` (this folder) as the starting default, and create the profile from what the user says (see "Learning the user's style").** This file holds the how; the profile holds the taste. User data lives in `~/.claude/reel-agent/` so plugin updates never overwrite it.
For what's trending, use the `trend-scout` skill and its notes in `~/.claude/reel-agent/trends/` — don't re-research per reel.

## Prerequisites
| Need | Required? | Without it |
|---|---|---|
| macOS + **Meta Edits** desktop app, running | yes | Can't build. Offer a shot list + beat plan the user can apply by hand. |
| **metapilot-native** MCP server (third-party bridge into Edits, default `http://127.0.0.1:19501/mcp`) | yes | Same as above. Check with `claude mcp list`. |
| Xcode command-line tools (`swiftc`) | recommended | Use `ffmpeg` for frame grabs, or `captureSourceFrames` after import. |
| `ffmpeg`, Python 3 | optional | Swift helpers + Edits analysis tools cover most needs. |

metapilot-native is not made by Meta or Anthropic. Its tool names can change between versions — read the live tool list rather than trusting this file blindly.

## 0. Setup (every session)
- Edits tools are deferred and **the tool set follows the app screen**: home-screen tools (`projects`, `newProject`, `openProject`, `duplicateProject`, `renameProject`) vs editor tools (everything else). After switching screens, reload the tools you need with one `ToolSearch select:` call.
- Compile the Swift helpers once into a scratch dir: `swiftc -O scripts/contact_sheet.swift -o <scratch>/contact_sheet` (same for `photo_grid.swift`, `probe.swift`). Don't name a binary the same as an existing directory.
- **Edits is sandboxed: it can't read `~/Downloads` (and may not read other folders).** Copy footage to `~/Movies/<project>/` (originals untouched) and import from there.

## 1. Intake & footage pass
1. List the folder; `mdls -name kMDItemContentCreationDate -name kMDItemDurationSeconds -name kMDItemPixelWidth -name kMDItemPixelHeight` each file (or `scripts/probe`).
2. `contact_sheet <outdir> <videos...>` and `photo_grid <out.jpg> <photos...>`; read the sheets. Tag each: subject, day/night, orientation, sharp windows, motion.
3. **Flag, don't silently drop**: strays (screenshots), files from other dates/trips, near-duplicates. Ask only if it changes the plan.
4. If footage is thin for the planned structure, list the exact missing shots ("scooter POV, waves, food, pool") — users happily supply specific shots when asked.

## 2. Plan
- Shot list in the structure from the style profile. Lengths in **beats**, not seconds.
- First frame = prettiest still (it becomes the thumbnail). Pick sharp windows for every shot (`captureSourceFrames`).
- Song: 2–3 licensed candidates (step 4). Caption per the style profile.
- Show the plan in a few lines and proceed unless the user objects.

## 3. Build
- **Version hygiene:** new reel → `newProject` + `renameProject "<Name> v1 (what)"`. New version → `saveProject` → `closeProject` → `duplicateProject` → rename → `openProject`. Never overwrite a version the user has seen. A duplicate keeps the old song — delete it if the song changes.
- Import with `importToMediaPanel`, **one file at a time** (parallel imports race). Photos (jpg/HEIC) work.
- Place each shot: `addMediaPanelItemsToTimeline {aliasIds:[id], startTime, sourceIn, sourceOut}` → lands on its own overlay track. Then `convertToMain` in timeline order (first one alone, rest batched). It may report "rollback failed" errors while still producing the right result — verify with `clips`/`state`.
- Insert into an existing timeline: place at the end, `convertToMain`, then `reorderClip {id, position}` (0-based).
- Remove: `selectById` (addToSelection for more) → `delete`.
- Landscape video → `autoReframe {ids, subject:"center", motion:"static", wideShotPolicy:"crop"}` (`largestFace` misfires in dark footage). Photos can't autoReframe → `setTransform {fitMode:"fill", focusX, focusY, allowBeyondCanvas:true, keyframes:"clear"}`, or manual `scale`/`x`/`y`. Avoid keyframed pans unless the style profile says otherwise.
- Mute every video clip with `setVolume 0` per clip (`muteTrack` takes an element id, not a track).
- Grade per clip with `applyFilter` (adjustment layers reject filters). Use the grade in the style profile.

## 4. Music (Edits licensed library)
- `searchMusic` / `listMusicTracks {query, tab:"", license:"any"}`. Use tracks with `importPath:"obfuscatedWindow"` (licensed). `fullFile` (royalty-free) downloads may fail (DownloadError 3) and `addMusicTrack` can silently add nothing. The "Trending" tab is mostly unlicensed creator "Original audio" — avoid.
- `addSongToComposition {track, audioAssetId}` → element with **beat data**. `slipClip` it to the section you want, then `beatMarkers` (markers every 2 beats, `[index, sourceSeconds]`, only on the first-added song element). Prefer a downbeat near the track's `highlights` where marker spacing is steady (vocal breaks give irregular markers).
- `python3 -I scripts/beat_plan.py plan.json` with those markers + current `clips` + target beats → period/BPM + exact `trimClip side=end` deltas (positive shortens, negative extends). Apply, then `slipClip` the song so its in-point is the chosen downbeat (timeline 0 = beat).
- Make the total a whole number of bars; trim the song and caption to the exact end; `setFade {fadeIn:0, fadeOut:1.5}`.
- **Audio clips can self-extend after ripple edits** — re-check (`elements` with a range past the end) after every structural change.
- **Claude can't hear.** Pick songs by data (see the style profile's "How to shortlist songs" and trend-scout's song signals); the user judges by ear.
- Fallback if the library is unavailable: free no-attribution libraries (e.g. Mixkit); avoid tracks marked "Content ID registered".

## 5. Caption
- Follow the style profile (text, preset, size, position, animation). Default from the example profile: `addText {text, atSeconds:0, duration:<total>}` → `selectTool textPresets` → `applyTextPreset {id, name}` → `setTextStyle {size, bold:false, color:"#FFFFFF", alignment:"center"}` → `setTextPosition {x:0.5, y:0.22}` → `setTextAnimation {animation:"none"}`.
- Check it never sits on faces or a busy bright area; fix the shot's framing rather than moving the caption per shot.
- Keep text out of the bottom ~15 % and the right-edge UI.

## 6. Check (before export)
- `state` → clipBoundaries on the beat grid; `elements {rangeStart:<total>, rangeEnd:<total+5>}` → nothing past the end.
- `frameSheet {id:"", path:"", times:...}` across every section + `captureFrame` close-ups. Look for letterboxing, blur, caption collisions, first frame.

## 7. Export & verify
- `setExportSettings {aspectRatio:"nineBySixteen", resolutionType:"HD", quality:"High", dynamicRange:"SDR", frameRate:30}` (all fields required; without aspectRatio the export can come out in the wrong shape).
- `export {path:"~/Movies/<project>/<name>-vN-<what>.mp4"}` → `wait` ~25 s → `exportStatus`.
- Verify the file: probe (1080×1920, duration), `audioLevels` (music present; fade drops ~20 dB at the end), `audioOnsets` (hits ≤1 frame from cuts), `frameSheet` with `path`.

## 8. Hand-off
Short: file path, project name, what changed, what to check by ear. Remind: publish from Edits, or add the same song inside Instagram so the reel joins the song's audio page.

## Learning the user's style
- First reel: copy `style.example.md` to `~/.claude/reel-agent/style.md` (create the folder), then replace the example with the user's choices as they react.
- After every round of feedback, record the **taste** in the profile (what they kept, rejected, and why, in their words) and **mechanics** (tool quirks) in this file's relevant section. Mark the posted version as the reference reel.
- Treat style.md as defaults, not laws: when footage or a brief pulls another way, propose the change in one line.

## Generic playbook (rules of thumb from creator/vendor blogs, 2026)
- Hook lands in the first 1–1.5 s; many viewers leave by 3 s. Open on the best visual.
- Shortest length that works (often 7–15 s for montage reels). End so it loops into frame 1.
- Cut on beats; one consistent grade; mostly hard cuts.
- Ranking (per Instagram's public statements): watch time, then sends/shares, likes, saves. 9:16, 1080×1920, H.264.
Sources: later.com/blog/instagram-reels-algorithm · opus.pro/blog/ideal-instagram-reels-length · inro.social/blog/instagram-reels-3-second-hook-leads · bundle.social/tools/safe-zone-checker
