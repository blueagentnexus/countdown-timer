"""Generate a stopwatch-with-smiley-face .ico for Countdown Clock."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "stopwatch_smiley.ico"


def draw(size: int) -> Image.Image:
    """Render a stopwatch + smiley at a given square size."""
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Scale helpers (all coords relative to a 256-base design).
    k = s / 256.0

    def sc(x):
        return int(round(x * k))

    body_color = (255, 173, 70, 255)   # orange (#FFAD46)
    rim_color = (40, 40, 40, 255)
    highlight = (255, 220, 150, 255)
    face_color = (255, 245, 200, 255)
    dark = (30, 30, 30, 255)
    red = (220, 50, 50, 255)

    # ---- Top crown (the little knob on top of the stopwatch) ----
    # Small rectangle + tiny button
    crown_w = sc(54)
    crown_h = sc(22)
    crown_x = (s - crown_w) // 2
    crown_y = sc(14)
    d.rounded_rectangle(
        [crown_x, crown_y, crown_x + crown_w, crown_y + crown_h],
        radius=sc(5), fill=rim_color,
    )
    # Button cap
    cap_w = sc(28)
    cap_h = sc(14)
    cap_x = (s - cap_w) // 2
    cap_y = sc(4)
    d.rounded_rectangle(
        [cap_x, cap_y, cap_x + cap_w, cap_y + cap_h],
        radius=sc(4), fill=rim_color,
    )

    # Side buttons (little nubs at upper-left and upper-right of body)
    nub_w = sc(16)
    nub_h = sc(14)
    # left
    d.rounded_rectangle(
        [sc(36), sc(54), sc(36) + nub_w, sc(54) + nub_h],
        radius=sc(3), fill=rim_color,
    )
    # right
    d.rounded_rectangle(
        [s - sc(36) - nub_w, sc(54), s - sc(36), sc(54) + nub_h],
        radius=sc(3), fill=rim_color,
    )

    # ---- Body (big circle) - centered square bounding box ----
    # Use a perfectly square body so inner rings are concentric.
    body_diam = sc(220)
    body_cx = s // 2
    body_cy = sc(36) + body_diam // 2
    body_bbox = [body_cx - body_diam // 2, body_cy - body_diam // 2,
                 body_cx + body_diam // 2, body_cy + body_diam // 2]
    # Outer rim (dark)
    d.ellipse(body_bbox, fill=rim_color)
    # Inner body (orange)
    inset = sc(10)
    inner = [body_bbox[0] + inset, body_bbox[1] + inset,
             body_bbox[2] - inset, body_bbox[3] - inset]
    d.ellipse(inner, fill=body_color)

    # Subtle highlight crescent (top-left) using two concentric ellipses.
    hl_pad = sc(6)
    hl_outer = [inner[0] + hl_pad, inner[1] + hl_pad,
                inner[2] - hl_pad, inner[3] - hl_pad]
    d.pieslice(hl_outer, start=205, end=315, fill=highlight)
    # Mask the inside with body color (leaving only a thin crescent).
    mask_pad = sc(10)
    hl_mask = [hl_outer[0] + mask_pad, hl_outer[1] + mask_pad,
               hl_outer[2] - mask_pad, hl_outer[3] - mask_pad]
    d.ellipse(hl_mask, fill=body_color)

    # ---- Face disc (lighter circle inside body, centered) ----
    face_pad = sc(32)
    face_bbox = [inner[0] + face_pad, inner[1] + face_pad,
                 inner[2] - face_pad, inner[3] - face_pad]
    d.ellipse(face_bbox, fill=face_color, outline=dark, width=max(1, sc(3)))

    # ---- Smiley ----
    cx = (face_bbox[0] + face_bbox[2]) // 2
    cy = (face_bbox[1] + face_bbox[3]) // 2
    face_w = face_bbox[2] - face_bbox[0]

    # Eyes (slightly raised, round dots)
    eye_r = max(2, sc(10))
    eye_dx = sc(22)
    eye_dy = sc(18)
    for ex in (cx - eye_dx, cx + eye_dx):
        d.ellipse(
            [ex - eye_r, cy - eye_dy - eye_r,
             ex + eye_r, cy - eye_dy + eye_r],
            fill=dark,
        )

    # Mouth (smile arc, raised a bit)
    mouth_w = sc(74)
    mouth_h = sc(44)
    mouth_top = cy - sc(8)
    mouth_bbox = [cx - mouth_w // 2, mouth_top,
                  cx + mouth_w // 2, mouth_top + mouth_h]
    d.arc(mouth_bbox, start=15, end=165, fill=dark, width=max(2, sc(7)))

    # ---- 12 o'clock tick (clearly inside the orange ring, not touching rim) ----
    tick_w = sc(6)
    tick_h = sc(16)
    # Place the tick between the outer dark rim and the cream face disc.
    tick_top = inner[1] + sc(6)
    d.rounded_rectangle(
        [cx - tick_w // 2, tick_top,
         cx + tick_w // 2, tick_top + tick_h],
        radius=sc(2), fill=red,
    )

    return img


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = draw(256)
    images = [draw(sz) for sz in sizes]
    # Pillow supports multi-size ICO via the `sizes` arg or via images list.
    base.save(
        OUT, format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[:-1],
    )
    print(f"Wrote: {OUT}")


if __name__ == "__main__":
    main()
