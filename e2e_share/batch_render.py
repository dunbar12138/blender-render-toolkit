"""Batch render every (asset x method x modality) combination in a single
``bpy`` process.  Doing this in one process is roughly 30x faster than calling
``blender_glb.py`` per-render because the studio background's lighting
importance map only has to be computed once.

Output layout (default):

    <output_root>/<asset_uid>/<method>_<modality>.png

E.g. ``e2e_share_2026-05-12_renders/1a769a9b3c084dd680da406ff2eabd40/hy_normal.png``.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

import bpy

# Allow importing blender_glb.py from the toolkit root (one level up).
_TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOLKIT_ROOT))
from blender_glb import (  # noqa: E402
    apply_normal_render,
    cleanup_studio_scene,
    configure_render,
    disable_shadows,
    fit_objects,
    import_glb,
)


METHOD_GLBS = ["org", "hy", "mv", "v1", "v4"]
MODALITIES = ["full_color", "normal"]


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]

    parser = argparse.ArgumentParser(description="Batch render e2e_share GLBs.")
    parser.add_argument(
        "--per_asset_dir",
        type=str,
        required=True,
        help=(
            "Folder containing per-asset subfolders, each holding the GLBs "
            "(<method>.glb) for one asset."
        ),
    )
    parser.add_argument(
        "--output_root",
        type=str,
        required=True,
        help=(
            "Folder to write renders into. One subfolder per asset will be "
            "created."
        ),
    )
    parser.add_argument(
        "--assets",
        type=str,
        nargs="*",
        default=None,
        help="Optional list of asset UIDs to render (defaults to all).",
    )
    parser.add_argument(
        "--max_assets",
        type=int,
        default=None,
        help="Render at most this many assets (handy for smoke tests).",
    )
    parser.add_argument(
        "--methods",
        type=str,
        nargs="*",
        default=METHOD_GLBS,
        help=f"Methods (glb stem names) to render. Default: {METHOD_GLBS}",
    )
    parser.add_argument(
        "--modalities",
        type=str,
        nargs="*",
        default=MODALITIES,
        choices=MODALITIES,
        help="Modalities to render.",
    )
    parser.add_argument("--start_rot_x", type=float, default=0.0)
    parser.add_argument("--start_rot_z", type=float, default=0.0)
    parser.add_argument("--target_size", type=float, default=2.0)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--resolution", type=int, default=720)
    parser.add_argument("--keep_ground", action="store_true")
    parser.add_argument("--keep_helper_sphere", action="store_true")
    parser.add_argument(
        "--hires_factor",
        type=float,
        default=0.0,
        help=(
            "If > 0, also render a high-resolution version of the same view "
            "(camera and model scale unchanged) at "
            "``resolution * hires_factor`` pixels. Output filename gets a "
            "'_hires' suffix. Useful for downstream cropping / zoom-ins."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-render even if the output PNG already exists.",
    )
    return parser.parse_args(argv)


def open_studio_bg() -> None:
    studio_blend = Path(__file__).resolve().parent / "load" / "studio_bg_static.blend"
    bpy.ops.wm.open_mainfile(filepath=str(studio_blend))


def clear_imported_objects(known_objs: set[str]) -> None:
    """Remove every object NOT present in ``known_objs`` (the baseline scene).

    Also purge orphan datablocks afterwards so memory does not blow up.
    """
    to_remove = [o for o in bpy.data.objects if o.name not in known_objs]
    for o in to_remove:
        bpy.data.objects.remove(o, do_unlink=True)
    # Purge orphan meshes / materials / images so memory does not grow forever.
    for _ in range(3):
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_recursive=True)


def render_one(
    glb_path: Path,
    out_path: Path,
    modality: str,
    args: argparse.Namespace,
    baseline_objs: set[str],
    target_size: float,
    resolution: int,
) -> None:
    clear_imported_objects(baseline_objs)

    objs = import_glb(str(glb_path))
    if not objs:
        raise RuntimeError(f"No objects imported from {glb_path}")

    disable_shadows(objs)

    _, meshes = fit_objects(
        objs, target_size, args.start_rot_x, args.start_rot_z
    )

    if modality == "normal":
        apply_normal_render(meshes)

    bpy.context.scene.render.resolution_x = resolution
    bpy.context.scene.render.resolution_y = resolution
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(out_path)
    bpy.context.scene.frame_set(0)
    bpy.ops.render.render(write_still=True)


def discover_assets(per_asset_dir: Path) -> list[str]:
    return sorted([p.name for p in per_asset_dir.iterdir() if p.is_dir()])


def main() -> None:
    args = parse_args()

    per_asset_dir = Path(args.per_asset_dir)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    if args.assets:
        assets = args.assets
    else:
        assets = discover_assets(per_asset_dir)
    if args.max_assets is not None:
        assets = assets[: args.max_assets]

    open_studio_bg()
    configure_render(args.samples, args.resolution)
    cleanup_studio_scene(args.keep_ground, args.keep_helper_sphere)
    baseline_objs = {o.name for o in bpy.data.objects}
    print(f"[batch] baseline objects: {len(baseline_objs)}")

    total = 0
    skipped = 0
    failed: list[tuple[str, str, str, str]] = []
    t0 = time.time()
    for asset in assets:
        asset_dir = per_asset_dir / asset
        for method in args.methods:
            glb_path = asset_dir / f"{method}.glb"
            if not glb_path.exists():
                print(f"[batch] missing: {glb_path}")
                continue
            for modality in args.modalities:
                # Build the list of (suffix, target_size, resolution) variants
                # to render.  Same view (= same target_size) for both, only
                # the pixel resolution changes.
                variants: list[tuple[str, float, int]] = [
                    ("", args.target_size, args.resolution),
                ]
                if args.hires_factor and args.hires_factor > 0:
                    variants.append(
                        (
                            "_hires",
                            args.target_size,
                            int(round(args.resolution * args.hires_factor)),
                        )
                    )

                for suffix, ts, res in variants:
                    out_path = (
                        output_root
                        / asset
                        / f"{method}_{modality}{suffix}.png"
                    )
                    if out_path.exists() and not args.overwrite:
                        skipped += 1
                        continue
                    t = time.time()
                    try:
                        render_one(
                            glb_path,
                            out_path,
                            modality,
                            args,
                            baseline_objs,
                            target_size=ts,
                            resolution=res,
                        )
                        total += 1
                        print(
                            f"[batch] {asset}/{method}_{modality}{suffix} "
                            f"({res}px) -> {out_path}  ({time.time() - t:.1f}s)"
                        )
                    except Exception as exc:
                        print(
                            f"[batch] FAILED {asset}/{method}_{modality}{suffix}: "
                            f"{exc}"
                        )
                        traceback.print_exc()
                        failed.append(
                            (asset, method, modality + suffix, str(exc))
                        )

    elapsed = time.time() - t0
    print(
        f"[batch] done. rendered={total} skipped={skipped} failed={len(failed)}"
        f"  elapsed={elapsed:.1f}s"
    )
    if failed:
        for f in failed:
            print(f"  FAIL {f}")


if __name__ == "__main__":
    main()
