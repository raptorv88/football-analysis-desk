import math
from PIL import Image, ImageDraw, ImageFilter

def create_favicon(size=64):
    # Render at 4x for smooth anti-aliased scaling
    scale = 4
    dim = size * scale
    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background rounded rect
    corner_radius = int(dim * 0.26)
    margin = int(dim * 0.04)
    draw.rounded_rectangle(
        [margin, margin, dim - margin, dim - margin],
        radius=corner_radius,
        fill=(18, 10, 26, 255),
        outline=(229, 46, 159, 220),
        width=int(scale * 1.5)
    )

    # 2. Football circle in center
    cx, cy = dim / 2, dim / 2
    r = dim * 0.33
    
    # Outer glow / shadow
    draw.ellipse([cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2], fill=(10, 5, 15, 180))

    # Ball base
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(245, 247, 250, 255), outline=(20, 12, 28, 255), width=int(scale * 1.8))

    # 3. Outer patches (classic dark panels of soccer ball)
    def pol(dist, angle_deg):
        rad = math.radians(angle_deg)
        return (cx + dist * math.cos(rad), cy + dist * math.sin(rad))

    # Central pentagon (brand pink #e52e9f)
    r_pent = r * 0.42
    pent_points = [pol(r_pent, -90 + i * 72) for i in range(5)]
    
    # Outer radiating seams to perimeter
    outer_points = [pol(r, -90 + i * 72) for i in range(5)]
    for i in range(5):
        draw.line([pent_points[i], outer_points[i]], fill=(25, 15, 35, 255), width=int(scale * 1.8))

    # Outer dark panels
    # Between outer points:
    for i in range(5):
        # Draw trapezoidal / triangular edge patch
        p1 = outer_points[i]
        p2 = pol(r, -90 + i * 72 - 18)
        p3 = pol(r, -90 + i * 72 + 18)
        p_mid = pol(r * 0.72, -90 + i * 72)
        draw.polygon([p2, p1, p3, p_mid], fill=(24, 15, 33, 255))
        draw.line([p2, p_mid], fill=(20, 12, 28, 255), width=int(scale * 1.2))
        draw.line([p3, p_mid], fill=(20, 12, 28, 255), width=int(scale * 1.2))
        draw.line([pent_points[i], p_mid], fill=(20, 12, 28, 255), width=int(scale * 1.5))

    # Central pentagon drawn on top in hot pink
    draw.polygon(pent_points, fill=(229, 46, 159, 255), outline=(255, 255, 255, 230), width=int(scale * 1.2))

    # Inner decorative pentagon highlight
    r_pent_inner = r_pent * 0.45
    pent_inner = [pol(r_pent_inner, -90 + i * 72) for i in range(5)]
    draw.polygon(pent_inner, fill=(255, 75, 184, 255))

    # 4. Ball outer rim outline
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(20, 12, 28, 255), width=int(scale * 1.8))

    # 5. Vibrant electric cyan analytics badge dot in bottom right
    dot_r = dim * 0.075
    dot_x, dot_y = dim - margin - dot_r - 2, dim - margin - dot_r - 2
    draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=(0, 229, 255, 255), outline=(255, 255, 255, 255), width=int(scale * 1))

    # Downsample with Lanczos for crisp rendering
    res = img.resize((size, size), Image.Resampling.LANCZOS)
    return res

# Generate 64x64 PNG
img64 = create_favicon(64)
img64.save("frontend/favicon.png", "PNG")

# Generate multi-size ICO (16, 32, 48, 64)
img16 = create_favicon(16)
img32 = create_favicon(32)
img48 = create_favicon(48)
img64.save("frontend/favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])

print("Favicon files created successfully: frontend/favicon.ico and frontend/favicon.png")

