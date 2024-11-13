#!/bin/bash

# Define the lists of textures and indices
mesh_objs=("an_avocado_2_mesh")

# ("a_beanie_1_GreenSweater_ours_TSDS" "a_toy_flower_2_GreenSweater_ours_TSDS" "a_miffy_bunny_GreenSweater_ours_TSDS" "an_avocado_2_avocado_ours_TSDS"  "a_mug_1_avocado_ours_TSDS" "a_phone_case_avocado_ours_TSDS" ≈ "a_coffee_cup_ClothBag_ours_TSDS" "a_coffee_cup_OrangeGlove_ours_TSDS" "a_coffee_cup_cantaloupe_ours_TSDS" "a_coffee_cup_GoldGoat_ours_TSDS" "a_coffee_cup_Strawberry_ours_TSDS" "a_chopping_board_CuttingBoard_ours_TSDS" "a_cork_table_mat_CorkMat_ours_TSDS" "a_corn_1_Corn_ours_TSDS" "a_heat_resistant_glove_OrangeGlove_ours_TSDS" "a_miffy_bunny_GreenSweater_ours_TSDS" "a_NFL_football_2_Football_ours_TSDS" "a_potato_Potato_ours_TSDS" "a_strawberry_Strawberry_ours_TSDS" "an_orange_Orange_ours_TSDS" "an_avocado_avocado_ours_TSDS" "a_cactus_in_a_pot_3_Orange_OrangeGlove_ours_TSDS" "a_gold_goat_sculpture_GoldGoat_TableTennisHandle_ours_TSDS" "lamp1_ClothBag_MetalFrame_ours_TSDS")

# Define the number of GPUs available
num_gpus=4

# Function to run Python scripts in parallel
run_scripts() {
    local gpu_id=$1
    local obj=$2

    echo "Running script: $obj on GPU: $gpu_id"
    mkdir output
    mkdir output/${obj}_full_color_rotate
    # CUDA_VISIBLE_DEVICES=$gpu_id python blender_obj_uv_normal.py --data_path ../logs/$obj --rotate_video > output/${obj}_full_color_rotate/rotate_video.log

    # # specific rotating angle for avocado example
    # CUDA_VISIBLE_DEVICES=$gpu_id python blender_obj_uv_normal.py --data_path ../logs/$obj --start_rot_x 75 --rotate_video > output/${obj}_full_color_rotate/rotate_video.log

    # ffmpeg -y -i  output/${obj}_full_color_rotate/%4d.png -c:v libx264 -r 30 -pix_fmt yuv420p output/${obj}_full_color_rotate.mp4

    # Test single-frame renderning for "non-ours" method
    # we manually specify the albedo map's name since it doesn't follow our convention of naming
    CUDA_VISIBLE_DEVICES=$gpu_id python blender_obj_uv_normal.py --data_path ../logs/$obj --start_rot_x 75 --albedo_map "an_avocado_2_mesh.png" > output/${obj}_albedo_rotate/single_frame.log
}

for ((i=0; i<${#mesh_objs[@]}; i+=num_gpus)); do
    for ((j=0; j<num_gpus && i+j<${#mesh_objs[@]}; j++)); do
        run_scripts $j "${mesh_objs[$((i+j))]}" &
    done
    wait
done
