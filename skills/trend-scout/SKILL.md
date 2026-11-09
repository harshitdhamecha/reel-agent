---
name: trend-scout
description: Find and "watch" currently trending Instagram Reels for a niche (e.g. Goa travel, Bali, weddings, cafes) and write a dated trend note — hooks, cut pacing, caption style, songs, length — for reel-maker to use. Use when the user asks what's trending, before planning a reel for a new niche, or when a trend note is older than ~3 weeks. Read-only and low-volume; never touches the user's main Instagram account.
---

# trend-scout

Watches public reels and writes a trend note to `~/.claude/reel-agent/trends/<niche>-<yyyy-mm>.md` (outside the plugin, so updates never wipe it). Pipeline: discover shortcodes → fetch metadata + MP4 → analyse with Edits tools → note.

> **Terms of service.** Automated access and scraping can violate Instagram's Terms of Use, and third-party scraping services carry their own terms. You are responsible for how you use this skill. It is designed to be read-only, low-volume and personal-use: it never posts, likes, follows, comments or messages, and never logs in to anything by itself.

## Rules
- **Never automate the user's main Instagram account.** Logged-out sources are the default.
- **Optional secondary-account browser.** If the user wants logged-in discovery (sound pages, hashtag search), they add a dedicated Playwright MCP server with its own profile, e.g.
  `claude mcp add --scope user playwright-ig -- npx @playwright/mcp@latest --user-data-dir ~/.local/share/playwright-ig`
  then restart Claude Code, and **log in themselves** to a secondary account. Before using it, read back the logged-in username (`/accounts/edit/`) and get the user to confirm it is not their main account. Record the confirmed username in `~/.claude/reel-agent/config.md`.
- **Read-only:** browse hashtags, reels and audio pages only — never like, follow, comment, DM, post, save, or edit the profile. Never type credentials. If logged out, or a checkpoint/captcha appears, stop and ask the user.
- **Low volume:** ~5–10 reels per run, a few seconds between pages. Paid scraping APIs (e.g. Nimble) cost credits.
- Delegate bulky discovery/download to a cheaper subagent (each scraped post result is ~7K tokens). Do the watching (frame sheets) yourself.
- Check `~/.claude/reel-agent/trends/` first; reuse a note younger than ~3 weeks.

## Prerequisites (all optional — use what's available)
| Tool | Gives | Fallback |
|---|---|---|
| Nimble MCP (`instagram_post` extract template) | likes, caption, song, MP4 URL, logged-out | secondary-account browser, or Exa/web search for reel links |
| Playwright MCP with a separate `--user-data-dir` | logged-in hashtag search, reel stats, **sound pages** | logged-out sources only |
| Exa / web search MCP | articles and boards listing trending reels | Claude's built-in WebSearch |
| Edits + metapilot-native MCP | `detectCuts`, `frameSheet`, `audioOnsets` on an MP4 path | `ffmpeg` scene detection (`-vf "select='gt(scene,0.3)',showinfo"`) + frame grabs |
| `yt-dlp` | public YouTube Shorts | skip cross-platform checks |

## 1. Discover reel shortcodes
Best → worst (as of late 2026; sites change — re-check if one fails):
- **imginn.com** tag/profile pages via `nimble_extract {url, driver:"vx10", output_format:"simplified_html"}` → regex `/p/([A-Za-z0-9_-]+)`. (`curl` gets 403; plain-text output drops links; profile pages are huge — save to a file and parse with python.)
- **Sibling posts:** every `instagram_post` result has `more_posts_by_user` (12 shortcodes) — cheap way to go deeper on a good creator.
- **followlly.com/trends/instagram/<niche>** (weekly, ranked by views/day; niche pages work, index may 404).
- **kabo.sh/trending/instagram-reels-this-week** (US top 50, plus some language editions) for global formats.
- **influglue.com** post pages give numeric media ids → `scripts/shortcode.py <id>`.
- Web search for news/listicles embedding reels.
- **Regional niches:** public boards are mostly US/global. For a specific country, use local hashtags/creators (e.g. India: `#goareels`, `#indiatravel`, city/venue tags) on imginn or the secondary-account browser, and the Edits music "For You" tab (regional to the Edits account).
- **Logged-in route (secondary-account browser):**
  - `instagram.com/explore/tags/<tag>/` redirects to keyword search; wait ~4 s, save the snapshot to a file, grep `/p/<shortcode>` (~20 posts, mixed ages; newer shortcodes sort later alphabetically within a length).
  - `/reel/<code>/` opens the Reels viewer: snapshot gives creator, caption, **likes, comments, reposts, shares** (button labels in that order) and the song link `/reels/audio/<id>/` labelled "Artist · Title". The viewer preloads the next feed reels — ignore those (the feed is personalised to the account).
  - `/reels/audio/<id>/` = **sound page: "N reels" using the song + view counts of top reels on it.** Not in the accessibility snapshot, but in `main.innerText` (regex `([\d.,]+[KM]?)\s+reels`). Best "is this song trending" signal: reel count + top views + niche reels using it.
  - **Batch it** (one call): `browser_run_code_unsafe` with an async loop — `page.goto` each URL, `page.waitForTimeout(5000 + random*3000)`, `page.evaluate(fn)`. `require` is unavailable there, so inline the function from `scripts/reel_extract.js`. Tag pages: collect `a[href*="/p/"]` hrefs via evaluate. Keep to ~10 reel pages per run.
  - Then check each song in Edits: `searchMusic` + `getMusicTrackDetails` (popular segments) — feeds reel-maker's song shortlist.
  - Empty `song` = the creator's original audio.
- **YouTube Shorts:** `yt-dlp` downloads public Shorts — useful for cross-platform format checks.
- Known broken (late 2026): Nimble `instagram_audio_page` template (returns empty), picmany (Cloudflare), jolygram via Nimble (times out).

## 2. Fetch
- `nimble_extract_templates_run {template:"instagram_post", params:{post_id:<shortcode>}}` → likes, comments, date, caption, `audio {original_audio_title, ig_artist_username}`, `videos_duration`, `videos[0]` (signed MP4 URL — expires; download promptly).
- `curl -sS -L -o ~/Movies/trend-lab/<niche>/<shortcode>.mp4 '<url>'` (Edits is sandboxed and reads `~/Movies`). Check size > 200 KB. Keep downloads for analysis only; don't redistribute.
- Performance bar: prefer ≥5K likes or ≥100K plays, posted within ~6 months.

## 3. Watch (Edits MCP, path-based — no project needed)
- `detectCuts {id:"", path, start:0, duration, sensitivity:0.5}` → cut times, shot count, avg shot length, flash bursts (runs of 0.1–0.17 s shots).
- `frameSheet {id:"", path, times:"…", columns:10, cellWidth:160}` → hook frame, caption text/style/position, content mix (day/night, people, POV).
- `audioOnsets {id:"", path, …}` → tempo. Song identity comes from the post's `audio` field / the reel's audio link.
- Spoken hooks: `transcribeClip` needs a timeline element (import into a scratch project) — only if the niche is talk-led.
- **Claude can't hear the music.** Record the song from metadata and let the user judge by ear. (Optional: a video-understanding plugin with an audio-capable model can describe music mood/drops, if the user chooses to set one up.)

## 4. Write the trend note
`~/.claude/reel-agent/trends/<niche>-<yyyy-mm>.md`: a table row per reel (shortcode, creator, date, likes/plays, length, cuts, avg shot, opener, caption text/style, song + sound-page reel count) + **Patterns** (what 2+ top reels share) + **Songs to shortlist** (song, why, reel count) + **How to apply** (reconcile with the user's style profile in `~/.claude/reel-agent/style.md` — the user's taste wins on captions and music).
See `trends/example-goa-travel-2026-11.md` for the format.

## Helpers
- `scripts/shortcode.py <numeric_media_id>...` → Instagram shortcodes (base64-style alphabet `A–Z a–z 0–9 - _`).
