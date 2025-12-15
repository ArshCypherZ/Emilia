
import os
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageChops

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_BOLD = os.path.join(BASE_DIR, "Logo", "Roboto-Medium.ttf")
FONT_REGULAR = os.path.join(BASE_DIR, "Logo", "Roboto-Regular.ttf")

def circle_crop(img):
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + img.size, fill=255)
    result = ImageOps.fit(img, mask.size, centering=(0.5, 0.5))
    result.putalpha(mask)
    return result

def draw_progress_bar(draw, x, y, w, h, progress, bg="#484b5b", fg="#00cec9"):
    # Draw background
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h/2, fill=bg)
    # Draw progress
    w_progress = max(h, int(w * progress))  # Ensure at least circle size
    if progress > 0:
        draw.rounded_rectangle((x, y, x + w_progress, y + h), radius=h/2, fill=fg)

def draw_gradient(draw, width, height, c1, c2):
    for y in range(height):
        r = int(c1[0] + (c2[0] - c1[0]) * y / height)
        g = int(c1[1] + (c2[1] - c1[1]) * y / height)
        b = int(c1[2] + (c2[2] - c1[2]) * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

def generate_rank_card_sync(
    firstname: str,
    avatar_bytes: bytes | None,
    current_xp: int,
    total_xp: int,
    level: int,
    rank_name: str,
):
    # Canvas
    W, H = 1000, 300
    
    # Gradient Background (Dark Blue/Purple to Black)
    # c1 = (30, 30, 35) # Old
    c1 = (15, 12, 41) 
    c2 = (48, 43, 99)
    # c3 = (36, 36, 62)
    
    image = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(image)
    
    # Horizontal Gradient
    for x in range(W):
        r = int(c1[0] + (c2[0] - c1[0]) * x / W)
        g = int(c1[1] + (c2[1] - c1[1]) * x / W)
        b = int(c1[2] + (c2[2] - c1[2]) * x / W)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

    # Load Fonts
    try:
        font_name = ImageFont.truetype(FONT_BOLD, 65)
        font_rank = ImageFont.truetype(FONT_BOLD, 45)
        font_xp = ImageFont.truetype(FONT_BOLD, 35)
        font_level = ImageFont.truetype(FONT_BOLD, 50)
    except IOError:
        font_name = ImageFont.load_default()
        font_rank = ImageFont.load_default()
        font_xp = ImageFont.load_default()
        font_level = ImageFont.load_default()

    # Avatar
    avatar_size = 230
    avatar_pos = (35, 35)
    
    if avatar_bytes:
        try:
            avatar = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            avatar = circle_crop(avatar)
            avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
        except Exception:
            avatar = Image.new("RGBA", (avatar_size, avatar_size), (200, 200, 200))
            avatar = circle_crop(avatar)
    else:
        # Default avatar
        avatar = Image.new("RGBA", (avatar_size, avatar_size), (100, 100, 100))
        avatar = circle_crop(avatar)
    
    # Shadow for avatar
    shadow = Image.new("RGBA", (avatar_size+10, avatar_size+10), (0, 0, 0, 80))
    shadow = circle_crop(shadow)
    image.paste(shadow, (avatar_pos[0]-5, avatar_pos[1]-5), shadow)
    image.paste(avatar, avatar_pos, avatar)

    # Text Positions
    text_x = 300
    
    # Name (Truncate if too long)
    if len(firstname) > 20:
        firstname = firstname[:17] + "..."
    draw.text((text_x, 40), firstname, font=font_name, fill="white")
    
    # Rank
    draw.text((text_x, 120), f"{rank_name}", font=font_rank, fill="#00cec9")
    
    # Level (Right adjusted)
    level_text = f"Level {level}"
    try:
        lvl_w = draw.textbbox((0,0), level_text, font=font_level)[2]
        draw.text((W - 50 - lvl_w, 45), level_text, font=font_level, fill="#ff7675")
    except:
        draw.text((W - 250, 45), level_text, font=font_level, fill="#ff7675")

    # XP Text
    xp_text = f"{current_xp} / {total_xp} XP"
    draw.text((text_x, 210), xp_text, font=font_xp, fill="#dfe6e9")

    # Progress Bar
    bar_x = text_x
    bar_y = 255
    bar_w = W - bar_x - 50
    bar_h = 25
    
    progress = 0
    if total_xp > 0:
        progress = min(1.0, current_xp / total_xp)
        
    draw_progress_bar(draw, bar_x, bar_y, bar_w, bar_h, progress, bg="#2d3436", fg="#0984e3")

    # Save to buffer
    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output
