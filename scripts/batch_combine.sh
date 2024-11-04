#!/bin/bash

# Define the lists of textures and indices
mesh_objs=("a_beanie_1_GreenSweater_ours" "a_toy_flower_2_GreenSweater_ours" "a_miffy_bunny_GreenSweater_ours"  "a_mug_1_avocado_ours"  "a_phone_case_avocado_ours" "a_coffee_cup_ClothBag_ours" "a_coffee_cup_OrangeGlove_ours" "a_coffee_cup_cantaloupe_ours" "a_coffee_cup_GoldGoat_ours" "a_coffee_cup_Strawberry_ours" "a_chopping_board_CuttingBoard_ours" "a_cork_table_mat_CorkMat_ours" "a_corn_1_Corn_ours" "a_heat_resistant_glove_OrangeGlove_ours" "a_NFL_football_2_Football_ours" "a_potato_Potato_ours" "a_strawberry_Strawberry_ours" "an_orange_Orange_ours" "a_gold_goat_sculpture_GoldGoat_TableTennisHandle__multiparts_2_ours" "a_cactus_in_a_pot_3_Orange_OrangeGlove__multiparts_2_ours" "lamp1_ClothBag_MetalFrame__multiparts_2_ours")
#  

# Define the number of GPUs available
num_gpus=4

# Function to run Python scripts in parallel
run_scripts() {
    local gpu_id=$1
    local obj=$2

    ffmpeg -y -i blender/output/${obj}_full_color_rotate.mp4 -i blender/output/${obj}_normal_rotate.mp4 -filter_complex vstack -c:v libx264 -r 30 -pix_fmt yuv420p blender/output/${obj}_combined.mp4
}

for ((i=0; i<${#mesh_objs[@]}; i+=num_gpus)); do
    for ((j=0; j<num_gpus && i+j<${#mesh_objs[@]}; j++)); do
        run_scripts $j "${mesh_objs[$((i+j))]}" &
    done
    wait
done
