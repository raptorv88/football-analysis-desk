import math
from PIL import Image, ImageDraw

def create_analytics_favicon(size=64):
    scale = 4
    dim = size * scale
    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Dark squircle badge
    margin = int(dim * 0.04)
    radius = int(dim * 0.25)
    draw.rounded_rectangle(
        [margin, margin, dim - margin, dim - margin],
        radius=radius,
        fill=(15, 9, 23, 255),
        outline=(229, 46, 159, 210),
        width=int(scale * 1.5)
    )

    # 2. Subtle baseline
    base_y = int(dim * 0.82)
    draw.line([int(dim * 0.16), base_y, int(dim * 0.84), base_y], fill=(60, 45, 75, 255), width=int(scale * 1.5))

    # 3. Analytics vertical bars (Left: Cyan, Mid: Violet, Right: Hot Pink)
    bar_w = int(dim * 0.15)
    gap = int(dim * 0.06)
    b1_x = int(dim * 0.19)
    b2_x = b1_x + bar_w + gap
    b3_x = b2_x + bar_w + gap

    b1_h = int(dim * 0.28)
    b2_h = int(dim * 0.44)
    b3_h = int(dim * 0.60)

    # Bar 1 (Cyan)
    draw.rounded_rectangle(
        [b1_x, base_y - b1_h, b1_x + bar_w, base_y],
        radius=int(bar_w * 0.35),
        fill=(0, 229, 255, 240)
    )

    # Bar 2 (Purple / Violet)
    draw.rounded_rectangle(
        [b2_x, base_y - b2_h, b2_x + bar_w, base_y],
        radius=int(bar_w * 0.35),
        fill=(168, 85, 247, 240)
    )

    # Bar 3 (Vibrant Pink - primary brand color)
    draw.rounded_rectangle(
        [b3_x, base_y - b3_h, b3_x + bar_w, base_y],
        radius=int(bar_w * 0.35),
        fill=(229, 46, 159, 255)
    )

    # 4. Upward Analytics Trend Line with glowing nodes
    # Centers of the bar tops:
    p1 = (b1_x + bar_w // 2, base_y - b1_h)
    p2 = (b2_x + bar_w // 2, base_y - b2_h)
    p3 = (b3_x + bar_w // 2, base_y - b3_h)
    p_peak = (int(dim * 0.86), int(dim * 0.16))

    # Trend line
    line_pts = [p1, p2, p3, p_peak]
    for i in range(len(line_pts) - 1):
        draw.line([line_pts[i], line_pts[i+1]], fill=(255, 255, 255, 250), width=int(scale * 2.2))
        draw.line([line_pts[i], line_pts[i+1]], fill=(0, 240, 255, 180), width=int(scale * 1.2))

    # Glowing data point nodes on the trend line
    for pt in [p1, p2, p3]:
        r_node = int(scale * 3)
        draw.ellipse([pt[0] - r_node, pt[1] - r_node, pt[0] + r_node, pt[1] + r_node], fill=(255, 255, 255, 255), outline=(0, 229, 255, 255), width=int(scale * 0.8))

    # Peak target node (Spark / arrow node)
    r_peak = int(scale * 4.2)
    draw.ellipse([p_peak[0] - r_peak, p_peak[1] - r_peak, p_peak[0] + r_peak, p_peak[1] + r_peak], fill=(0, 240, 255, 255), outline=(255, 255, 255, 255), width=int(scale * 1.2))

    res = img.resize((size, size), Image.Resampling.LANCZOS)
    return res

# Generate PNG and multi-size ICO
img64 = create_analytics_favicon(64)
img64.save("frontend/favicon.png", "PNG")

img16 = create_analytics_favicon(16)
img32 = create_analytics_favicon(32)
img48 = create_analytics_favicon(48)
img64.save("frontend/favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

print("Analytics favicon generated: frontend/favicon.ico, frontend/favicon.png")

