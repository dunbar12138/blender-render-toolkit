"""Pick a crop region on one reference render and apply it to every matching
render of the same asset.

Why this exists: every ``*_hires.png`` for a given asset is rendered with the
same camera and the same model scale, so an axis-aligned crop region selected
on one of them maps 1:1 to the others.  This script gives you (a) an
interactive matplotlib picker, (b) a JSON record of the crop you chose, and
(c) cropped PNGs for every method/modality of the asset.

Common usage (you must point ``--render_root`` at the folder that holds the
per-asset render subfolders, e.g. ``e2e_share_2026-05-12_renders``)::

    # Interactive picker, defaults to v4_full_color_hires.png as reference
    conda activate py311
    python e2e_share/crop_results.py \\
        --render_root /path/to/e2e_share_2026-05-12_renders \\
        12321371e98d41b4afe98796a529cf17

    # Reuse the saved crop later (or apply a manual bbox)
    python e2e_share/crop_results.py \\
        --render_root /path/to/e2e_share_2026-05-12_renders \\
        12321371e98d41b4afe98796a529cf17 \\
        --bbox 540 320 1320 1500       # x y w h, in source-image pixels

    # Crop several assets at once (still interactive per asset)
    python e2e_share/crop_results.py \\
        --render_root /path/to/e2e_share_2026-05-12_renders \\
        12321371... 70693700... 019be0c9...

The crop box is stored at ``<render_root>/<uid>/crop_bbox.json`` and the
cropped PNGs land next to the originals as ``<method>_<modality>_crop.png``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image


DEFAULT_REF_NAME = "v4_full_color_hires.png"
SOURCE_SUFFIX = "_hires.png"   # which renders get cropped
OUTPUT_SUFFIX = "_crop.png"    # what the cropped PNGs are saved as
BBOX_JSON = "crop_bbox.json"


# ---------------------------------------------------------------------------
# Bbox normalisation helpers
# ---------------------------------------------------------------------------
def _clamp_int(v: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(v))))


def make_square_bbox(
    x: float, y: float, w: float, h: float, img_w: int, img_h: int
) -> tuple[int, int, int, int]:
    """Return an integer ``(left, top, right, bottom)`` square bbox.

    The square is constructed by taking ``side = max(w, h)`` and centring it
    on the user's box.  It is then shifted (not shrunk) so it stays inside
    the image bounds.  If the requested side is larger than either image
    dimension, the side is reduced to the smaller dimension.
    """
    side = max(abs(w), abs(h))
    side = min(side, img_w, img_h)
    if side < 1:
        raise ValueError(
            f"degenerate bbox: w={w} h={h} (image {img_w}x{img_h})"
        )

    cx = x + w / 2.0
    cy = y + h / 2.0

    half = side / 2.0
    left = cx - half
    top = cy - half
    if left < 0:
        left = 0
    if top < 0:
        top = 0
    if left + side > img_w:
        left = img_w - side
    if top + side > img_h:
        top = img_h - side

    side_i = _clamp_int(side, 1, min(img_w, img_h))
    left_i = _clamp_int(left, 0, img_w - side_i)
    top_i = _clamp_int(top, 0, img_h - side_i)
    return left_i, top_i, left_i + side_i, top_i + side_i


# ---------------------------------------------------------------------------
# Interactive picker
# ---------------------------------------------------------------------------
def pick_bbox_interactive(ref_path: Path) -> tuple[int, int, int, int]:
    """Open ``ref_path`` in a matplotlib window, let the user draw a box, and
    return the chosen bbox in *source-image* pixel coordinates."""
    import matplotlib.pyplot as plt
    from matplotlib.widgets import RectangleSelector

    img = Image.open(ref_path)
    img_w, img_h = img.size

    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots(figsize=(9, 9))
    ax.imshow(img)
    ax.set_title(
        f"{ref_path.name}  ({img_w}x{img_h})\n"
        "Click + drag a box.  Final crop is auto-squared (max of w, h).  "
        "[Enter] / close to confirm.  [r] to reset."
    )
    ax.set_xlim(0, img_w)
    ax.set_ylim(img_h, 0)

    # Outline preview that shows the squared crop after each drag.
    preview = Rectangle(
        (0, 0), 0, 0,
        fill=False, edgecolor="lime", linewidth=2.0, linestyle="--",
        visible=False,
    )
    ax.add_patch(preview)

    state: dict = {"bbox": None}

    def on_select(eclick, erelease) -> None:
        x0, x1 = sorted([eclick.xdata, erelease.xdata])
        y0, y1 = sorted([eclick.ydata, erelease.ydata])
        bb = make_square_bbox(
            x0, y0, x1 - x0, y1 - y0, img_w, img_h
        )
        state["bbox"] = bb
        l, t, r, b = bb
        side = r - l
        preview.set_bounds(l, t, side, side)
        preview.set_visible(True)
        ax.set_title(
            f"{ref_path.name}  ({img_w}x{img_h})\n"
            f"square crop: x={l}  y={t}  side={side}   "
            f"({side / img_w:.0%} of width)\n"
            "[Enter] / close to confirm.  [r] to reset."
        )
        fig.canvas.draw_idle()

    def on_key(event) -> None:
        if event.key == "enter":
            plt.close(fig)
        elif event.key == "r":
            state["bbox"] = None
            preview.set_visible(False)
            ax.set_title(
                f"{ref_path.name}  ({img_w}x{img_h})\nReset.  "
                "Draw a new crop box."
            )
            fig.canvas.draw_idle()

    selector = RectangleSelector(
        ax,
        on_select,
        useblit=True,
        button=[1],
        minspanx=5,
        minspany=5,
        spancoords="pixels",
        interactive=True,
    )
    fig.canvas.mpl_connect("key_press_event", on_key)
    plt.tight_layout()
    plt.show()
    # Keep the selector reference alive long enough for the user to draw.
    _ = selector

    if state["bbox"] is None:
        raise SystemExit("[crop] no bbox was selected; aborting.")
    return state["bbox"]


# ---------------------------------------------------------------------------
# Apply crop to every matching render
# ---------------------------------------------------------------------------
def crop_asset(
    asset_dir: Path,
    bbox: tuple[int, int, int, int],
    ref_size: tuple[int, int],
    *,
    source_suffix: str,
    output_suffix: str,
) -> int:
    sources = sorted(asset_dir.glob(f"*{source_suffix}"))
    if not sources:
        print(f"  [warn] no '*{source_suffix}' files in {asset_dir}")
        return 0
    n = 0
    for src in sources:
        with Image.open(src) as im:
            if im.size != ref_size:
                print(
                    f"  [warn] {src.name} is {im.size}, expected {ref_size}; "
                    "skipping (resolution mismatch)."
                )
                continue
            cropped = im.crop(bbox)
            out_path = src.with_name(
                src.name.removesuffix(source_suffix) + output_suffix
            )
            cropped.save(out_path)
            n += 1
            print(f"  cropped {src.name} -> {out_path.name}")
    return n


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "assets",
        nargs="+",
        help="Asset UIDs (folder names under --render_root).",
    )
    p.add_argument(
        "--render_root",
        type=str,
        required=True,
        help=(
            "Folder containing per-asset render subfolders "
            "(usually ``e2e_share_2026-05-12_renders``)."
        ),
    )
    p.add_argument(
        "--bbox",
        nargs=4,
        type=int,
        metavar=("X", "Y", "W", "H"),
        default=None,
        help=(
            "Manual bbox in source-image pixel coordinates.  Skips the "
            "interactive picker; applied to every asset.  Non-square "
            "input is auto-expanded to side=max(W,H) and re-centred."
        ),
    )
    p.add_argument(
        "--ref",
        default=DEFAULT_REF_NAME,
        help=(
            "Reference image filename (relative to each asset folder) used to "
            f"pick the bbox. Default: {DEFAULT_REF_NAME}"
        ),
    )
    p.add_argument(
        "--source_suffix",
        default=SOURCE_SUFFIX,
        help=f"Suffix for files to crop. Default: {SOURCE_SUFFIX}",
    )
    p.add_argument(
        "--output_suffix",
        default=OUTPUT_SUFFIX,
        help=f"Suffix for cropped outputs. Default: {OUTPUT_SUFFIX}",
    )
    p.add_argument(
        "--reuse_saved_bbox",
        action="store_true",
        help=(
            "Use the bbox stored in crop_bbox.json (if present) instead of "
            "showing the picker.  Falls back to the picker if no JSON exists."
        ),
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    render_root = Path(args.render_root)

    for uid in args.assets:
        print(f"\n=== {uid} ===")
        asset_dir = render_root / uid
        if not asset_dir.is_dir():
            print(f"  [skip] folder not found: {asset_dir}")
            continue

        ref_path = asset_dir / args.ref
        if not ref_path.exists():
            # Fall back to the first available _hires render
            candidates = sorted(asset_dir.glob(f"*{args.source_suffix}"))
            if not candidates:
                print(f"  [skip] no reference image and no source files")
                continue
            ref_path = candidates[0]
            print(f"  [info] using {ref_path.name} as reference")

        with Image.open(ref_path) as im:
            ref_size = im.size

        bbox: tuple[int, int, int, int] | None = None

        if args.bbox is not None:
            x, y, w, h = args.bbox
            bbox = make_square_bbox(x, y, w, h, *ref_size)
            if w != h:
                print(
                    f"  [info] --bbox was non-square ({w}x{h}); squared to "
                    f"side={bbox[2] - bbox[0]} centred on the input region"
                )
            print(f"  using bbox (ltrb): {bbox}")
        elif args.reuse_saved_bbox:
            json_path = asset_dir / BBOX_JSON
            if json_path.exists():
                data = json.loads(json_path.read_text())
                bbox = tuple(data["bbox_ltrb"])
                print(f"  reusing saved bbox: {bbox}")
            else:
                print(f"  [info] no saved bbox at {json_path}, opening picker")
                bbox = pick_bbox_interactive(ref_path)
        else:
            bbox = pick_bbox_interactive(ref_path)

        # Save bbox metadata for reproducibility / pptx integration.
        meta = {
            "bbox_ltrb": list(bbox),
            "bbox_xywh": [
                bbox[0],
                bbox[1],
                bbox[2] - bbox[0],
                bbox[3] - bbox[1],
            ],
            "ref": ref_path.name,
            "ref_size": list(ref_size),
        }
        (asset_dir / BBOX_JSON).write_text(json.dumps(meta, indent=2))
        print(f"  saved bbox metadata -> {asset_dir / BBOX_JSON}")

        n = crop_asset(
            asset_dir,
            bbox,
            ref_size,
            source_suffix=args.source_suffix,
            output_suffix=args.output_suffix,
        )
        print(f"  produced {n} cropped image(s)")


if __name__ == "__main__":
    sys.exit(main())
