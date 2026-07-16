import sharp from 'sharp';
import satori from 'satori';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Candidate caption fonts. Default = Poppins (closest to the TikTok caption look).
const FONT_DATA = {
  Poppins:    { data: readFileSync(join(__dirname, '../fonts/Poppins-SemiBold.ttf')), weight: 600 },
  Montserrat: { data: readFileSync(join(__dirname, '../fonts/Montserrat-Bold.ttf')),  weight: 700 },
  Nunito:     { data: readFileSync(join(__dirname, '../fonts/Nunito-Bold.ttf')),      weight: 700 },
  TikTokSans: { data: readFileSync(join(__dirname, '../fonts/TikTokSans36pt-Bold.otf')), weight: 700 },
};
const DEFAULT_FONT = 'TikTokSans';

const PROJECT_REF = 'qlcmgxgwpzmiebzxflai';
const BG_BUCKET = 'rich-life-images';
const SB_PUBLIC = `https://${PROJECT_REF}.supabase.co/storage/v1/object/public/${BG_BUCKET}`;

// Each pillar auto-discovers its backgrounds from a dedicated bucket folder.
// Drop a new image into bg/<pillar>/ in the bucket and it's picked up on the
// next render — no code change needed.
const PILLAR_FOLDER = {
  bw_gatekeeping: 'bg/bwc',
  strong_informational: 'bg/si',
  rich_life: 'bg/lavish',
};

// Static fallback (used only if the dynamic bucket listing fails). One
// character's folder per pillar so even the fallback never mixes characters.
// Layout 2026-07-02: bg/<pillar>/char2|char3/ — see listCharacterPools().
const BG_POOLS = {
  bw_gatekeeping: [
    'bg/bwc/char3/Img1_crop.png',
    'bg/bwc/char3/cover_INF-008_leg_machine_seated.jpg',
    'bg/bwc/char3/cover_Img2.png','bg/bwc/char3/cover_Img3.png',
    'bg/bwc/char3/cover_Img5.png','bg/bwc/char3/cover_Img6.png','bg/bwc/char3/cover_Img7.png',
    'bg/bwc/char3/cover_winner_08_gym_selfie_back_turned_bright.png',
    'bg/bwc/char3/cover_winner_09_gym_selfie_close_chest_bright.png',
  ],
  strong_informational: [
    'bg/si/char3/Img1_crop.png',
    'bg/si/char3/cover_INF-008_leg_machine_seated.jpg',
    'bg/si/char3/cover_Img2.png','bg/si/char3/cover_Img3.png',
    'bg/si/char3/cover_Img5.png','bg/si/char3/cover_Img6.png','bg/si/char3/cover_Img7.png',
    'bg/si/char3/cover_winner_08_gym_selfie_back_turned_bright.png',
    'bg/si/char3/cover_winner_09_gym_selfie_close_chest_bright.png',
  ],
  rich_life: [
    'bg/lavish/char2/IMG-002_kitchen_island_dawn.jpg','bg/lavish/char2/IMG-021_poolside_teak_lounger.jpg',
    'bg/lavish/char2/cover_IMG-001_closet_walk_in.jpg','bg/lavish/char2/cover_IMG-006_valet_range_rover.jpg',
    'bg/lavish/char2/cover_IMG-007_yacht_deck_legs.jpg','bg/lavish/char2/cover_IMG-009_suv_red_bottoms.jpg',
    'bg/lavish/char2/cover_IMG-020_jet_stairs_LV_keepall.jpg','bg/lavish/char2/cover_IMG-032_brunch_champagne_watch.jpg',
  ],
};

// --- Character-aware pool discovery -------------------------------------
// Layout: bg/<pillar>/<character>/*.png|jpg  — one subfolder per character.
// A carousel locks to ONE character: every slide pulls from that character's
// folder only (different poses, same woman). Loose files directly in
// bg/<pillar>/ still work as a legacy "_loose" group so old layouts render.
async function listStorage(prefix) {
  const r = await fetch(
    `https://${PROJECT_REF}.supabase.co/storage/v1/object/list/${BG_BUCKET}`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ prefix, limit: 1000 }),
    }
  );
  if (!r.ok) return null;
  return r.json();
}

// Returns { charName: [paths...] } for the pillar, or null if the top-level
// listing fails (caller then uses the static fallback). A FAILED subfolder
// listing throws instead of silently dropping that character — a missing
// character would skew rotation invisibly.
async function listCharacterPools(pillar) {
  const folder = PILLAR_FOLDER[pillar];
  let items;
  try {
    items = await listStorage(folder + '/');
  } catch {
    return null;
  }
  if (!items) return null;
  const pools = {};
  const loose = items
    .filter((i) => i && i.id && /\.(png|jpe?g)$/i.test(i.name))
    .map((i) => `${folder}/${i.name}`);
  const subfolders = items.filter((i) => i && i.id == null).map((i) => i.name);
  const listings = await Promise.all(
    subfolders.map((sf) => listStorage(`${folder}/${sf}/`))
  );
  subfolders.forEach((sf, idx) => {
    if (!listings[idx]) throw new Error(`listing failed for ${folder}/${sf}/`);
    const files = listings[idx]
      .filter((i) => i && i.id && /\.(png|jpe?g)$/i.test(i.name))
      .map((i) => `${folder}/${sf}/${i.name}`);
    if (files.length) pools[sf] = files;
  });
  // Loose files only count when there are no character subfolders — once the
  // per-character layout exists, stray loose files must not become a pickable
  // mixed-women pseudo-character.
  if (!Object.keys(pools).length && loose.length) pools._loose = loose;
  return Object.keys(pools).length ? pools : null;
}

const W = 1080, H = 1350;
const TEXT_W = W - 140;      // usable text width (70px side padding)
const MAX_BLOCK_H = H * 0.72; // text block must fit within 72% of frame height

// Crisp black outline ring + blurred dark halo so white text stays readable
// over ANY background (incl. bright windows / white walls) without a visible box.
function legibilityShadow(ringPx) {
  const dirs = [];
  for (let dx = -ringPx; dx <= ringPx; dx++) {
    for (let dy = -ringPx; dy <= ringPx; dy++) {
      if (dx === 0 && dy === 0) continue;
      dirs.push(`${dx}px ${dy}px 0 #000`);
    }
  }
  // blurred dark halo — this is what saves bright backgrounds
  dirs.push('0px 0px 12px rgba(0,0,0,0.95)');
  dirs.push('0px 0px 22px rgba(0,0,0,0.85)');
  dirs.push('0px 3px 6px rgba(0,0,0,0.9)');
  return dirs.join(', ');
}

// Auto-fit: pick the largest font (and matching wrap width) where the whole
// text block fits within MAX_BLOCK_H. Long copy shrinks instead of overflowing.
function fitText(text) {
  const t = String(text || '').trim();
  for (let fontSize = 60; fontSize >= 34; fontSize -= 2) {
    const charW = fontSize * 0.54;                         // avg glyph advance
    const maxChars = Math.max(8, Math.floor(TEXT_W / charW));
    const lines = wrapByChars(t, maxChars);
    const blockH = lines.length * fontSize * 1.28;
    if (blockH <= MAX_BLOCK_H) return { fontSize, lines };
  }
  const charW = 34 * 0.54;
  return { fontSize: 34, lines: wrapByChars(t, Math.floor(TEXT_W / charW)) };
}

function wrapByChars(text, maxChars) {
  const words = text.split(' ');
  const lines = [];
  let cur = '';
  for (const w of words) {
    if (cur && (cur + ' ' + w).length > maxChars) { lines.push(cur); cur = w; }
    else cur = cur ? cur + ' ' + w : w;
  }
  if (cur) lines.push(cur);
  return lines;
}

async function makeTextPng(text, fontName) {
  const { weight } = FONT_DATA[fontName];
  const { fontSize, lines } = fitText(text);
  const ringPx = fontSize >= 52 ? 3 : 2;

  const lineNodes = lines.map(line => ({
    type: 'div',
    props: {
      style: {
        display: 'flex', justifyContent: 'center', width: '100%',
        color: '#ffffff', fontSize, fontWeight: weight,
        fontFamily: fontName, lineHeight: 1.28, textAlign: 'center',
        textShadow: legibilityShadow(ringPx),
      },
      children: [line],
    },
  }));

  const svg = await satori(
    {
      type: 'div',
      props: {
        style: {
          width: W, height: H, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', padding: '0 70px',
        },
        children: lineNodes,
      },
    },
    { width: W, height: H, fonts: [{ name: fontName, data: FONT_DATA[fontName].data, weight, style: 'normal' }] }
  );

  return sharp(Buffer.from(svg)).png().toBuffer();
}

async function fetchBg(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error('bg fetch failed: ' + r.status);
  return Buffer.from(await r.arrayBuffer());
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'POST only' });

  let body = req.body;
  if (typeof body === 'string') { try { body = JSON.parse(body); } catch { body = {}; } }

  const { carousel_id, pillar, slide_1, slide_2, slide_3, slide_4, slide_5, slide_6, slide_7 } = body || {};
  const fontName = Object.prototype.hasOwnProperty.call(FONT_DATA, body?.font) ? body.font : DEFAULT_FONT;

  // Unknown pillar must fail loudly — a silent bw_gatekeeping fallback renders
  // the wrong pillar's characters (e.g. legacy transformation_simple_character_2
  // rows would get BWC gym imagery) with no error signal.
  if (!carousel_id || typeof carousel_id !== 'string') {
    return res.status(400).json({ error: 'carousel_id required' });
  }
  if (!PILLAR_FOLDER[pillar]) {
    return res.status(400).json({ error: `Unknown pillar "${pillar}" — expected one of: ${Object.keys(PILLAR_FOLDER).join(', ')}` });
  }

  // Auto-discover the pillar's character pools from the bucket; fall back to
  // the static list (as one single-character pool) if listing fails.
  let pools;
  try {
    pools = await listCharacterPools(pillar);
  } catch (e) {
    return res.status(502).json({ error: 'Background pool listing failed: ' + e.message });
  }
  if (!pools) pools = { _fallback: BG_POOLS[pillar] };

  const slideTexts = [slide_1, slide_2, slide_3, slide_4, slide_5, slide_6, slide_7]
    .map((s) => (typeof s === 'string' ? s.trim() : ''))
    .filter(Boolean);
  if (!slideTexts.length) return res.status(400).json({ error: 'No slide text provided' });

  function shuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  // Lock the whole carousel to ONE character so slides never mix people.
  // `body.character` forces a specific pool; otherwise pick a random character
  // among those with enough images to give every slide a distinct background
  // (fall back to all characters if none is big enough). Equal weight per
  // character so no pool dominates.
  const charNames = Object.keys(pools);
  let charName = body?.character && pools[body.character] ? body.character : null;
  if (!charName) {
    const bigEnough = charNames.filter((c) => pools[c].length >= slideTexts.length);
    const candidates = bigEnough.length ? bigEnough : charNames;
    charName = candidates[Math.floor(Math.random() * candidates.length)];
  }
  const pool = pools[charName];

  // First-image rule: slide 1 must be a designated cover (filename prefixed
  // `cover_` in the bucket — sourced from carousel_images.image_type='first image'
  // / hook_priority>=9). Slides 2+ take distinct images from the rest of the
  // same character's pool. If the pool has no cover, fall back to a plain
  // shuffle so nothing ever fails to render.
  const isCover = (p) => /(^|\/)cover_/.test(p);
  const coversInPool = pool.filter(isCover);
  let order;
  if (coversInPool.length && !body?.bg) {
    const cover = coversInPool[Math.floor(Math.random() * coversInPool.length)];
    order = [cover, ...shuffle(pool.filter((p) => p !== cover))];
  } else {
    order = shuffle(pool);
  }
  const coverUsed = coversInPool.length && !body?.bg ? order[0] : null;
  const bgCache = {};
  async function getBg(name) {
    if (!bgCache[name]) bgCache[name] = await fetchBg(SB_PUBLIC + '/' + name);
    return bgCache[name];
  }

  const images = [];
  const usedBgs = [];
  for (let i = 0; i < slideTexts.length; i++) {
    const bgName = body?.bg ? body.bg : order[i % order.length];
    usedBgs.push(bgName);
    let bgBuffer;
    try {
      bgBuffer = await getBg(bgName);
    } catch (e) {
      return res.status(502).json({ error: 'Could not fetch background: ' + e.message });
    }
    const textPng = await makeTextPng(slideTexts[i], fontName);
    const jpeg = await sharp(bgBuffer)
      .resize(W, H, { fit: 'cover', position: 'top' })
      .composite([{ input: textPng, blend: 'over' }])
      .jpeg({ quality: 88 })
      .toBuffer();
    images.push({ filename: `slide_0${i + 1}.jpg`, data: jpeg.toString('base64') });
  }

  const SBK = process.env.SUPABASE_SERVICE_KEY;
  const PROJECT = 'qlcmgxgwpzmiebzxflai';
  const BUCKET = 'carousel-renders';
  const slideUrls = {};

  // Per-file retry (3 attempts) so one transient storage blip can't strand a
  // carousel half-overwritten with two different characters at the live URLs.
  async function uploadWithRetry(img) {
    const uploadUrl = `https://${PROJECT}.supabase.co/storage/v1/object/${BUCKET}/${encodeURIComponent(carousel_id)}/${encodeURIComponent(img.filename)}`;
    let lastErr = '';
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        const uploadRes = await fetch(uploadUrl, {
          method: 'POST',
          headers: { Authorization: `Bearer ${SBK}`, 'Content-Type': 'image/jpeg', 'x-upsert': 'true' },
          body: Buffer.from(img.data, 'base64'),
        });
        if (uploadRes.ok) return null;
        lastErr = await uploadRes.text();
      } catch (e) {
        lastErr = e.message;
      }
      await new Promise((r) => setTimeout(r, 400 * attempt));
    }
    return lastErr;
  }

  for (const img of images) {
    const err = await uploadWithRetry(img);
    if (err) {
      return res.status(502).json({ error: `Upload failed for ${img.filename} after 3 attempts: ${err}` });
    }
    const idx = parseInt(img.filename.replace(/\D/g,'')) || (images.indexOf(img) + 1);
    slideUrls[`slide_${idx}_url`] = `https://${PROJECT}.supabase.co/storage/v1/object/public/${BUCKET}/${encodeURIComponent(carousel_id)}/${encodeURIComponent(img.filename)}`;
  }

  res.json({ carousel_id, font: fontName, character: charName, characters_available: charNames, cover: coverUsed, bgs: usedBgs, pool_size: pool.length, rendered_at: new Date().toISOString(), ...slideUrls });
}
