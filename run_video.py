import argparse
import cv2
import numpy as np
import os
import torch
import torch.nn.functional as F
from torchvision.transforms import Compose
import subprocess, shlex

from depth_anything.dpt import DepthAnything
from depth_anything.util.transform import Resize, NormalizeImage, PrepareForNet
from depth_anything.util.colormap import get_colormap


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--video-path', type=str)
    parser.add_argument('--outdir', type=str, default='./vis_video_depth')
    parser.add_argument('--encoder', type=str, default='vitl', choices=['vits', 'vitb', 'vitl'])
    parser.add_argument('--only-depth', action='store_true', help="Output depth map only, no video")
    parser.add_argument('--with-sound', action='store_true', help="Add original audio-streams to output using ffmpeg")
    parser.add_argument('--colormap', type=str, default='inferno', help="specify which opencv colormap you want")

    args = parser.parse_args()

    # set colormap
    colormap = get_colormap(args.colormap)

    margin_width = 50

    DEVICE = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'

    depth_anything = DepthAnything.from_pretrained('LiheYoung/depth_anything_{}14'.format(args.encoder)).to(DEVICE).eval()
    
    total_params = sum(param.numel() for param in depth_anything.parameters())
    print('Total parameters: {:.2f}M'.format(total_params / 1e6))
    
    transform = Compose([
        Resize(
            width=518,
            height=518,
            resize_target=False,
            keep_aspect_ratio=True,
            ensure_multiple_of=14,
            resize_method='lower_bound',
            image_interpolation_method=cv2.INTER_CUBIC,
        ),
        NormalizeImage(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        PrepareForNet(),
    ])

    if os.path.isfile(args.video_path):
        if args.video_path.endswith('txt'):
            with open(args.video_path, 'r') as f:
                lines = f.read().splitlines()
        else:
            filenames = [args.video_path]
    else:
        filenames = os.listdir(args.video_path)
        filenames = [os.path.join(args.video_path, filename) for filename in filenames if not filename.startswith('.')]
        filenames.sort()
    
    os.makedirs(args.outdir, exist_ok=True)
    
    for k, filename in enumerate(filenames):
        print('Progress {:}/{:},'.format(k+1, len(filenames)), 'Processing', filename)

        raw_video = cv2.VideoCapture(filename)
        frame_width, frame_height = int(raw_video.get(cv2.CAP_PROP_FRAME_WIDTH)), int(raw_video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_rate = int(raw_video.get(cv2.CAP_PROP_FPS))
        output_width = frame_width if args.only_depth else frame_width * 2 + margin_width
        
        filename_base = os.path.basename(filename)
        output_path = os.path.join(args.outdir, filename_base[:filename_base.rfind('.')] + '_video_depth.mp4')
        out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), frame_rate, (output_width, frame_height))
        
        while raw_video.isOpened():
            ret, raw_frame = raw_video.read()
            if not ret:
                break
            
            frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2RGB) / 255.0
            
            frame = transform({'image': frame})['image']
            frame = torch.from_numpy(frame).unsqueeze(0).to(DEVICE)
            
            with torch.no_grad():
                depth = depth_anything(frame)

            depth = F.interpolate(depth[None], (frame_height, frame_width), mode='bilinear', align_corners=False)[0, 0]
            depth = (depth - depth.min()) / (depth.max() - depth.min()) * 255.0
            
            depth = depth.cpu().numpy().astype(np.uint8)
            depth_color = cv2.applyColorMap(depth, colormap)
            
            split_region = np.ones((frame_height, margin_width, 3), dtype=np.uint8) * 255
            combined_frame = depth_color if args.only_depth else cv2.hconcat([raw_frame, split_region, depth_color])
            
            out.write(combined_frame)
        
        raw_video.release()
        out.release()

        if args.with_sound:
            output_sound_path = os.path.join(args.outdir,
                                             filename_base[:filename_base.rfind('.')] + '_video_depth_sound.mp4')
            command = f"ffmpeg -y -i \"{filename}\" -i \"{output_path}\" -map 0:a -map 1:v:0 -c:v copy \"{output_sound_path}\""
            command = shlex.split(command)

            # Execute the command
            result = subprocess.run(command, capture_output=True, text=True)

            # Check if the command was successful
            if result.returncode == 0:
                # Command executed successfully, print output
                print("Command output:\n", result.stdout)
            else:
                # Command failed, print error message
                print("Error executing command:\n", result.stderr)

            # remove video without sound
            os.remove(output_path)
