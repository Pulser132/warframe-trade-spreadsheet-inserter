# Plan: Visual item thumbnails for scanned trades

Implementation plan for the `UX-Overhaul` feature described in `goal.md`. Renders the 6
receiving-slot items from an OCR scan as thumbnails (icon + name + ducats) in a dedicated,
toggleable row beneath the existing text panels.

## Confirmed decisions (from goal + interview)

1. **Layout** — The thumbnails live in a **dedicated full-width row below** the
   "Current Trade" / "Lifetime Totals" panels. A toggle **shows/hides** that row; the text
   panels always remain in text mode (no in-place swap).
2. **Placeholders** — A single committed neutral placeholder tile (`assets/placeholder.png`,
   a grey "?" pre-sized to the thumb dimensions). Manually-added (ducat-button) slots and
   OCR-unresolved/non-ducat slots show the placeholder + their ducat value. Empty slots
   (fewer than 6 items) render a blank/dim cell.
3. **Image source** — The scanner sources **every** image from
   `assets/item_images/index.json`, keyed by the canonical normalized name it already has for
   both cache hits and freshly-fetched items. **`scripts/wf_ducat_lookup.js` is NOT modified**
   (the goal's proposed resolver `image` field is redundant and omitted).
4. **Persistence** — Toggle state persists in `configs/config.json` under a boolean key
   `"show_thumbnails"` (default `true`), via new `config_manager` helpers mirroring the
   existing `ocr_hotkey` ones (which already preserve unknown keys).
5. **Image mapping rule** — For each component with a ducat value:
   `comp.name === "Blueprint"` → parent `item.imageName` (full prime render); otherwise
   `comp.imageName` (generic per-type icon). Same key space as `data/ducat_lookup.json`.
6. **Thumb size** — Fixed 64×64 px cells. Item images are resized at runtime with Pillow
   (`ImageTk`); the placeholder is pre-sized so it loads via `tk.PhotoImage` without Pillow.

## Deviations from `goal.md` (intentional)

- The goal described the toggle as an in-place **swap** of the "Current Trade" panel content
  and a `"trade_view"` string key. The interview settled on a **show/hide of a separate
  full-width row** with a boolean `"show_thumbnails"` key instead.
- The goal's **step 3 (resolver `image` field in `--resolve-json`)** is dropped — the scanner
  derives all images from `index.json`, so the Node resolver stays unchanged.

---

## Phase 1 — Image bundling script (Node, offline-first)

**Goal:** one regeneratable script that builds the name→file map and downloads every needed
PNG into the committed `assets/item_images/` directory.

- Create **`scripts/fetch_item_images.js`**:
  - Iterate `new Items()` from `@wfcd/items`; for each `item.components` entry **with a ducat
    value** (mirror the `!comp.ducats` filter in `buildIndex`), compute the normalized
    `"<item> <component>"` key (reuse the same `normalize()` logic as `wf_ducat_lookup.js`).
  - Apply the mapping rule: `comp.name === "Blueprint"` → `item.imageName`; else
    `comp.imageName`.
  - Write the sorted `{ normalizedName -> imageFileName }` map to
    **`assets/item_images/index.json`**.
  - Collect the **unique** set of image filenames (de-duped so the ~14 shared generic icons
    download once). For each, download from `https://cdn.warframestat.us/img/<file>` using
    Node's built-in `https` module — **follow 301/302 redirects** (CDN redirects to
    `raw.githubusercontent.com`). Skip files already present on disk.
  - Report counts: total mappings, unique images, downloaded, skipped, failed.
  - Create `assets/item_images/` if absent.
- Add a **`"fetch-images"`** alias to `scripts/package.json` (mirroring `"generate"`).
- `assets/item_images/` (PNGs + `index.json`) is committed (the `assets/` tree is tracked;
  `.gitignore` ignores `data/` and `configs/`, not `assets/`).

**Verify:** `cd scripts && npm install && npm run fetch-images` → ~171 PNGs + `index.json`;
re-running skips already-present files.

## Phase 2 — Neutral placeholder asset

- Create **`assets/placeholder.png`** — a simple neutral grey tile with a "?" glyph, sized
  64×64 to match the thumb dimensions (so it loads via `tk.PhotoImage`, no Pillow resize
  needed). Generate once (e.g. a throwaway Pillow snippet) and commit the PNG.

## Phase 3 — Scanner image field (`ocr_scanner.py`)

- Add an index loader, e.g. `_load_image_index(path)` reading
  `assets/item_images/index.json`; a missing file returns `{}` (not an error), consistent
  with `_load_lookup`.
- In `scan()`, after entries are finalized, set an `"image"` key on every entry:
  - resolved (`source` in `cache`/`fetched`) → `index.get(entry["name"])` (may be `None` if
    the index lacks a mapping).
  - unresolved placeholder → `None`.
- Update the `scan()` docstring to document the new `"image"` field in each result dict.
- **No change** to `wf_ducat_lookup.js`.

**Verify:** `python tests/ocr_offline_test.py` resolved slots carry an `image` filename that
exists under `assets/item_images/`.

## Phase 4 — App state & thumbnail UI (`app.py`)

**Parallel slot metadata**

- Add `self.trade_items: list[dict]`, kept in lockstep with `self.history`. Each entry:
  `{"name": str|None, "ducats": int, "image": str|None, "source": str}`.
- `add_item(self, ducat_value, item=None)` — append to `history` as today; also append to
  `trade_items`: when `item` is provided (from a scan) use its `name`/`image`/`source`;
  otherwise a manual add → `{"name": None, "ducats": ducat_value, "image": None,
  "source": "manual"}`. Keep the `TRADE_ITEM_LIMIT` guard governing both lists.
- `undo_item` pops both lists; `reset_trade` clears both; `log_trade` clears both (via
  `reset_trade`).
- `scan_trade_window` passes each result dict to `add_item(item["ducats"], item=item)` so
  `trade_items` carries name/image/source.

**Thumbnail row**

- New constant for the dir: `ITEM_IMAGES_DIR = assets/item_images`.
- Build a full-width `ttk.LabelFrame` (e.g. "Trade Items") below `middle_frame`. Re-grid the
  existing rows: ducat frame (0), middle_frame (1), **thumbnail frame (2)**, controls (3),
  status (4) — shift `controls_frame` and `_status_label` down by one row.
- 6 fixed cells (`TRADE_ITEM_LIMIT`), each a small frame with: an image `ttk.Label` (64×64),
  a name `ttk.Label` (wraplength ~80, up to ~2 lines, title-cased; blank for manual/empty),
  and a ducat `ttk.Label`.
- `refresh_thumbnails()` renders the 6 cells from `self.trade_items`:
  - filled + has resolvable image file → load `assets/item_images/<file>`, resize to 64×64
    via Pillow `ImageTk`, show it + name + ducats.
  - filled but no image (manual/unresolved) or image file missing → placeholder + ducats
    (and a small "manual"/"unresolved" hint for the name line).
  - empty slot → placeholder dimmed / blank cell, no text.
  - **Hold every `PhotoImage` on `self`** (e.g. `self._thumb_images = [...]`) so Tk doesn't
    garbage-collect them.
- Call `refresh_thumbnails()` from `refresh_display()` (or directly after every
  `history`/`trade_items` mutation) so the row stays live.

**Graceful fallback**

- Lazy `from PIL import Image, ImageTk` inside the render path. If Pillow is missing or an
  image file can't be loaded, fall back to the placeholder + text; never raise. (OCR already
  requires Pillow, so this only matters for manual use without OCR deps.)

**Toggle**

- A `ttk.Checkbutton` ("Show item thumbnails") — placed near the thumbnail frame or in the
  controls area — bound to a `tk.BooleanVar`. Its command does `grid()` / `grid_remove()` on
  the thumbnail frame and persists the new value via `save_show_thumbnails()`.
- On startup, initialize the var and the frame's visibility from `load_show_thumbnails()`.
  Because the window is `resizable(False, False)`, showing/hiding the row lets Tk re-fit the
  window height automatically.

## Phase 5 — Config persistence (`config_manager.py`)

- Add `load_show_thumbnails()` → reads `"show_thumbnails"` from `config.json`, default
  `True`; and `save_show_thumbnails(value)` → writes the key preserving all other keys.
  Mirror the existing `load_ocr_hotkey`/`save_ocr_hotkey` pair.

## Phase 6 — Docs & tests

- **`CLAUDE.md`**: document the new `assets/item_images/` dir + `index.json`,
  `scripts/fetch_item_images.js` / `npm run fetch-images`, `assets/placeholder.png`, the
  scanner's new `"image"` field, the thumbnail row + show/hide toggle, the parallel
  `trade_items` state, and the `"show_thumbnails"` config key. Note that the resolver is
  intentionally unchanged.
- **`tests/ocr_offline_test.py`**: optionally assert each resolved entry carries an `"image"`
  filename that exists under `assets/item_images/`; do not require it for unresolved slots.
  Keep the skip-clean behavior when deps/images are absent.

## Phase 7 — Verification (manual, per goal)

1. `cd scripts && npm install && npm run fetch-images` → `assets/item_images/` fills with
   ~171 PNGs + `index.json`; re-running skips existing files.
2. `python tests/ocr_offline_test.py` → resolved slots include an `image` filename present
   under `assets/item_images/`.
3. `python main.py` → run an OCR scan (F8): the thumbnail row shows 6 cells, the main
   Blueprint slot as a full prime render and components as generic icons; manual/unresolved
   slots show the placeholder; the toggle hides/shows the row and the choice persists across
   restarts.

## Out of scope

- No image for manually-added (button) items (placeholder only — no item identity).
- Top-panel (player's own offered) items remain ignored; receiving panel only.
- `settings_window.py` is unchanged (the toggle lives on the main window).
