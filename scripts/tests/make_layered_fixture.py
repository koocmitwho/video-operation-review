"""Bounded tutorial fixture: UI text is synthetic, never a real program result."""
from pathlib import Path
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont


def make_tutorial(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype('DejaVuSans.ttf', 18) if Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').exists() else ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 18)
    for n in range(32):
        im = Image.new('RGB', (640, 360), '#20242b')
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 640, 38), fill='#3d4b61')
        d.text((12, 8), 'Synthetic Lab | File   Settings   Run', fill='white', font=font)
        d.text((20, 62), 'Object: Model-A', fill='white', font=font)
        rate = '1.00' if n < 21 else '0.02'
        d.text((20, 98), 'Applied rate: '+rate, fill='white', font=font)
        status = 'Waiting for user' if n < 16 else 'Ready'
        if n in (16, 23):
            d.rectangle((70, 40, 340, 155), fill='#e9eef4')
            d.text((80, 55), 'Edit rate...' if n == 16 else 'Import result.csv', fill='black', font=font)
            d.text((80, 100), 'Menu visible for ONE frame', fill='black', font=font)
        if n in (17, 19, 20):
            d.rectangle((160, 120, 550, 285), fill='#c2c9d3')
            d.text((180, 135), 'Rate settings | Model-A', fill='black', font=font)
            val = {17: '0.20', 19: '1.00', 20: '0.02'}[n]
            d.rectangle((295, 170, 420, 206), fill='white')
            d.text((180, 177), 'Rate:', fill='black', font=font)
            d.text((300, 177), val, fill='black', font=font)
            d.text((230, 244), 'Apply          Cancel', fill='black', font=font)
        if n == 18: status = 'Cancelled. Applied rate remains 1.00'
        if n == 21: status = 'Applied rate = 0.02'
        if n >= 22:
            d.text((20, 305), 'Output: result.csv', fill='#b4ebcc', font=font)
            status = 'Export completed: result.csv'
        if n >= 24:
            d.text((20, 145), 'Input: result.csv | Loaded rows: 8', fill='#b4ebcc', font=font)
            status = 'Loaded result.csv (8 rows)'
        d.text((20, 333), status, fill='white', font=font)
        if n < 16 or n > 24:
            d.rectangle((450+n*3, 75, 453+n*3, 83), fill='white')
            if n % 2: d.rectangle((400, 200, 401, 215), fill='#aeb8c4')
        im.save(root / f'{n:03}.png')
    video = root / 'tutorial.mkv'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', '8', '-i', str(root/'%03d.png'), '-c:v', 'ffv1', str(video)], check=True, capture_output=True)
    truth = {'kind': 'synthetic UI', 'frames': 32, 'key_frames': list(range(16,25)), 'final_rate': '0.02', 'cancelled_value': '0.20', 'handoff': 'result.csv', 'real_user_video': False}
    (root/'truth.json').write_text(json.dumps(truth, indent=2), encoding='utf-8')
    return video
