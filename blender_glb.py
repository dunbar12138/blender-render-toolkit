"""Render a .glb mesh (with embedded materials) to a single PNG.

Supports two modalities:
  - full_color : preserve the embedded materials from the GLB.
  - normal     : replace each material with a camera-space normal renderer
                 that respects each material's existing normal map (if any),
                 falling back to geometry normals otherwise.

Designed to be called via Blender's bundled Python or via a `bpy` pip install.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    # When invoked via `blender --background --python script.py -- <args>` we
    # need to strip everything before the `--` separator.
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = argv[1:]

    parser = argparse.ArgumentParser(description="Render a .glb to a PNG image.")
    parser.add_argument("--glb_path", type=str, required=True, help="Path to input .glb file")
    parser.add_argument(
        "--output_path",
        type=str,
        required=True,
        help="Full path to the output PNG (parent dir will be created).",
    )
    parser.add_argument(
        "--texture_type",
        choices=["full_color", "normal"],
        default="full_color",
        help="Rendering modality.",
    )
    parser.add_argument(
        "--start_rot_x",
        type=float,
        default=0.0,
        help="Initial rotation around the X axis (degrees). Default 0 because "
        "glTF imports are already auto-converted to +Z up.",
    )
    parser.add_argument(
        "--start_rot_z",
        type=float,
        default=0.0,
        help="Initial rotation around the Z axis (degrees).",
    )
    parser.add_argument(
        "--target_size",
        type=float,
        default=2.0,
        help="Target longest-edge size for the imported model after auto-fit.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=128,
        help="Cycles render samples.",
    )
    parser.add_argument(
        "--resolution",
        type=int,
        default=720,
        help="Output square resolution (pixels).",
    )
    parser.add_argument(
        "--keep_ground",
        action="store_true",
        help="Keep the studio scene's ground plane (default: hide it for "
        "transparent shadow-free output).",
    )
    parser.add_argument(
        "--keep_helper_sphere",
        action="store_true",
        help="Keep the studio scene's debug sphere (default: hide it).",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Render-engine setup
# ---------------------------------------------------------------------------
def configure_render(samples: int, resolution: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"

    prefs = bpy.context.preferences.addons["cycles"].preferences
    # Try CUDA first, then METAL (mac), then OPTIX, then OPENCL.
    for backend in ("CUDA", "METAL", "OPTIX", "OPENCL"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            scene.cycles.device = "GPU"
            print(f"[render] Using GPU backend: {backend}")
            break
        except Exception as exc:  # pragma: no cover - depends on host
            print(f"[render] backend {backend} not available: {exc}")
    else:
        scene.cycles.device = "CPU"
        print("[render] Falling back to CPU rendering.")

    scene.cycles.samples = samples
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    # Transparent background so the rendered object can be composited freely.
    scene.render.film_transparent = True


# ---------------------------------------------------------------------------
# Studio scene cleanup
# ---------------------------------------------------------------------------
# Names of helper objects baked into ``load/studio_bg_static.blend``.  We
# selectively hide them so the imported GLB renders against a transparent
# background with no spurious geometry / shadows.
STUDIO_GROUND_NAMES = {"Plane"}
STUDIO_HELPER_NAMES = {"Sphere"}


def _hide_object(obj: bpy.types.Object) -> None:
    obj.hide_render = True
    obj.hide_viewport = True


def cleanup_studio_scene(keep_ground: bool, keep_helper_sphere: bool) -> None:
    for obj in list(bpy.data.objects):
        if not keep_ground and obj.name in STUDIO_GROUND_NAMES:
            _hide_object(obj)
            print(f"[studio] hid ground plane: {obj.name}")
        if not keep_helper_sphere and obj.name in STUDIO_HELPER_NAMES:
            _hide_object(obj)
            print(f"[studio] hid helper sphere: {obj.name}")


# ---------------------------------------------------------------------------
# GLB import + auto-fit
# ---------------------------------------------------------------------------
def import_glb(glb_path: str) -> list[bpy.types.Object]:
    pre = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    new_objs = [o for o in bpy.data.objects if o not in pre]
    print(f"[import] imported {len(new_objs)} object(s) from {glb_path}")
    return new_objs


def world_bbox(objs: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    minv = Vector((float("inf"),) * 3)
    maxv = Vector((float("-inf"),) * 3)
    for obj in objs:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            world = obj.matrix_world @ Vector(corner)
            for i in range(3):
                minv[i] = min(minv[i], world[i])
                maxv[i] = max(maxv[i], world[i])
    return minv, maxv


def fit_objects(
    objs: list[bpy.types.Object],
    target_size: float,
    rot_x_deg: float,
    rot_z_deg: float,
) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    """Center the imported objects at the origin and uniformly scale the longest
    bounding-box edge to ``target_size``.  After this, the bounding-box centre
    stays at the world origin under *any* parent rotation, so we can freely
    apply ``rot_x`` / ``rot_z`` afterwards.

    Steps:
      1. Bake every imported mesh's hierarchy transform into its mesh data
         (mirrors what ``blendertoolbox.readGLB`` does).  After this each mesh
         has identity location/rotation/scale.
      2. Compute the world bounding box of the baked meshes.
      3. Translate every mesh by ``-center`` so the bbox centre is at origin.
      4. Parent meshes to a fresh empty and apply scale + rotation to the
         empty.  Because the centre is at origin, rotation does not introduce
         translation drift.
      5. Remove the imported helper empties (now redundant).
    """
    bpy.ops.object.select_all(action="DESELECT")

    meshes = [o for o in objs if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("fit_objects: no MESH objects to fit")

    # 1. Bake hierarchy transforms onto the mesh data so each mesh becomes
    #    a self-contained piece with identity object transform.
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.select_all(action="DESELECT")

    # 2. Compute world bbox after baking.
    minv, maxv = world_bbox(meshes)
    extent = maxv - minv
    longest = max(extent.x, extent.y, extent.z)
    scale = target_size / longest if longest > 0 else 1.0
    center = (minv + maxv) * 0.5

    # 3. Centre each mesh at origin in its local (== world) space.
    for m in meshes:
        m.location = m.location - center

    # 4. Parent meshes to a single empty and apply scale / rotation.
    empty = bpy.data.objects.new("ImportRoot", None)
    bpy.context.collection.objects.link(empty)
    for m in meshes:
        m.parent = empty
    empty.scale = (scale, scale, scale)
    empty.rotation_euler = (
        math.radians(rot_x_deg),
        0.0,
        math.radians(rot_z_deg),
    )

    # 5. Drop leftover empties from the import (their transforms are baked in).
    #    Skip our own ImportRoot so we don't lose the parent we just made.
    for o in list(objs):
        if (
            o.type == "EMPTY"
            and o is not empty
            and o.name in bpy.data.objects
        ):
            try:
                bpy.data.objects.remove(o, do_unlink=True)
            except Exception:
                pass

    return empty, meshes


# ---------------------------------------------------------------------------
# Material conversion for normal rendering
# ---------------------------------------------------------------------------
def convert_material_to_normal_render(mat: bpy.types.Material) -> None:
    """Replace ``mat``'s node tree with a camera-space normal visualizer.

    If the original material had a normal map (TEX_IMAGE -> NORMAL_MAP), we
    reuse that image so that surface micro-detail is preserved.  Otherwise we
    fall back to the geometry normal of the mesh.
    """
    nt = mat.node_tree
    if nt is None:
        mat.use_nodes = True
        nt = mat.node_tree

    # Inspect the existing tree first to capture any normal map.
    normal_image = None
    normal_uv_name: str | None = None
    for node in nt.nodes:
        if node.type == "NORMAL_MAP":
            color_input = node.inputs.get("Color")
            if color_input and color_input.is_linked:
                src = color_input.links[0].from_node
                if src.type == "TEX_IMAGE" and src.image is not None:
                    normal_image = src.image
                    vec_in = src.inputs.get("Vector")
                    if vec_in and vec_in.is_linked:
                        v_src = vec_in.links[0].from_node
                        if v_src.type == "UVMAP":
                            normal_uv_name = v_src.uv_map
            uv_attr = getattr(node, "uv_map", "")
            if uv_attr and not normal_uv_name:
                normal_uv_name = uv_attr
            break

    # Wipe and rebuild.
    for node in list(nt.nodes):
        nt.nodes.remove(node)

    output = nt.nodes.new("ShaderNodeOutputMaterial")
    emission = nt.nodes.new("ShaderNodeEmission")
    gamma = nt.nodes.new("ShaderNodeGamma")
    gamma.inputs["Gamma"].default_value = 2.2
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.vector_type = "TEXTURE"
    mapping.inputs["Location"].default_value = (-1.0, -1.0, 1.0)
    mapping.inputs["Scale"].default_value = (2.0, 2.0, -2.0)
    vec_xform = nt.nodes.new("ShaderNodeVectorTransform")
    vec_xform.convert_from = "WORLD"
    vec_xform.convert_to = "CAMERA"
    vec_xform.vector_type = "NORMAL"

    normal_map_node = nt.nodes.new("ShaderNodeNormalMap")
    normal_map_node.space = "TANGENT"

    if normal_image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = normal_image
        # Important: tangent-space normal maps must be Non-Color.
        try:
            tex.image.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
        tex.extension = "REPEAT"
        tex.interpolation = "Linear"

        if normal_uv_name:
            uvm = nt.nodes.new("ShaderNodeUVMap")
            uvm.uv_map = normal_uv_name
            nt.links.new(uvm.outputs["UV"], tex.inputs["Vector"])

        nt.links.new(tex.outputs["Color"], normal_map_node.inputs["Color"])
        normal_map_node.inputs["Strength"].default_value = 1.0
    else:
        # Fall back to geometry normal: feed Geometry.Normal into the chain
        # directly (skip the normal-map node).
        normal_map_node.inputs["Strength"].default_value = 0.0

    nt.links.new(normal_map_node.outputs["Normal"], vec_xform.inputs["Vector"])
    nt.links.new(vec_xform.outputs["Vector"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], gamma.inputs["Color"])
    nt.links.new(gamma.outputs["Color"], emission.inputs["Color"])
    nt.links.new(emission.outputs["Emission"], output.inputs["Surface"])

    # Layout for human inspection.
    output.location = (700, 0)
    emission.location = (500, 0)
    gamma.location = (300, 0)
    mapping.location = (100, 0)
    vec_xform.location = (-100, 0)
    normal_map_node.location = (-300, 0)


def apply_normal_render(objs: list[bpy.types.Object]) -> None:
    visited: set[str] = set()
    for obj in objs:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None:
                # Create a fresh material so we get geometry normals.
                mat = bpy.data.materials.new(name=f"NormalMat_{obj.name}")
                mat.use_nodes = True
                slot.material = mat
            if mat.name in visited:
                continue
            visited.add(mat.name)
            convert_material_to_normal_render(mat)


def disable_shadows(objs: list[bpy.types.Object]) -> None:
    for obj in objs:
        if obj.type == "MESH":
            obj.visible_shadow = False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    args = parse_args()

    studio_blend = Path(__file__).parent / "load" / "studio_bg_static.blend"
    if not studio_blend.exists():
        raise FileNotFoundError(f"Missing studio blend: {studio_blend}")

    bpy.ops.wm.open_mainfile(filepath=str(studio_blend))
    configure_render(args.samples, args.resolution)
    cleanup_studio_scene(args.keep_ground, args.keep_helper_sphere)

    objs = import_glb(args.glb_path)
    if not objs:
        raise RuntimeError(f"No objects imported from {args.glb_path}")

    # Always disable shadow casting on the imported model.  With the studio
    # ground plane hidden and a transparent film there is nothing for shadows
    # to land on anyway, but disabling them avoids any spurious darkening of
    # the model's own surfaces from secondary bounces.
    disable_shadows(objs)

    _, meshes = fit_objects(
        objs, args.target_size, args.start_rot_x, args.start_rot_z
    )

    if args.texture_type == "normal":
        apply_normal_render(meshes)
    # full_color: preserve embedded GLB materials.

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(out_path)
    bpy.context.scene.frame_set(0)
    bpy.ops.render.render(write_still=True)
    print(f"[done] wrote {out_path}")


if __name__ == "__main__":
    main()
