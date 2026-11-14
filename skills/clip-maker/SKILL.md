---
name: clip-maker
description: Turn long-form video (stream VODs, podcasts, gameplay, talks) into short vertical clips for Instagram Reels and YouTube Shorts — find the best moments from the transcript and loudness, cut them, reframe to 9:16 (talking head, facecam-over-gameplay stack, or gameplay crop), add word-by-word captions and a hook, export and verify. Use when the user says "clip this", "make shorts from this stream/podcast/VOD", gives a long video URL or file, joins a clipping campaign, or wants launch-week clips (e.g. a big game release). Drives Meta's Edits app on macOS through the metapilot-native MCP server.
---

# clip-maker

Input: a long video (URL or file) + who/what it is + the **permission basis**. Output: 3–5 verified 1080×1920 clips with word captions and a hook, plus a sidecar JSON recording source and permission.

Mechanics shared with reel-maker (Edits screens, `appState`, `convertToMain` noise, HEVC/60 fps export, new filename per export) are in `../reel-maker/SKILL.md` §0, §4, §7 — read those first. For what clips perform in a niche, use `trend-scout` (and its notes).

## Rules (read first)
- **Only clip what you're allowed to.** Valid bases: a clipping campaign that names the source (Whop Content Rewards etc. — follow its rules: credit line, hashtags, tags, banned content), the creator's stated clipping policy, a Creative Commons licence (`yt-dlp --print "%(license)s"`), or the user's own footage. Record it in the sidecar. No basis → stop and say so.
- **Never re-upload trailers, cutscenes or other people's videos raw.** Publisher trailers (e.g. a game trailer) are the classic Content ID/strike magnet. Clip *reactions, commentary and gameplay moments*, transformed (below).
- **Spoilers:** for story games and launches, flag any clip that shows story beats/endings in the hand-off; put "SPOILER" in the hook if posting is still wanted.
- Posting is the user's job (dedicated clipping accounts, never automated). This skill only produces files.

## Prerequisites
| Need | Required? | Without it |
|---|---|---|
| Edits + metapilot-native MCP | yes | Produce timestamps + transcript cuts the user can apply by hand. |
| `yt-dlp`, `ffmpeg` | yes (download, loudness) | User supplies the file. |
| `whisper.cpp` (`brew install whisper-cpp` + a `ggml-base.bin` model) | recommended | Edits `transcribeClip` per section (slower for hours of VOD). |

## 1. Source → `~/Movies/clips/<project>/`
- Long VODs: download **only the sections you need**:
  `yt-dlp -f "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]" --merge-output-format mp4 --download-sections "*HH:MM:SS-HH:MM:SS" -o "src-<id>.%(ext)s" <url>`
  Section downloads re-encode through ffmpeg and run roughly **0.7× real time** (10 min took ~7 min). Never download a whole long stream: pick windows first (below), then download just those at 1080p.
- **Pick windows without downloading — `scripts/stream_moments.py <youtube-url>`** (~15 s for a 3–11 h VOD). Viewers already marked the moments:
  - **Timestamp comments** (top 300–400 comments; 1–2 timestamps each; likes on a log scale; navigation comments like "match starts from here" demoted) — exact to the second and the comment text is a ready hook idea ("7:43:08 the switch from 😂 to 🤨 is hilarious", 170 likes).
  - **Most-replayed heatmap** — 100 bins over the video (≈ 2 min bins on 3 h, ≈ 7 min on 11 h): coarse, so transcribe that window to find the exact beat. Appears once the video has enough views (hours, not minutes).
  - **Live-chat spikes** (`--chat <id>.live_chat.json` from `yt-dlp --skip-download --write-subs --sub-langs live_chat <url>`) — the only signal right after a stream ends. Slow to fetch (3.4 h Hindi stream: ~150 MB, ~12 min) and modest on huge chats (peaks ~1.7× median), so run it in the background.
  - Output: windows ranked by score with a ready `--download-sections` string, chapter and hook idea. Read the hook ideas yourself; still confirm each window from its transcript.
  - Twitch/Kick: use the channel's top clips (`yt-dlp --flat-playlist "https://www.twitch.tv/<user>/clips?filter=clips&range=24hr"` → view counts) as the moment list.
- Edits can only read `~/Movies` — stage there.
- Write `sidecar.json`: `{source_url, creator, permission, section, clips:[{file, source_in:[[a,b],…], layout, hook}]}`. Times in the sidecar are relative to the downloaded section; note the section offset.

## 2. Transcribe + find moments
- Fast pass over the whole file: `ffmpeg -i src.mp4 -ac 1 -ar 16000 src.wav` → `whisper-cli -m <models>/ggml-base.bin -f src.wav -l en -oj -of src -np` (10 min of audio ≈ 17 s on Apple silicon). **Pass `-l` explicitly** (`en`, `hi` for Hindi): `-l auto` mis-detected an English talk as Javanese. Whisper segments are coarse (whole seconds) — fine for finding moments, not for captions.
- `python3 -I "$SKILL/scripts/find_moments.py" src.json --audio src.wav --top 8 [--offset <section start s>]` → ranked windows (15–45 s) with hook line, payoff line, score and reasons (strong hook, loud moments, reaction near the end, ends mid-sentence). It is a narrowing tool: **Claude reads the top windows' text and makes the pick** — the scorer can't tell when a window drifts off-topic at the end.
- What makes a clip: a first line that works with no context (question, bold claim, "wait—"), one idea, a payoff in the last 3 s (punchline, reveal, scream, result). Streams/gameplay: loudness peaks + reaction words beat transcript quality.
- Precise word timings: Edits `transcribeClip {id:<timeline clip id>, language:"en", mergeSplitWords:true}` → `words[{text,start,end}]` in timeline seconds plus `lines`. Use it on the placed clip to find filler/dead air to jump-cut ("um", "where are they? yeah").

## 3. Build in Edits (one clip at a time)
- New project per source: `newProject` → `setTitle "<source> clips"`. Canvas is 1440×2560 @ 60 fps.
- `importToMediaPanel {path}` (once) → per clip `addMediaPanelItemsToTimeline {aliasIds:[alias], startTime, sourceIn, sourceOut}` → `convertToMain`. **Jump cuts** = several placements back to back (e.g. 187.0–195.1 then 197.9–205.4) instead of splitting later.
- Clips share one project; build → export → clear (`deleteCaptions {}` with no id deletes all captions; `selectById` + `delete` for clips/text) → next clip.

### Layouts
- **(a) Talking head:** `autoReframe {ids, subject:"largestFace", motion:"follow", wideShotPolicy:"crop"}`. Check `frameSheet`: if the source has letterbox bars or a picture-in-picture panel, fix with `setTransform {id, scale, x, y, allowBeyondCanvas:true, keyframes:"clear"}`. Placing source point `f` (0–1 across the frame) at canvas centre: `x = 0.5 + (0.5 − f) × scale`; `scale` is in canvas widths (a 16:9 source filling a 9:16 canvas height is ≈3.16). Upscaling a small face panel beyond ~4× looks soft.
- **(b) Facecam + gameplay (streams), or speaker + slides:** `splitScreen {id, layout:"stack2", panels:'[{"crop":{"left":0,"top":0.07,"right":0.205,"bottom":0.36}},{"crop":{"left":0.22,"top":0.06,"right":1,"bottom":0.94}}]', background:"blur", gap:0}` → panel 1 (top) = the original element, panel 2 = a muted copy on a new track, plus a blurred background copy. Crops are normalised source rects. `panels` **must** be a JSON array of objects (`'[{}, {}]'` = default halves); a `dryRun` param is rejected. Re-cropping a panel later with `cropClip {id, rect}` also rescales it to fill its slot.
- **(c) Gameplay only:** `autoReframe {subject:"center", wideShotPolicy:"crop"}` for action at the centre (driving, shooting), or `splitScreen` with one gameplay panel + blur background to keep the full HUD width.

### Audio
- Speech must be loud enough: check `loudness {id:"", path:<export>}` or ffmpeg `ebur128`. Conference/stream audio often sits at −26 LUFS. Fix on the element: `processAudio {id, chain:'[{"type":"highpass","hz":80},{"type":"normalize","target":-14}]', mode:"replace"}` → reports `beforeLufs`/`afterLufs` (landed at −16 LUFS, peak +0.1 dBFS — add a `{"type":"gain"}` step of −1 dB if peaks clip). Valid step types: highpass, lowpass, notch, eq, isolation, gain, normalize; highpass takes `hz`. `isolation` cleans crowd/game noise under a voice.
- Music under speech: rarely needed for clips; if used, keep it ≥ 18 dB under the voice (`setDucking`).

## 4. Captions + hook
- `generateCaptions {source:"video", language:"en", curseWords:false}` (source must be `video|voiceover|importedAudio|all`) → phrase captions with per-word tokens. `captions` returns everything (large) — call it once, then edit by id.
- Clean up: `editCaption {id, text}` (drop "um", fix mis-hearings, de-duplicate), `deleteCaptions {id}` for filler-only phrases, `splitCaption {id, time}` at a word gap so each phrase is ≤ ~5 words.
- Style: `setCaptionStyle {style:"Word Highlight Box"}` (bold condensed `InstagramSqueeze-Black`, highlights the spoken word) + `setCaptionHighlightColor {color:"#FFD60A"}`. Other good word-by-word styles: "Word Highlight", "Short Pop", "Short Hard Cut". Captions sit at y≈0.73 by default — above the bottom UI. `setTextPosition` on one caption id moves only that phrase; keep them consistent.
- Hook (first ~2.5 s): `addText {text, atSeconds:0, duration:2.5}` → `setTextStyle {size:40, bold:true, color:"#FFFFFF", alignment:"center"}` → `setEmphasis {style:"backgroundPill", color:"#000000CC"}` → `setTextPosition`. **Size 64 wraps mid-word on a 9:16 canvas; 40 fits ~20 characters per line.** Put it where it covers no face (on a stack, the seam at y≈0.47 works).
- Credit line when required: small (size ~20) text at y≈0.08 for the whole clip, e.g. `🎥 <creator>`; extend with `trimClip {id, side:"end", delta:<negative to extend>}`.

## 5. Export + verify
- `setExportSettings` as in reel-maker §7 (HEVC, fps follows the 60 fps canvas) → `export {path:"…/<clip>-tryN.mp4"}` → `wait` 20–30 s → `exportStatus`.
- Verify: probe 1080×1920 + duration; loudness −14…−16 LUFS, peak < 0 dBFS; `frameSheet` across the clip for faces under text, panel edges/borders, letterboxing, caption timing.
- Update `sidecar.json`. Batch 3–5 clips per source.

## 6. Originality (avoid "reused content" / unoriginal-content penalties)
YouTube's reused-content policy and Instagram's originality ranking both demote straight re-uploads. Every clip should add something: a written hook, edited word captions, reframing/layout (stack, zoom), jump cuts that tighten the moment, and ideally a short commentary/context line. Don't post the same clip to many accounts, don't watermark-strip, and keep clips from one source varied (different moments, different hooks). Campaigns usually require exactly this ("original edit, not a reupload").

## 7. Hand-off
Clip paths + one line each (moment, hook, layout, length), sidecar path, flags (spoilers, weak audio, soft upscales), and what to post where. Measured on the trial (Nov 2026, Apple silicon): 10-min section download ~7 min; whisper 17 s; moment ranking < 1 s; build + export ~2–3 min per clip once the layout is known.

## Always-on clipping (how pro clippers scale)
1. **Watchlist** of permitted sources, one niche per output account (campaign briefs name the streamer's handle): `sources.json` `[{channel_url, platform, permission, campaign, language, account}]`.
2. **Poll** each channel for new VODs/streams (`yt-dlp --flat-playlist -I 1:5 --print "%(id)s|%(title)s|%(duration)s" <channel>/streams`), skip ids already in the log.
3. **Rank** with `stream_moments.py` (chat right after the stream; re-run after ~12–24 h when comments + heatmap fill in for a second batch).
4. **Download only the top windows**, build 3–5 clips per stream with different hooks, export, verify.
5. **Queue** files + caption + hashtags + campaign tag for posting; post within hours of the stream (first clips of a moment win). Posting stays a human/approved step unless the user authorises an official API (YouTube Data API upload; Instagram Graph API publishing on a Business/Creator account) — never browser bots, never the user's main account.
6. **Track**: views per clip at 24 h / 72 h → feed back which hooks/streamers pay; submit to the campaign within ~30 min of posting.
- Volume pros run: 3–5 posts per account per day, several single-niche accounts. Don't post the same clip on several accounts (duplicate/spam flags; campaigns pay once per clip).
- Money: campaign budgets drain fast, per-clip caps limit a viral clip (e.g. $35 cap at $0.70/1K), most gaming briefs want Tier-1 (US/UK/CA/AU) viewers — English clips of US streamers earn; Hindi clips grow reach but rarely pay.

## Launch-week playbook (big game releases, e.g. GTA VI on 19 Nov 2026)
- Before launch: line up sources with permission (streamer clipping campaigns, creators with open clipping policies); prepare the project template (stack layout + caption style + hook style) so day-one clips take minutes.
- Launch day: biggest streams first; clip first reactions, funny NPC/physics moments, "you can do THIS" discoveries, map/size comparisons, glitches. Mark story spoilers.
- Avoid: raw trailer re-uploads, leaked footage, piracy links.
- Volume: 3–5 clips per stream, posted across IG Reels + YouTube Shorts with different hooks.
