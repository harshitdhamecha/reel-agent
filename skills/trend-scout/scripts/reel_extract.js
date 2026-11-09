// Paste as the `function` of playwright browser_evaluate on an instagram.com/reel/<code>/ page
// (logged-in Reels viewer). Returns the FIRST (active) reel only; the viewer preloads more.
() => {
  const m = document.querySelector('main');
  if (!m) return { error: 'no main — logged out or not loaded' };
  const a = m.querySelector('a[href*="/reels/audio/"]');
  let song = a ? a.textContent.replace(/Audio image/g, '').trim() : null;
  if (song && song.length % 2 === 0 && song.slice(0, song.length / 2) === song.slice(song.length / 2)) song = song.slice(0, song.length / 2);
  const lines = m.innerText.split('\n').map(s => s.trim()).filter(Boolean);
  const isNum = s => /^\d[\d.,]*[KM]?$/.test(s);
  const i = lines.findIndex(isNum);
  const counts = i < 0 ? [] : lines.slice(i, i + 4).filter(isNum); // likes, comments, reposts, shares
  return {
    code: location.pathname.split('/').filter(Boolean).pop(),
    creator: lines[0],
    caption: lines.slice(1, i).filter(s => !['•', 'Follow', '.'].includes(s)).join(' ').slice(0, 160),
    likes: counts[0], comments: counts[1], reposts: counts[2], shares: counts[3],
    song, audio: a ? a.getAttribute('href') : null,
  };
}
