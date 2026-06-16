#!/usr/bin/env node
/**
 * Warframe ducat value lookup using @wfcd/items.
 *
 * Usage:
 *   node wf_ducat_lookup.js <search term>   — print matching items and ducat values
 *   node wf_ducat_lookup.js --generate      — write full data/ducat_lookup.json
 */

const fs = require("fs");
const path = require("path");
const Items = require("@wfcd/items");

const args = process.argv.slice(2);

function normalize(s) {
  return String(s)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function buildIndex() {
  const index = [];
  for (const item of new Items()) {
    if (!item.components) continue;
    for (const comp of item.components) {
      if (!comp.ducats) continue;
      const name = `${item.name} ${comp.name}`;
      index.push({ name, norm: normalize(name), ducats: comp.ducats });
    }
  }
  return index;
}

function levenshtein(a, b) {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = new Array(n + 1);
  let curr = new Array(n + 1);
  for (let j = 0; j <= n; j++) prev[j] = j;
  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[n];
}

function ratio(a, b) {
  const maxLen = Math.max(a.length, b.length) || 1;
  return 1 - levenshtein(a, b) / maxLen;
}

// Similarity of two tokens. Beyond edit-distance, treat one token containing the
// other as a strong match so a merged OCR token (e.g. "chromapnrrt" for
// "chroma" + "prime") still anchors on its embedded name.
function tokenSim(a, b) {
  const r = ratio(a, b);
  const [short, long] = a.length <= b.length ? [a, b] : [b, a];
  if (short.length >= 4 && long.includes(short)) return Math.max(r, 0.9);
  return r;
}

// Best per-token similarity of `token` against any token in `pool`.
function bestTokenRatio(token, pool) {
  let best = 0;
  for (const p of pool) {
    const r = tokenSim(token, p);
    if (r > best) best = r;
  }
  return best;
}

// Token-overlap fallback for labels with a mid-word OCR misread (e.g. the small
// first line of two-line warframe-component labels reads "Print"/"Prnmie" for
// "Prime"). Anchors on the distinctive leading name token, then scores each
// candidate by how well its tokens align with the query's. The in-game label
// appends "Blueprint" to component names that @wfcd stores without it, so a
// trailing "blueprint" on a 4+ token query is dropped before matching.
function resolveByTokens(q, index) {
  // The game appends "Blueprint" to component names (Chassis/Neuroptics/Systems)
  // that @wfcd stores without it. Drop a trailing "blueprint" when it follows a
  // component word (anything but "prime") so it doesn't tie with the warframe's
  // main "<name> prime blueprint". A genuine main BP ends "...prime blueprint",
  // so it's kept.
  let qToks = q.split(" ").filter(Boolean);
  const n = qToks.length;
  if (n >= 3 && qToks[n - 1] === "blueprint" && qToks[n - 2] !== "prime") {
    qToks = qToks.slice(0, -1);
  }
  // "prime" is in every candidate, so it's non-discriminative — score on the
  // name + component tokens, which is also why a misread "prime" doesn't matter.
  const discriminative = (toks) => toks.filter((t) => t !== "prime");
  qToks = discriminative(qToks);
  if (qToks.length === 0) return null;

  let best = null;
  let bestScore = 0;
  for (const it of index) {
    const cToks = discriminative(it.norm.split(" ").filter(Boolean));
    if (cToks.length === 0) continue;
    if (bestTokenRatio(cToks[0], qToks) < 0.85) continue; // leading name token
    let sum = 0;
    for (const ct of cToks) sum += bestTokenRatio(ct, qToks);
    const score = sum / cToks.length;
    if (score > bestScore) {
      bestScore = score;
      best = it;
    }
  }
  return best && bestScore >= 0.8 ? best : null;
}

// Hybrid resolve: exact normalized match, substring, whole-string fuzzy >= 0.85,
// then a token-overlap fallback for mid-word misreads on multi-word labels.
function resolveOne(query, index) {
  const q = normalize(query);
  if (!q) return null;

  for (const it of index) {
    if (it.norm === q) return it;
  }

  let best = null;
  if (q.length >= 6) {
    for (const it of index) {
      if (it.norm.includes(q) || q.includes(it.norm)) {
        if (!best || it.norm.length < best.norm.length) best = it;
      }
    }
    if (best) return best;
  }

  best = null;
  let bestScore = 0;
  for (const it of index) {
    const score = ratio(q, it.norm);
    if (score > bestScore) {
      bestScore = score;
      best = it;
    }
  }
  if (best && bestScore >= 0.85) return best;

  return resolveByTokens(q, index);
}

if (args[0] === "--resolve-json") {
  // Batched, machine-readable resolver for ocr_scanner.py cache misses.
  const queries = args.slice(1);
  const index = buildIndex();
  const out = queries.map((q) => {
    const match = resolveOne(q, index);
    return {
      query: q,
      name: match ? match.norm : null,
      ducats: match ? match.ducats : null,
    };
  });
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
}

if (args[0] === "--generate") {
  const outPath = path.join(__dirname, "..", "data", "ducat_lookup.json");
  fs.mkdirSync(path.dirname(outPath), { recursive: true });

  const lookup = {};
  for (const item of new Items()) {
    if (!item.components) continue;
    for (const comp of item.components) {
      if (!comp.ducats) continue;
      const fullName = normalize(`${item.name} ${comp.name}`);
      lookup[fullName] = comp.ducats;
    }
  }

  const sorted = Object.fromEntries(Object.entries(lookup).sort(([a], [b]) => a.localeCompare(b)));
  fs.writeFileSync(outPath, JSON.stringify(sorted, null, 2));
  console.log(`Wrote ${Object.keys(sorted).length} entries to ${outPath}`);
  process.exit(0);
}

const query = args.join(" ").trim().toLowerCase();
if (!query) {
  console.error("Usage: node wf_ducat_lookup.js <item name>");
  console.error("       node wf_ducat_lookup.js --generate");
  process.exit(1);
}

const results = [];
for (const item of new Items()) {
  if (!item.components) continue;
  for (const comp of item.components) {
    if (!comp.ducats) continue;
    const fullName = `${item.name} ${comp.name}`.toLowerCase();
    if (fullName.includes(query)) {
      results.push({ name: `${item.name} ${comp.name}`, ducats: comp.ducats });
    }
  }
}

if (results.length === 0) {
  console.log(`No items found matching "${args.join(" ")}"`);
} else {
  results.sort((a, b) => a.name.localeCompare(b.name));
  results.forEach((r) => console.log(`${r.name}: ${r.ducats} ducats`));
}
