import bpy
import math
import sys, os
import argparse
from blender_material import (
    Full_color_texture,
    normal_render_texture,
    albedo_render_texture,
)
import pdb


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render an object with full color texture"
    )
    parser.add_argument("--data_path", type=str, help="Path to the object data")
    parser.add_argument("--obj_name", type=str, help="Name of the object")
    parser.add_argument(
        "--texture_type",
        choices=["full_color", "normal", "albedo"],
        default="full_color",
        help="Type of texture to render",
    )
    parser.add_argument(
        "--output_path",
        type=str,
        default="output",
        help="Path to save the rendered image",
    )
    parser.add_argument(
        "--start_rot_x", type=float, default=90, help="Start rotation in x-axis"
    )
    parser.add_argument(
        "--start_rot_z", type=float, default=0, help="Start rotation in z-axis"
    )
    parser.add_argument(
        "--rotate_video", action="store_true", help="Rotate the object in the video"
    )
    parser.add_argument(
        "--rotate_video_frames", type=int, default=250, help="Number of frames for the video rotation"
    )
    parser.add_argument(
        "--albedo_map", type=str, default="", help="Path to the albedo map"
    )
    parser.add_argument(
        "--normal_map", type=str, default="", help="Path to the normal map"
    )
    parser.add_argument(
        "--postfix",
        type=str,
        default="",
        help="customizable postfix for the output file",
    )
    parser.add_argument("--disable_shadow", action="store_true", help="Disable shadow")
    parser.add_argument("--scale", type=float, default=2.0, help="Scale the object")
    return parser.parse_args()


def main():
    args = parse_args()

    # Set the render engine to Cycles
    bpy.context.scene.render.engine = "CYCLES"

    # Set the device to GPU
    bpy.context.preferences.addons["cycles"].preferences.get_devices()
    bpy.context.preferences.addons["cycles"].preferences.compute_device_type = "CUDA"

    # Open the .blend
    bpy.ops.wm.open_mainfile(filepath="load/studio_bg_static.blend")

    # Load the obj
    data_path = args.data_path
    if args.obj_name:
        obj_name = args.obj_name
    else:
        obj_name = os.path.basename(data_path.rstrip("/"))

    print(data_path, obj_name)

    bpy.ops.wm.obj_import(filepath=os.path.join(data_path, f"{obj_name}.obj"))

    MAX_NAME_LENGTH = 63  # Maximum length of object name in Blender
    obj_name = obj_name[:MAX_NAME_LENGTH]
    obj = bpy.data.objects[obj_name]

    if args.disable_shadow:  # Disable shadow, usually for normal rendering
        obj.visible_shadow = False

    # Scale the object
    s = args.scale

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.transform.resize(value=(s, s, s))

    if args.normal_map != "":
        if args.normal_map == "None":
            print("Normal map set to None. Render the geometry normal instead.")
            normal_map_name = None  # render geometry normal without tactile normal map
        else:
            normal_map_name = os.path.join(data_path, args.normal_map)
    else:
        # by default, load the tacitle normal map
        normal_map_name = os.path.join(data_path, f"{obj_name}_tactile_normal.png")
        # check if the normal map exists. if not, set it to None
        if not os.path.exists(normal_map_name):
            print(
                f"Normal map {normal_map_name} does not exist. Set to None and render the geometry normal instead."
            )
            normal_map_name = None

    if args.albedo_map != "":
        albedo_map_name = os.path.join(data_path, args.albedo_map)
    else:
        albedo_map_name = os.path.join(data_path, f"{obj_name}_albedo.png")

    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = args.rotate_video_frames
    bpy.context.scene.frame_step = 1
    bpy.context.scene.render.fps = 30

    # Insert keyframes to rotate the cube
    start_rotation = (math.radians(args.start_rot_x), 0, math.radians(args.start_rot_z))
    obj.rotation_euler = start_rotation
    obj.keyframe_insert(data_path="rotation_euler", frame=1)

    end_rotation = (
        start_rotation[0],
        start_rotation[1],
        start_rotation[2] + 2 * math.pi,
    )
    obj.rotation_euler = end_rotation
    obj.keyframe_insert(data_path="rotation_euler", frame=args.rotate_video_frames)

    # Reset the object's rotation to the start position for consistent rendering
    obj.rotation_euler = start_rotation

    # Set interpolation to linear for constant speed rotation
    for fcurve in obj.animation_data.action.fcurves:
        for kf in fcurve.keyframe_points:
            kf.interpolation = "LINEAR"

    if args.texture_type == "normal":
        normal_mat = bpy.data.materials.new(name="NormalMat")
        normal_mat.use_nodes = True
        normal_render_texture(normal_mat, normal_map_name)
        obj.material_slots[0].material = normal_mat
    elif args.texture_type == "full_color":
        full_color_mat = bpy.data.materials.new(name="FullColorMat")
        full_color_mat.use_nodes = True
        Full_color_texture(full_color_mat, albedo_map_name, normal_map_name)
        obj.material_slots[0].material = full_color_mat
    elif args.texture_type == "albedo":
        albedo_mat = bpy.data.materials.new(name="AlbedoMat")
        albedo_mat.use_nodes = True
        albedo_render_texture(albedo_mat, albedo_map_name)
        obj.material_slots[0].material = albedo_mat

    os.makedirs(f"config/", exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=f"config/{obj_name}_{args.texture_type}.blend")

    if not args.rotate_video:
        # Render the first frame
        bpy.context.scene.frame_set(0)

        bpy.context.scene.render.image_settings.file_format = "PNG"
        bpy.context.scene.render.filepath = os.path.join(
            args.output_path, f"{obj_name}_{args.texture_type}{args.postfix}.png"
        )
        os.makedirs(f"{args.output_path}", exist_ok=True)
        bpy.ops.render.render(write_still=True)
    else:
        # Render the animation
        bpy.context.scene.render.image_settings.file_format = "PNG"
        bpy.context.scene.render.filepath = os.path.join(
            args.output_path, f"{obj_name}_{args.texture_type}{args.postfix}_rotate/"
        )

        os.makedirs(
            os.path.join(
                args.output_path,
                f"{obj_name}_{args.texture_type}{args.postfix}_rotate/",
            ),
            exist_ok=True,
        )
        bpy.ops.render.render(animation=True)

        # Use ffmpeg to convert the images to a video
        # os.system(f'ffmpeg -y -i {args.output_path}/{obj_name}_{args.texture_type}_rotate/%4d.png -c:v libx264 -r 30 -pix_fmt yuv420p {args.output_path}/{obj_name}_{args.texture_type}_rotate.mp4')


if __name__ == "__main__":
    main()
