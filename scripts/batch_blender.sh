#!/bin/bash

# Full-color rendering

# echo current directory
echo "current directory: $(pwd)" # NOTE: run this script in directory "blender-render-toolkit"

# Define the lists of textures and indices

# ### Mesh objects used in blender-render-toolkit "main" branch ###
# mesh_objs=("avocado") # NOTE: change --data_path from "../logs/$obj" to "examples/$obj"

### Mesh objects used in TactileDreamFusion project ###
mesh_objs=("an_avocado_2_avocado_example")

# Define the number of GPUs available
num_gpus=4

# Function to run Python scripts in parallel
run_scripts() {
    local gpu_id=$1
    local obj=$2

    echo "Running script: $obj on GPU: $gpu_id"
    mkdir output
    mkdir output/${obj}_full_color_rotate

    # NOTE: remove "--start_rot_x 75" or set to other apporiate angles for different mesh objects
  
    CUDA_VISIBLE_DEVICES=$gpu_id python blender_obj_uv_normal.py --data_path ../logs/$obj --start_rot_x 75 --rotate_video > output/${obj}_full_color_rotate/rotate_video.log

    ffmpeg -y -i  output/${obj}_full_color_rotate/%4d.png -c:v libx264 -r 30 -pix_fmt yuv420p output/${obj}_full_color_rotate.mp4

}

for ((i=0; i<${#mesh_objs[@]}; i+=num_gpus)); do
    for ((j=0; j<num_gpus && i+j<${#mesh_objs[@]}; j++)); do
        run_scripts $j "${mesh_objs[$((i+j))]}" &
    done
    wait
done
