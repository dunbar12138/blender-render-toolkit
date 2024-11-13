# write a script to combine the full-color rendering and normal rendering into a single video, split into left and right, freeze the middle frame and do a sliding window effect
import cv2
import numpy as np
import os, sys
import argparse
import numpy as np

def parse_args():
    parser = argparse.ArgumentParser(description='Create a swipe window effect')
    parser.add_argument('--output_path', type=str, default='output', help='Path to save the rendered image')
    parser.add_argument('--obj_name', type=str, required=True, help='Name of the object')

    return parser.parse_args()


# swipe screen function, per frame
def lin_brush(col_g, color, t, shift=1/6):
    # NOTE: add a shift so the sliding window effect starts from the middle
    t = t + shift 
    t = t - 1 if t > 1 else t
    t = np.sin(t*np.pi)
    imgw = col_g.shape[1]
    wpx = int(t*imgw)
    img_new = np.zeros_like(color)
    img_new[:,:wpx] = color[:,:wpx]
    img_new[:,wpx:] = col_g[:,wpx:]

    return img_new


def main():

    args = parse_args()
    # Settings
    frame_count = 251  # Total frames
    halfway = frame_count // 2
    freeze_frame = 3 # duration of the freeze frame
    slide_frames = 80  # Duration of slide effect
    width, height = (720, 720)  # Use your video's actual width and height

    # Initialize output frames list
    output_frames = []

    # Loop over all frames
    for i in range(frame_count):
        # Load frames from both videos
        frameA = cv2.imread(f'{args.output_path}/{args.obj_name}_full_color_rotate/{i:04d}.png')
        frameB = cv2.imread(f'{args.output_path}/{args.obj_name}_normal_rotate/{i:04d}.png')

        # Initial split-screen effect: left from A, right from B
        if i != halfway:
            # Standard split down the middle
            combined = np.hstack((frameA[:, :width//2], frameB[:, width//2:]))
            # Add combined frame to output frames
            output_frames.append(combined)

        else: # free the frame and do the sliding window effect
            for t in range(freeze_frame):
                combined = np.hstack((frameA[:, :width//2], frameB[:, width//2:]))
                output_frames.append(combined)

            for t in range(slide_frames):
                # blend two frames
                combined = lin_brush(frameA, frameB, t/slide_frames)
                output_frames.append(combined)
            
            for t in range(freeze_frame):
                combined = np.hstack((frameA[:, :width//2], frameB[:, width//2:]))
                output_frames.append(combined)

    # Save output frames
    output_dir = os.path.join(args.output_path, f'{args.obj_name}_combined_swipe')
    os.makedirs(output_dir, exist_ok=True)
    for idx, frame in enumerate(output_frames):
        cv2.imwrite(f'{output_dir}/{idx:04d}.png', frame)



if __name__ == "__main__":
    main()