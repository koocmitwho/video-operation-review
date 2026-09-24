"""Small lossless, synthetic fixtures. No captured user screen or historical video."""
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw


def run(args, cwd=None):
    p = subprocess.run(args, cwd=cwd, capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8', errors='replace'))


def make_fixtures(root, ffmpeg='ffmpeg'):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    frames = []
    for n in range(8):
        img = Image.new('RGB', (160, 90), (32, 32, 32))
        draw = ImageDraw.Draw(img)
        draw.text((5, 5), 'SYNTHETIC TEST', fill='white')
        if n == 3:
            draw.rectangle((145, 81, 147, 83), fill='white')
        if n >= 6:
            draw.rectangle((30, 25, 125, 68), fill=(150, 150, 150))
        frames.append(img)
    p = subprocess.run([ffmpeg, '-v', 'error', '-y', '-f', 'rawvideo',
                        '-pixel_format', 'rgb24', '-video_size', '160x90',
                        '-framerate', '8', '-i', 'pipe:0', '-c:v', 'ffv1',
                        str(root / '重复与瞬态 test.mkv')],
                       input=b''.join(im.tobytes() for im in frames), capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.decode('utf-8', errors='replace'))
    for n in range(4):
        img = Image.new('RGB', (426, 240), (20 + n * 20, 30, 40))
        ImageDraw.Draw(img).text((10, 10), f'SYNTHETIC VFR {n}', fill='white')
        img.save(root / f'vfr{n}.png')
    (root / 'timings.txt').write_text(
        "ffconcat version 1.0\nfile vfr0.png\nduration 0.04\n"
        "file vfr1.png\nduration 0.16\nfile vfr2.png\nduration 0.28\nfile vfr3.png\n",
        encoding='utf-8')
    run([ffmpeg, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', 'timings.txt',
         '-fps_mode', 'vfr', '-c:v', 'ffv1', '-output_ts_offset', '5', '不同尺寸 VFR.mkv'], root)
    (root / '损坏.mkv').write_bytes(b'not a video\x00\x01')
    return root / '重复与瞬态 test.mkv', root / '不同尺寸 VFR.mkv'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    args = parser.parse_args()
    for path in make_fixtures(args.output):
        print(path)
