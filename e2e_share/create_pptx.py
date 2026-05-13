"""Compile e2e_share renders into a PowerPoint deck.

Layout: one *column* per example.  Within each column the rows are:

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

A small extra gap separates one method pair from the next (so each
``full_color`` / ``normal`` pair visually reads as belonging to the same
method).  When ``<key>_crop.png`` exists next to a render it is overlaid as
a corner inset (typically the zoom-in produced by ``crop_results.py``).

Usage::

    conda activate py311
    python e2e_share/create_pptx.py \\
        --data_root  /path/to/e2e_share_2026-05-12/data/per_asset \\
        --render_root /path/to/e2e_share_2026-05-12_renders \\
        --captions    /path/to/e2e_share_2026-05-12/data/captions.csv \\
        --output      /path/to/results.pptx \\
        --assets      12321371... 70693700... 019be0c9...
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_VERTICAL_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


# ---------------------------------------------------------------------------
# Defaults (override layout via the constants below; data via CLI flags)
# ---------------------------------------------------------------------------
# Render columns from top to bottom in this order.  ``v1`` is intentionally
# omitted.
METHODS = ["v4", "org", "hy", "mv"]
MODALITIES = ["full_color", "normal"]
INPUT_KEYS = ["geo_normal", "color", "tex_normal_ws"]

# Manual aliases for cases where prefix matching is ambiguous or the user
# typed something that doesn't even share a long prefix with the real folder.
MANUAL_ALIAS: dict[str, str] = {
    "79693700d33180ba3afa469dabfef74e": "70693700d33180ba3afa469dabfef74e",
    "1a49b0714571487d9164b9ba89f9ca5c": "1a49b0714571487d9164b9ba13d03e3f",
}


# ---------------------------------------------------------------------------
# Layout (inches) -- vertical layout: one column per example.
# ---------------------------------------------------------------------------
LABEL_COL_W = 1.25            # leftmost column with row labels
COL_W = 1.55                  # width of each example column
IMG_H = 1.55                  # height of each image cell (square)
CAPTION_H = 1.05              # height of the caption / uid row at the top
GROUP_GAP = 0.18              # vertical gap between input group and method group
METHOD_GAP = 0             # extra gap between two consecutive method pairs
PAIR_GAP = -0.1                # gap *within* a (full_color, normal) pair (tight)
COL_GAP = 0.05                # horizontal gap between example columns
LEFT_MARGIN = 0.30
RIGHT_MARGIN = 0.30
TOP_MARGIN = 0.25
BOTTOM_MARGIN = 0.25
TITLE_H = 0.50
COLS_PER_SLIDE = 6            # how many examples to fit on each slide

CAPTION_FS = 9
LABEL_FS = 11
HEADER_FS = 12
TITLE_FS = 22

# ----- Inset (zoom-in crop) overlay configuration -----
# When a cropped variant exists (``<key>_crop.png``), it is overlaid on the
# main render in this corner.  Sizes are fractions of the cell.
INSET_FRAC = 0.42                # inset side length as a fraction of the cell
INSET_PAD = 0.02                 # gap from the cell edges, in inches
INSET_CORNER = "bottom_right"    # "bottom_right" | "bottom_left" | "top_right" | "top_left"
INSET_BORDER_PT = 1.5            # thickness of the white border behind the inset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def resolve_asset(name: str, available: list[str]) -> str | None:
    """Map a user-supplied asset name to the actual folder name."""
    if name in MANUAL_ALIAS:
        return MANUAL_ALIAS[name]
    if name in available:
        return name
    matches = [a for a in available if a.startswith(name)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"  [warn] ambiguous prefix {name!r}: {matches}")
        return matches[0]
    return None


def load_captions(csv_path: Path) -> dict[str, str]:
    """Parse ``captions.csv`` into ``{uid: caption}``.

    The CSV uses commas inside quoted captions, so we use the ``csv`` module
    which handles quoting correctly.
    """
    import csv

    out: dict[str, str] = {}
    if not csv_path.exists():
        return out
    with csv_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = (row.get("uid") or "").strip()
            cap = (row.get("caption") or "").strip()
            if uid:
                out[uid] = cap
    return out


def first_sentence(text: str, max_chars: int = 280) -> str:
    if not text:
        return ""
    snippet = text.split(".")[0].strip()
    if not snippet:
        snippet = text.strip()
    if len(snippet) > max_chars:
        snippet = snippet[: max_chars - 1].rstrip() + "…"
    return snippet


def add_image_or_placeholder(
    slide,
    img_path: Path,
    left: float,
    top: float,
    w: float,
    h: float,
    placeholder_label: str,
    inset_path: Path | None = None,
) -> None:
    if img_path.exists():
        slide.shapes.add_picture(
            str(img_path), Inches(left), Inches(top), width=Inches(w), height=Inches(h)
        )
    else:
        tb = slide.shapes.add_textbox(
            Inches(left), Inches(top), Inches(w), Inches(h)
        )
        tf = tb.text_frame
        tf.text = placeholder_label
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.font.size = Pt(9)
        p.font.color.rgb = RGBColor(160, 160, 160)
        p.font.italic = True
        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE

    if inset_path is not None and inset_path.exists():
        _add_inset(slide, inset_path, left, top, w, h)


def _add_inset(
    slide, inset_path: Path, cell_left: float, cell_top: float,
    cell_w: float, cell_h: float,
) -> None:
    """Overlay ``inset_path`` as a small picture in a corner of the cell with
    a thin white border for visual separation."""
    side = INSET_FRAC * min(cell_w, cell_h)
    pad = INSET_PAD

    if INSET_CORNER == "bottom_right":
        ix = cell_left + cell_w - side - pad
        iy = cell_top + cell_h - side - pad
    elif INSET_CORNER == "bottom_left":
        ix = cell_left + pad
        iy = cell_top + cell_h - side - pad
    elif INSET_CORNER == "top_right":
        ix = cell_left + cell_w - side - pad
        iy = cell_top + pad
    else:  # top_left
        ix = cell_left + pad
        iy = cell_top + pad

    # White outline behind the inset (rectangle slightly larger than the
    # picture).  We add the rectangle first so the picture renders on top.
    border_in = INSET_BORDER_PT / 72.0
    rect = slide.shapes.add_shape(
        1,                                  # MSO_SHAPE.RECTANGLE
        Inches(ix - border_in),
        Inches(iy - border_in),
        Inches(side + 2 * border_in),
        Inches(side + 2 * border_in),
    )
    rect.fill.solid()
    rect.fill.fore_color.rgb = RGBColor(255, 255, 255)
    rect.line.color.rgb = RGBColor(255, 255, 255)
    rect.line.width = Pt(0)
    rect.shadow.inherit = False

    slide.shapes.add_picture(
        str(inset_path),
        Inches(ix),
        Inches(iy),
        width=Inches(side),
        height=Inches(side),
    )


def add_label(
    slide,
    text: str,
    left: float,
    top: float,
    w: float,
    h: float,
    *,
    fs: int = LABEL_FS,
    bold: bool = False,
    align=PP_ALIGN.CENTER,
    color: tuple[int, int, int] = (40, 40, 40),
    italic: bool = False,
    anchor=MSO_VERTICAL_ANCHOR.MIDDLE,
    word_wrap: bool = False,
) -> None:
    tb = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(w), Inches(h)
    )
    tf = tb.text_frame
    tf.word_wrap = word_wrap
    tf.vertical_anchor = anchor
    tf.text = text
    p = tf.paragraphs[0]
    p.alignment = align
    p.font.size = Pt(fs)
    p.font.bold = bold
    p.font.italic = italic
    p.font.name = "Palatino"
    p.font.color.rgb = RGBColor(*color)


# Each row is described by a dict so we can express both "single image"
# rows and "two-image side-by-side" rows uniformly.
#
# Keys:
#   kind     -- "input" or "render"
#   label    -- left-side row label
#   cells    -- list of (sublabel, key) tuples; len(1) for full-width, len(2)
#               for side-by-side at half width
#   gap_before -- extra vertical gap added above this row (in inches)
def row_layout() -> list[dict]:
    rows: list[dict] = []

    # geo_normal full row (full height).
    rows.append(
        {
            "kind": "input",
            "label": "geo_normal",
            "cells": [("", "geo_normal")],
            "gap_before": 0.0,
            "height": IMG_H,
        }
    )
    # color + tex_normal_ws side-by-side (half width, half height so each
    # thumbnail keeps a 1:1 aspect ratio).
    rows.append(
        {
            "kind": "input",
            "label": "color | tex_normal_ws",
            "cells": [("", "color"), ("", "tex_normal_ws")],
            "gap_before": 0.0,
            "height": IMG_H / 2.0,
        }
    )

    # Method pairs.  First pair gets the input/method group gap; subsequent
    # pairs get a smaller inter-method gap.  Within a pair (FC -> N) there is
    # no gap so the two reads as one method.
    for mi, m in enumerate(METHODS):
        for mod_idx, mod in enumerate(MODALITIES):
            if mi == 0 and mod_idx == 0:
                gap = GROUP_GAP
            elif mod_idx == 0:
                gap = METHOD_GAP
            else:
                gap = PAIR_GAP
            label = f"{m} · {mod.replace('_', ' ')}"
            rows.append(
                {
                    "kind": "render",
                    "label": label,
                    "cells": [("", f"{m}_{mod}")],
                    "gap_before": gap,
                    "height": IMG_H,
                }
            )
    return rows


def row_y_positions(rows: list[dict]) -> tuple[list[float], float]:
    """Return the Y position of every row plus total content height."""
    y_positions: list[float] = []
    y = TOP_MARGIN + TITLE_H + CAPTION_H
    for r in rows:
        y += r["gap_before"]
        y_positions.append(y)
        y += r["height"]
    total_h = y + BOTTOM_MARGIN
    return y_positions, total_h


# ---------------------------------------------------------------------------
# Build PPTX
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--data_root",
        required=True,
        help="Folder containing per-asset subfolders (the input refs).",
    )
    p.add_argument(
        "--render_root",
        required=True,
        help="Folder containing per-asset render subfolders.",
    )
    p.add_argument(
        "--captions",
        default=None,
        help=(
            "CSV with columns including ``uid`` and ``caption``. "
            "Optional -- if omitted the deck just shows the uid."
        ),
    )
    p.add_argument(
        "--output",
        required=True,
        help="Output .pptx path.",
    )
    p.add_argument(
        "--assets",
        nargs="+",
        required=True,
        help=(
            "Asset UIDs to include, in the order they should appear. "
            "Truncated/typo'd entries are resolved by prefix match."
        ),
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    data_root = Path(args.data_root)
    render_root = Path(args.render_root)
    output_pptx = Path(args.output)
    captions_csv = Path(args.captions) if args.captions else None

    available = sorted([p.name for p in data_root.iterdir() if p.is_dir()])

    print("Resolving target assets...")
    targets: list[str] = []
    for raw in args.assets:
        resolved = resolve_asset(raw, available)
        if resolved is None:
            print(f"  [skip] no folder matches {raw!r}")
            continue
        if resolved != raw:
            print(f"  {raw!r} -> {resolved!r}")
        else:
            print(f"  {raw}")
        targets.append(resolved)
    print(f"\nResolved {len(targets)} / {len(args.assets)} assets")

    captions = load_captions(captions_csv) if captions_csv else {}
    rows = row_layout()
    y_positions, total_h = row_y_positions(rows)

    cols_per_slide = COLS_PER_SLIDE
    total_w = (
        LEFT_MARGIN
        + LABEL_COL_W
        + cols_per_slide * (COL_W + COL_GAP)
        + RIGHT_MARGIN
    )

    prs = Presentation()
    prs.slide_width = Inches(total_w)
    prs.slide_height = Inches(total_h)
    print(f"\nSlide dimensions: {total_w:.2f} x {total_h:.2f} in")

    def col_x(slot: int) -> float:
        """X of example column ``slot`` (0-based)."""
        return LEFT_MARGIN + LABEL_COL_W + slot * (COL_W + COL_GAP)

    n_slides = (len(targets) + cols_per_slide - 1) // cols_per_slide
    for s in range(n_slides):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        chunk = targets[s * cols_per_slide : (s + 1) * cols_per_slide]

        # ----- Title -----
        add_label(
            slide,
            f"e2e_share 2026-05-12 — slide {s + 1} / {n_slides}",
            LEFT_MARGIN,
            TOP_MARGIN,
            total_w - LEFT_MARGIN - RIGHT_MARGIN,
            TITLE_H,
            fs=TITLE_FS,
            bold=True,
            align=PP_ALIGN.LEFT,
            color=(20, 20, 20),
        )

        # ----- Row labels (leftmost column) -----
        # Caption-row label
        add_label(
            slide,
            "Caption",
            LEFT_MARGIN,
            TOP_MARGIN + TITLE_H,
            LABEL_COL_W,
            CAPTION_H,
            fs=HEADER_FS,
            bold=True,
            align=PP_ALIGN.RIGHT,
            color=(80, 80, 110),
        )
        # Image-row labels
        for r, ry in zip(rows, y_positions):
            color = (50, 70, 130) if r["kind"] == "render" else (60, 60, 60)
            add_label(
                slide,
                r["label"],
                LEFT_MARGIN,
                ry,
                LABEL_COL_W,
                r["height"],
                fs=LABEL_FS,
                bold=True,
                align=PP_ALIGN.RIGHT,
                color=color,
            )

        # ----- One column per example -----
        for slot, uid in enumerate(chunk):
            x = col_x(slot)
            asset_dir = data_root / uid
            render_dir = render_root / uid

            # Caption box at the top of the column.
            uid_label = uid if len(uid) <= 28 else uid[:25] + "..."
            cap_text = first_sentence(captions.get(uid, ""), max_chars=240)
            tb = slide.shapes.add_textbox(
                Inches(x),
                Inches(TOP_MARGIN + TITLE_H),
                Inches(COL_W),
                Inches(CAPTION_H),
            )
            tf = tb.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_VERTICAL_ANCHOR.TOP
            tf.text = uid_label
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            p.font.size = Pt(8)
            p.font.bold = True
            p.font.name = "Consolas"
            p.font.color.rgb = RGBColor(80, 80, 80)
            if cap_text:
                p2 = tf.add_paragraph()
                p2.alignment = PP_ALIGN.CENTER
                p2.text = cap_text
                p2.font.size = Pt(CAPTION_FS)
                p2.font.italic = True
                p2.font.name = "Palatino"
                p2.font.color.rgb = RGBColor(40, 40, 40)

            # Image rows -- support 1- or 2-cell rows.
            for r, ry in zip(rows, y_positions):
                cells = r["cells"]
                n = len(cells)
                row_h = r["height"]
                if n == 1:
                    cell_w = COL_W
                else:
                    cell_w = (COL_W - (n - 1) * 0.04) / n
                cell_h = row_h
                for ci, (_sub, key) in enumerate(cells):
                    cx = x + ci * (cell_w + 0.04)
                    inset_path: Path | None = None
                    if r["kind"] == "input":
                        img_path = asset_dir / f"{key}.png"
                    else:
                        img_path = render_dir / f"{key}.png"
                        candidate = render_dir / f"{key}_crop.png"
                        if candidate.exists():
                            inset_path = candidate
                    add_image_or_placeholder(
                        slide,
                        img_path,
                        cx,
                        ry,
                        cell_w,
                        cell_h,
                        placeholder_label=f"missing\n{key}",
                        inset_path=inset_path,
                    )

    output_pptx.parent.mkdir(parents=True, exist_ok=True)
    print(f"\nWriting {output_pptx}")
    prs.save(str(output_pptx))
    size_mb = os.path.getsize(output_pptx) / (1024 * 1024)
    print(f"  -> {size_mb:.1f} MB, {n_slides} slide(s), {len(targets)} column(s)")


if __name__ == "__main__":
    main()
