# `e2e_share` rendering / figure pipeline

End-to-end pipeline that turns a folder of `e2e_share_*` per-asset GLBs into
a side-by-side PowerPoint deck comparing every method and modality, with
optional zoom-in insets.

## Layout

```
blender-render-toolkit/
├── blender_glb.py         # generic single-shot GLB renderer (used by batch_render.py)
└── e2e_share/
    ├── README.md          # (this file)
    ├── batch_render.py    # 1. render every (asset × method × modality) PNG
    ├── crop_results.py    # 2. interactively pick a square crop region per asset
    └── create_pptx.py     # 3. compile inputs + renders + insets into a .pptx
```

## Expected input data layout

The pipeline assumes you have an `e2e_share_<date>` data dump that looks
like this (referred to as `<DATA_ROOT>` below):

```
e2e_share_2026-05-12/
├── data/
│   ├── captions.csv                # rows: uid, collection, caption, edit_instruction
│   └── per_asset/
│       ├── <uid>/
│       │   ├── color.png           # reference renders
│       │   ├── geo_normal.png
│       │   ├── tex_normal_ws.png
│       │   ├── caption.txt
│       │   ├── edit_instruction.txt
│       │   ├── org.glb             # method outputs
│       │   ├── hy.glb
│       │   ├── mv.glb              # may be missing for some assets
│       │   ├── v1.glb
│       │   └── v4.glb
│       └── ...
```

Renders go into a sibling folder `<RENDER_ROOT>` (this repo never writes
inside `<DATA_ROOT>`). For convenience all examples below use the dump at
`SIGGRAPHAsia26/e2e_share_2026-05-12/`.

## Setup

```bash
# python ≥ 3.10
conda create -n e2e_share python=3.11 -y
conda activate e2e_share
pip install bpy==4.2.0 python-pptx pillow matplotlib
```

Apple-Silicon Macs: `bpy` ships a Metal Cycles backend, which `blender_glb.py`
auto-detects. CUDA is preferred when available.

## 1. Render every method / modality

```bash
DATA=/Users/kdeng/Repos/BlenderToolbox/SIGGRAPHAsia26/e2e_share_2026-05-12
python e2e_share/batch_render.py \
    --per_asset_dir $DATA/data/per_asset \
    --output_root   $DATA/../e2e_share_2026-05-12_renders \
    --samples 64 --resolution 720
```

Per `(asset, method, modality)` this writes
`<RENDER_ROOT>/<uid>/<method>_<modality>.png`.

Notable flags:

* `--assets <uid> [<uid> ...]` — restrict to specific assets
  (defaults: all subfolders of `--per_asset_dir`)
* `--methods` — defaults to `org hy mv v1 v4`
* `--modalities` — defaults to `full_color normal`
* `--hires_factor 3.0` — additionally render `<method>_<modality>_hires.png`
  at 3× the regular resolution (same camera, same model scale; useful as a
  source for `crop_results.py`)
* `--start_rot_x` / `--start_rot_z` — degrees, applied after auto-fit
* `--target_size` — longest bbox edge after auto-fit (default `2.0`)
* `--overwrite` — re-render even if the file exists (default skips)
* `--keep_ground` / `--keep_helper_sphere` — keep the studio-blend props
  (defaults hide them; output PNGs have a transparent background and no shadow)

The script opens `load/studio_bg_static.blend` once, then loops through every
job in the same `bpy` process so the studio lighting's importance-map cost
(~50 s) is paid only once. Typical throughput on an Apple-Silicon Mac is
2–4 s/render at 720 px and ~8 s/render at 2160 px.

GLBs that don't exist (e.g. some assets are missing `mv.glb`) are logged as
`[batch] missing: ...` and skipped.

## 2. Pick a crop region per asset (optional, for zoom-in insets)

For each asset you'd like a zoom-in for, open the picker and draw a box on
the reference render. The box is automatically squared (max of width/height)
and applied identically to every `*_hires.png` of that asset.

```bash
RENDER=$DATA/../e2e_share_2026-05-12_renders
python e2e_share/crop_results.py --render_root $RENDER \
    12321371e98d41b4afe98796a529cf17 \
    70693700d33180ba3afa469dabfef74e \
    019be0c912ed4e1982a40ef96f105085
```

Controls:

* Click + drag to select. The squared region is drawn back on top in dashed
  green so you see what will be saved.
* `r` to reset; `Enter` (or close window) to confirm.
* `--bbox X Y W H` to skip the picker and supply pixel coordinates manually
  (non-square input is auto-expanded to `side = max(W, H)` and re-centred).
* `--reuse_saved_bbox` to re-apply previously-picked bboxes (e.g. after
  re-rendering).
* `--ref some_other_render.png` to pick on a different reference render
  (default `v4_full_color_hires.png`).
* `--source_suffix _hires.png --output_suffix _crop.png` to control which
  files get cropped and what suffix the cropped versions use (defaults shown).

For each asset this writes
`<RENDER>/<uid>/<method>_<modality>_crop.png` and a
`<RENDER>/<uid>/crop_bbox.json` record (so the choice is reproducible).

## 3. Compile the PowerPoint

```bash
python e2e_share/create_pptx.py \
    --data_root   $DATA/data/per_asset \
    --render_root $RENDER \
    --captions    $DATA/data/captions.csv \
    --output      $DATA/../e2e_share_2026-05-12_renders.pptx \
    --assets      \
        12321371e98d41b4afe98796a52 \
        70693700d33180ba3afa469dabf \
        019be0c912ed4e1982a40ef96f1 \
        0523259081dd4a3eaa3567071f1 \
        1a49b0714571487d9164b9ba13d \
        31ab9f9ad2fa425aa75e8bb76ca
```

Layout: one column per example. Within each column the rows are

```
[uid + caption]
[geo_normal]                       <- input refs
[color | tex_normal_ws]            <- both on a single row, half width
[v4 full_color]                    <- methods (FC + N tightly stacked)
[v4 normal]
[org full_color]
[org normal]
[hy full_color]
[hy normal]
[mv full_color]
[mv normal]
```

When `<key>_crop.png` exists for any render cell, it is overlaid as a corner
inset on top of that cell (no layout change, no extra rows). Cells whose
crop hasn't been picked simply render without an inset.

Notable behaviour and constants (top of `create_pptx.py`):

* Asset names accept any unique prefix of a real folder name; truncated /
  typo'd entries are normalised via `resolve_asset()` and `MANUAL_ALIAS`.
* `METHODS` defaults to `["v4", "org", "hy", "mv"]` — `v1` is intentionally
  omitted in this deck.
* `INPUT_KEYS` defaults to `["geo_normal", "color", "tex_normal_ws"]`.
* `INSET_FRAC` (0.42), `INSET_CORNER` (`bottom_right`), `INSET_PAD`,
  `INSET_BORDER_PT` — knobs for the zoom-in inset overlay.
* `COLS_PER_SLIDE` (6) — additional examples spill onto further slides.
* `GROUP_GAP` / `METHOD_GAP` / `PAIR_GAP` — vertical spacing between
  the input block, between method pairs, and within a `(FC, N)` pair.

## End-to-end one-liner (assuming the data dump is at `$DATA`)

```bash
DATA=/path/to/e2e_share_2026-05-12
RENDER=/path/to/e2e_share_2026-05-12_renders

# 1. render the regular and hires variants
python e2e_share/batch_render.py \
    --per_asset_dir $DATA/data/per_asset \
    --output_root   $RENDER \
    --hires_factor  3.0

# 2. (optional) pick crops for the assets you care about
python e2e_share/crop_results.py --render_root $RENDER <uid1> <uid2> ...

# 3. compile the deck
python e2e_share/create_pptx.py \
    --data_root   $DATA/data/per_asset \
    --render_root $RENDER \
    --captions    $DATA/data/captions.csv \
    --output      $RENDER/../results.pptx \
    --assets      <uid1> <uid2> ...
```

## Output file naming summary

| File | Source | Notes |
|---|---|---|
| `<uid>/<method>_<modality>.png` | `batch_render.py` | regular render at `--resolution` (default 720 px) |
| `<uid>/<method>_<modality>_hires.png` | `batch_render.py --hires_factor X` | same view, X× resolution |
| `<uid>/<method>_<modality>_crop.png` | `crop_results.py` | square crop of the corresponding `_hires.png` |
| `<uid>/crop_bbox.json` | `crop_results.py` | reproducible record of the chosen crop |
| `<output>.pptx` | `create_pptx.py` | the comparison deck |
