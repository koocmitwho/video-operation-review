"""Create a synthetic GUI sequence for agent forward-testing, never a real app recording."""
import argparse
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont


def make(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=20)
    small = ImageFont.load_default(size=16)
    frames = []
    # Each entry is an intentionally visible state; actions between states may be unobserved.
    states = [
        ('main', '1', 'Ready', ''),
        ('main', '1', 'Ready', ''),
        ('menu', '1', 'Ready', ''),
        ('dialog', '1', 'Ready', ''),
        ('dialog', '20', 'Ready', ''),
        ('main', '1', 'Cancelled', ''),
        ('dialog', '5', 'Ready', ''),
        ('dialog', '5', 'Ready', ''),
        ('main', '5', 'Applied rate = 5', ''),
        ('main', '5', 'Running...', 'print("SUCCESS")'),
        ('main', '5', 'Error: output folder not found', 'print("SUCCESS")'),
        ('main', '5', 'Error: output folder not found', 'print("SUCCESS")'),
    ]
    for mode, rate, state, code in states:
        image = Image.new('RGB', (800, 450), '#eef1f4')
        d = ImageDraw.Draw(image)
        d.rectangle((0, 0, 800, 35), fill='#24334a')
        d.text((12, 7), 'SYNTHETIC UI FIXTURE - NOT A REAL APP', fill='white', font=font)
        d.text((15, 47), 'File       Settings       Run', fill='#182536', font=font)
        d.text((15, 100), 'Selected object: Sample A', fill='#182536', font=font)
        d.text((15, 137), f'Current rate: {rate if mode == "main" else "1"}', fill='#182536', font=font)
        d.text((15, 175), 'Input: input.csv', fill='#182536', font=font)
        d.text((15, 212), 'Output: results/out.csv', fill='#182536', font=font)
        if code:
            d.text((15, 265), 'Editor source (not execution output):', fill='#182536', font=small)
            d.text((15, 294), code, fill='#004590', font=font)
        if mode == 'menu':
            d.rectangle((100, 78, 350, 118), fill='white', outline='#596e85')
            d.text((111, 88), 'Processing options...', fill='#182536', font=font)
        if mode == 'dialog':
            d.rectangle((300, 90, 735, 340), fill='#fcfcff', outline='#50657c', width=2)
            d.text((322, 108), 'Processing options', fill='#182536', font=font)
            d.text((322, 167), 'Rate:', fill='#182536', font=font)
            d.rectangle((410, 155, 660, 199), fill='white', outline='#385380')
            d.text((427, 167), rate, fill='#182536', font=font)
            d.rectangle((409, 264, 535, 311), fill='#e2eafa', outline='#385380')
            d.text((440, 278), 'Apply', fill='#182536', font=font)
            d.rectangle((552, 264, 692, 311), fill='#eeeeee', outline='#385380')
            d.text((579, 278), 'Cancel', fill='#182536', font=font)
        d.rectangle((0, 400, 800, 450), fill='#dce4ec')
        d.text((12, 416), state, fill='#982822' if state.startswith('Error') else '#182536', font=font)
        frames.append(image.tobytes())
    proc = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pixel_format', 'rgb24',
                           '-video_size', '800x450', '-framerate', '2', '-i', 'pipe:0', '-c:v', 'ffv1',
                           str(output)], input=b''.join(frames), capture_output=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode('utf-8', errors='replace'))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    print(make(parser.parse_args().output))
