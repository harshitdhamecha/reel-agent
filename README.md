# reel-agent

A Claude Code plugin that turns a folder of footage and a one-line brief ("goa reel") into a **beat-synced vertical reel in your own style**, built inside Meta's **Edits** app, keeps an eye on what's trending on Instagram so the reels feel current, and **clips long videos (streams, podcasts, gameplay) into captioned Shorts/Reels**.

Four skills:

- **reel-maker** reads your footage, plans the shots in beats, builds the project in Edits, syncs every cut to the song's beat grid frame by frame, adds the caption, exports a 1080×1920 MP4 (HEVC, as Edits exports) and checks it against the song's actual hits. It **learns your taste** from your feedback into a style profile, so reel #2 starts where reel #1 ended.
- **style-coach** trains the agent on **your** taste: give it a few reels you made or love and it measures them (cut pacing in beats, flash-montage opener, tempo, on-beat accuracy, colour warmth, caption placement, fade-out), asks up to 6 quick questions, and writes your style profile. After every reel it records what you changed or approved, in your words.
- **trend-scout** finds top reels in a niche and works out the hook, cut pacing, caption style, length and song for each. It also reads a song's sound page to see whether the song is rising. It writes a dated trend note that reel-maker uses.
- **clip-maker** turns a long video (stream VOD, podcast, gameplay, talk) into 3–5 vertical clips: transcribes it (whisper.cpp or Edits), ranks moments by hook, payoff and loudness peaks (`find_moments.py`), cuts with jump cuts, reframes (talking head, facecam-over-gameplay stack, gameplay crop), adds word-by-word captions and a hook, normalises speech loudness, and exports with a sidecar recording the source and **permission basis** (clipping campaign, creator policy or Creative Commons). It never re-uploads trailers raw.

## Train it on your style

1. Export or save 3–5 reels you made (or love) as MP4s, e.g. in `~/Movies/my-reels/`.
2. Tell Claude: **"learn my style from ~/Movies/my-reels"**. style-coach measures each reel (`skills/style-coach/scripts/analyze_reel.py`, ffmpeg only), looks at the frames, and asks ≤ 6 questions (vibe, caption tone, music, camera moves, people vs scenery, length).
3. It writes `~/.claude/reel-agent/style.md`, with every rule tagged by its evidence ("user said", "measured: 3/3 reels", "feedback on v2"). Your words always beat measurements. Every reel after that starts from this profile, and your feedback keeps refining it.

No reels yet? Say "set up my reel style" and it runs the interview on top of the example profile.

## What a session looks like

```
you:    ~/Movies/bali-trip  — make a bali reel
claude: (contact sheets of every clip) 31 clips, 12 photos. Two are screenshots, skipping.
        Thin on: road POV, food. Got any?
        Plan: 13.6 s, 7 bars. Flash montage of 14 shots in 4 beats, then arrival, scooter,
        rice terraces, golden hour, night, and a 4-beat ending hold.
        Songs (you judge by ear):
          1. <trending track> — on 3 of the top 5 Bali reels, 124 BPM, highlight at 0:41
          2. <classic> — the song people tie to Bali
        Building 1…
        → ~/Movies/bali-reel/bali-reel-v1-<song>.mp4 (verified: 1080×1920, cuts within 1 frame of beats)
you:    no zoom on the photos, and the caption feels too salesy
claude: v2. Saved to your style profile: "no camera moves on photos; recap captions, not invitations".
```

## Install

```
/plugin marketplace add harshitdhamecha/reel-agent
/plugin install reel-agent@reel-agent
```

Or clone it and run `/plugin marketplace add ./reel-agent`.

## Prerequisites

| | Required | Notes |
|---|---|---|
| macOS + [Edits](https://www.instagram.com/edits/) (Meta's video editor) | yes | The editor the reels are built in. |
| `metapilot-native` MCP server | yes | Third-party bridge that exposes Edits to Claude (default `http://127.0.0.1:19501/mcp`). Not made by Meta or Anthropic. |
| Xcode command-line tools (`swiftc`) | recommended | For the footage contact-sheet helpers. |
| [Nimble](https://nimbleway.com) MCP | optional | Logged-out reel metadata and MP4s for trend-scout (paid credits). |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) with its own `--user-data-dir` | optional | Logged-in trend discovery with a **secondary** Instagram account. |
| `ffmpeg`, Python 3 | recommended | style-coach's reel analyzer and the beat planner (`python3`). |
| `yt-dlp` | optional (required for clip-maker URLs) | Downloads VOD sections for clip-maker; YouTube Shorts for trend checks. |
| `whisper.cpp` (`brew install whisper-cpp` + a `ggml-base.bin` model) | recommended for clip-maker | Fast transcripts of long videos; Edits `transcribeClip` works without it, slower. |

Your data lives in `~/.claude/reel-agent/`, which plugin updates never touch:
- `style.md`: your learned style, written by style-coach (or created on your first reel from `skills/reel-maker/style.example.md`).
- `trends/`: dated trend notes.
- `config.md`: the confirmed secondary account, if you set one up.

## Limitations

- **Claude can't hear.** It shortlists songs by data: what top reels use, how many reels use a sound, tempo, and whether the beat grid is steady. **You** pick by ear. Exports are checked for audio levels and onset timing, not for taste.
- It only works with the Edits app on macOS, through a third-party MCP bridge whose tools may change.
- Music comes from the Edits licensed library. Royalty-free downloads there were unreliable when tested.
- The tools for scraping trends break when sites change. The skill lists fallbacks, but expect to fix things now and then.

## Safety and terms

- **It never automates your main Instagram account.** Logged-in discovery uses a separate browser profile, and **you** log in to a secondary account yourself. The skill reads back the username and asks you to confirm before it uses that account.
- Browsing is read-only: no likes, follows, comments, DMs or posts. It also keeps volume low, about 5–10 reels per run.
- **Automated access and scraping may violate Instagram's Terms of Use**, and third-party scraping services have their own terms. You are responsible for how you use this. Downloaded reels are for analysis only, so don't redistribute other creators' content.
- Music licensing is handled by Edits and Instagram. Publish from Edits, or add the same licensed song inside Instagram.

## Development

```
python3 -I -m unittest discover -s tests
```

`skills/reel-maker/scripts/beat_plan.py` fits the song's beat grid from the Edits beat markers. It then prints exact placements for a fresh build (or trims for an existing timeline) so that every cut lands on a beat, rounded to whole frames without drift. It reads the raw `beatMarkers` output directly (`markers_file` + `window`). `skills/style-coach/scripts/analyze_reel.py` measures a finished reel with ffmpeg only: cuts (brightness-normalised frame correlation), flash bursts, tempo, a half-beat grid fitted to the cuts (BPM, beat structure, off-grid cuts), grade numbers and fade-out; its test builds a synthetic reel with known cuts and a 120 BPM click. `skills/trend-scout/scripts/shortcode.py` converts Instagram media IDs to shortcodes.

## License

MIT, © Harshit Dhamecha
