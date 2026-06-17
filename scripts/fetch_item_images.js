#!/usr/bin/env node
/**
 * Bundle item thumbnail images for the trade UI, using @wfcd/items.
 *
 * Builds a normalized "<item> <component>" name -> image filename map (same
 * key space as data/ducat_lookup.json) and downloads every unique image into
 * assets/item_images/ so the app can render thumbnails fully offline.
 *
 * Usage:
 *   node fetch_item_images.js
 */

const fs = require("fs");
const path = require("path");
const https = require("https");
const Items = require("@wfcd/items");

const OUT_DIR = path.join(__dirname, "..", "assets", "item_images");
const INDEX_PATH = path.join(OUT_DIR, "index.json");
const CDN_BASE = "https://cdn.warframestat.us/img/";

function normalize(s) {
  return String(s)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function buildImageIndex() {
  const index = {};
  for (const item of new Items()) {
    if (!item.components) continue;
    for (const comp of item.components) {
      if (!comp.ducats) continue;
      const name = normalize(`${item.name} ${comp.name}`);
      const image = comp.name === "Blueprint" ? item.imageName : comp.imageName;
      if (image) index[name] = image;
    }
  }
  return Object.fromEntries(Object.entries(index).sort(([a], [b]) => a.localeCompare(b)));
}

function download(url, destPath, redirectsLeft = 5) {
  return new Promise((resolve, reject) => {
    if (redirectsLeft < 0) {
      reject(new Error(`Too many redirects for ${url}`));
      return;
    }
    https
      .get(url, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          res.resume();
          download(res.headers.location, destPath, redirectsLeft - 1).then(resolve, reject);
          return;
        }
        if (res.statusCode !== 200) {
          res.resume();
          reject(new Error(`HTTP ${res.statusCode} for ${url}`));
          return;
        }
        const tmpPath = destPath + ".tmp";
        const file = fs.createWriteStream(tmpPath);
        res.pipe(file);
        file.on("finish", () => {
          file.close((err) => {
            if (err) {
              reject(err);
              return;
            }
            fs.renameSync(tmpPath, destPath);
            resolve();
          });
        });
        file.on("error", reject);
      })
      .on("error", reject);
  });
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const index = buildImageIndex();
  fs.writeFileSync(INDEX_PATH, JSON.stringify(index, null, 2));

  const uniqueImages = [...new Set(Object.values(index))].sort();

  let downloaded = 0;
  let skipped = 0;
  let failed = 0;

  for (const file of uniqueImages) {
    const destPath = path.join(OUT_DIR, file);
    if (fs.existsSync(destPath)) {
      skipped++;
      continue;
    }
    try {
      await download(CDN_BASE + file, destPath);
      downloaded++;
    } catch (e) {
      failed++;
      console.error(`Failed to download ${file}: ${e.message}`);
    }
  }

  console.log(
    `Mappings: ${Object.keys(index).length}, unique images: ${uniqueImages.length}, ` +
      `downloaded: ${downloaded}, skipped: ${skipped}, failed: ${failed}`
  );
  console.log(`Wrote ${INDEX_PATH}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
