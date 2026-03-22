"""
create_icon.py — Generates study_companion.ico
Run once before building: python create_icon.py
Requires: pip install Pillow
"""
from PIL import Image, ImageDraw, ImageFont
import os

def make_icon():
    sizes = [256, 128, 64, 48, 32, 16]
    frames = []

    for size in sizes:
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Rounded rectangle background
        pad  = int(size * 0.06)
        r    = int(size * 0.22)
        draw.rounded_rectangle(
            [pad, pad, size - pad, size - pad],
            radius=r,
            fill=(218, 119, 86, 255),   # --accent colour
        )

        # Book emoji approximation — white rectangle pages
        bx = int(size * 0.22)
        by = int(size * 0.20)
        bw = int(size * 0.56)
        bh = int(size * 0.60)
        # Left page
        draw.rectangle([bx, by, bx + bw//2 - 1, by + bh], fill=(255, 255, 255, 230))
        # Right page
        draw.rectangle([bx + bw//2 + 1, by, bx + bw, by + bh], fill=(255, 255, 255, 200))
        # Spine
        draw.rectangle([bx + bw//2 - 2, by, bx + bw//2 + 2, by + bh],
                       fill=(218, 119, 86, 255))
        # Lines on left page
        lx = bx + int(size * 0.05)
        for i in range(3):
            y = by + int(size * 0.15) + i * int(size * 0.12)
            lw = int(size * 0.18) - i * int(size * 0.02)
            draw.rectangle([lx, y, lx + lw, y + max(1, int(size * 0.03))],
                           fill=(180, 100, 60, 180))

        frames.append(img)

    out = os.path.join(os.path.dirname(__file__), "study_companion.ico")
    frames[0].save(
        out, format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"Icon saved to: {out}")


if __name__ == "__main__":
    make_icon()
