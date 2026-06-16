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

// Hybrid resolve: exact normalized match, then substring, then fuzzy >= 0.85.
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
  return best && bestScore >= 0.85 ? best : null;
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
      const fullName = `${item.name} ${comp.name}`.toLowerCase();
      lookup[fullName] = comp.ducats;
    }
  }

  fs.writeFileSync(outPath, JSON.stringify(lookup, null, 2));
  console.log(`Wrote ${Object.keys(lookup).length} entries to ${outPath}`);
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
