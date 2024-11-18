#!/bin/bash

# echo current directory
echo "current directory: $(pwd)" # NOTE: run this script in directory "blender-render-toolkit"

# Define the lists of textures and indices
### Mesh objects used in TactileDreamFusion project ###
### change --data_path from "examples/$obj" to "../logs/$obj" for the following objects if blender-render-toolkit is placed under TactileDreamFusion project ###

mesh_objs=("a_cactus_in_a_pot_3_Orange_OrangeGlove_ours_TSDS" "a_gold_goat_sculpture_GoldGoat_TableTennisHandle_ours_TSDS" "lamp1_ClothBag_MetalFrame_ours_TSDS")

# Define the number of GPUs available
num_gpus=4

# Function to run Python scripts in parallel
run_scripts() {
    local gpu_id=$1
    local obj=$2

    echo "Running script: $obj on GPU: $gpu_id"
    mkdir output
    mkdir output/${obj}_label_rotate

    CUDA_VISIBLE_DEVICES=$gpu_id python blender_obj_uv_normal.py --data_path ../logs/$obj --rotate_video --texture_type label > output/${obj}_label_rotate/rotate_video.log

    ffmpeg -y -i  output/${obj}_label_rotate/%4d.png -c:v libx264 -r 30 -pix_fmt yuv420p output/${obj}_label_rotate.mp4

}

for ((i=0; i<${#mesh_objs[@]}; i+=num_gpus)); do
    for ((j=0; j<num_gpus && i+j<${#mesh_objs[@]}; j++)); do
        run_scripts $j "${mesh_objs[$((i+j))]}" &
    done
    wait
done
