from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import requests
from io import BytesIO
import base64
import os
import urllib.request
import re

# Arabic text support

try:
import arabic_reshaper
from bidi.algorithm import get_display
ARABIC_SUPPORT = True
except ImportError:
ARABIC_SUPPORT = False
print(“Warning: arabic-reshaper or python-bidi not installed. Arabic text may not render correctly.”)

app = FastAPI()

# Enable CORS

app.add_middleware(
CORSMiddleware,
allow_origins=[”*”],
allow_credentials=True,
allow_methods=[”*”],
allow_headers=[”*”],
)

# Format presets with safe zones

# Safe zones account for platform UI overlays (username, CTA buttons, etc.)

FORMAT_PRESETS = {
# SQUARE FORMATS (1:1)
“instagram_feed”: {
“width”: 1080,
“height”: 1080,
“safe_top”: 0.05,      # Minimal - no major UI overlay on squares
“safe_bottom”: 0.05,   # Minimal - caption appears below image
“aspect”: “square”
},
“facebook_feed”: {
“width”: 1080,
“height”: 1080,
“safe_top”: 0.05,
“safe_bottom”: 0.05,
“aspect”: “square”
},


# VERTICAL FORMATS (9:16) - Stories/Reels
"instagram_story": {
    "width": 1080, 
    "height": 1920, 
    "safe_top": 0.20,      # 20% - Username, sponsored label, close button
    "safe_bottom": 0.15,   # 15% - Swipe up / CTA button area
    "aspect": "vertical"
},
"instagram_reel": {
    "width": 1080, 
    "height": 1920, 
    "safe_top": 0.18,      # Slightly less than story
    "safe_bottom": 0.20,   # More bottom space for captions/buttons
    "aspect": "vertical"
},
"facebook_story": {
    "width": 1080, 
    "height": 1920, 
    "safe_top": 0.20, 
    "safe_bottom": 0.15,
    "aspect": "vertical"
},
"facebook_reel": {
    "width": 1080, 
    "height": 1920, 
    "safe_top": 0.18, 
    "safe_bottom": 0.20,
    "aspect": "vertical"
},
"tiktok": {
    "width": 1080, 
    "height": 1920, 
    "safe_top": 0.20,      # TikTok has more UI at top
    "safe_bottom": 0.22,   # Captions, buttons, engagement icons
    "aspect": "vertical"
},

# LANDSCAPE FORMAT (for Facebook feed link posts)
"facebook_landscape": {
    "width": 1200, 
    "height": 628, 
    "safe_top": 0.08, 
    "safe_bottom": 0.08,
    "aspect": "landscape"
},

# ALIASES for simpler naming (matches your form options)
"square": {
    "width": 1080, 
    "height": 1080, 
    "safe_top": 0.05, 
    "safe_bottom": 0.05,
    "aspect": "square"
},
"vertical": {
    "width": 1080, 
    "height": 1920, 
    "safe_top": 0.20,      # 20% top safe zone
    "safe_bottom": 0.15,   # 15% bottom safe zone
    "aspect": "vertical"
},
"story": {
    "width": 1080, 
    "height": 1920, 
    "safe_top": 0.20, 
    "safe_bottom": 0.15,
    "aspect": "vertical"
},
"reel": {
    "width": 1080, 
    "height": 1920, 
    "safe_top": 0.18, 
    "safe_bottom": 0.20,
    "aspect": "vertical"
},


}

# =============================================================================

# ARABIC TEXT UTILITIES

# =============================================================================

def contains_arabic(text):
“”“Check if text contains Arabic characters”””
arabic_pattern = re.compile(r’[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]’)
return bool(arabic_pattern.search(text))

def contains_rtl(text):
“”“Check if text contains any RTL characters (Arabic, Hebrew, etc.)”””
rtl_pattern = re.compile(r’[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]’)
return bool(rtl_pattern.search(text))

def process_arabic_text(text):
“””
Process Arabic text for correct display:
1. Reshape letters (connect them properly)
2. Apply bidirectional algorithm (RTL display)
“””
if not ARABIC_SUPPORT:
return text


if not contains_arabic(text):
    return text

try:
    # Reshape Arabic characters (connects letters properly)
    reshaped_text = arabic_reshaper.reshape(text)
    # Apply bidirectional algorithm for correct RTL display
    bidi_text = get_display(reshaped_text)
    return bidi_text
except Exception as e:
    print(f"Arabic text processing error: {e}")
    return text


def get_text_alignment(text, requested_alignment=“center”):
“””
Determine text alignment based on content and request.
Arabic text defaults to right-aligned unless specified otherwise.
“””
if requested_alignment != “auto”:
return requested_alignment


# Auto-detect: Arabic = right, others = center
if contains_rtl(text):
    return "right"
return "center"


# =============================================================================

# FONT UTILITIES

# =============================================================================

def download_font(font_name=“bold”):
“”“Download and cache font”””
font_path = f”/tmp/{font_name}_font.ttf”
if not os.path.exists(font_path):
try:
url = “https://raw.githubusercontent.com/googlefonts/Montserrat/main/fonts/ttf/Montserrat-Bold.ttf”
headers = {‘User-Agent’: ‘Mozilla/5.0’}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as response:
with open(font_path, ‘wb’) as f:
f.write(response.read())
except Exception as e:
print(f”Font download failed: {e}”)
try:
alt_url = “https://cdn.jsdelivr.net/fontsource/fonts/montserrat@latest/latin-700-normal.ttf”
req = urllib.request.Request(alt_url, headers={‘User-Agent’: ‘Mozilla/5.0’})
with urllib.request.urlopen(req, timeout=10) as response:
with open(font_path, ‘wb’) as f:
f.write(response.read())
except Exception as e2:
print(f”Alt font download also failed: {e2}”)
return None
return font_path

def download_custom_font(font_url, font_id):
“”“Download custom font from URL (e.g., Airtable attachment)”””
import hashlib
url_hash = hashlib.md5(font_url.encode()).hexdigest()[:8]
font_path = f”/tmp/custom_{font_id}_{url_hash}.ttf”


if not os.path.exists(font_path):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(font_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            with open(font_path, 'wb') as f:
                f.write(response.read())
    except Exception as e:
        print(f"Custom font download failed: {e}")
        return None
return font_path


def download_font_regular():
“”“Download regular weight font”””
font_path = “/tmp/regular_font.ttf”
if not os.path.exists(font_path):
try:
url = “https://raw.githubusercontent.com/googlefonts/Montserrat/main/fonts/ttf/Montserrat-SemiBold.ttf”
headers = {‘User-Agent’: ‘Mozilla/5.0’}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=10) as response:
with open(font_path, ‘wb’) as f:
f.write(response.read())
except Exception as e:
print(f”Font download failed: {e}”)
return None
return font_path

def get_font(size, bold=True, custom_font_url=None):
“”“Get font at specified size with proper fallback”””


if custom_font_url:
    custom_font_path = "/tmp/custom_font.ttf"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(custom_font_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            with open(custom_font_path, 'wb') as f:
                f.write(response.read())
        return ImageFont.truetype(custom_font_path, size)
    except Exception as e:
        print(f"Custom font download failed: {e}")

font_path = download_font() if bold else download_font_regular()
if font_path and os.path.exists(font_path):
    try:
        return ImageFont.truetype(font_path, size)
    except Exception as e:
        print(f"Font load error: {e}")

# Fallback - try system fonts (including Arabic-supporting fonts)
fallback_fonts = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",  # Arabic support
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]
for fallback in fallback_fonts:
    if os.path.exists(fallback):
        try:
            return ImageFont.truetype(fallback, size)
        except:
            continue

return ImageFont.load_default()


# =============================================================================

# DRAWING UTILITIES

# =============================================================================

def hex_to_rgb(hex_color):
“”“Convert hex colour to RGB tuple”””
hex_color = hex_color.lstrip(’#’)
return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def get_text_size(draw, text, font):
“”“Get text bounding box size”””
bbox = draw.textbbox((0, 0), text, font=font)
return bbox[2] - bbox[0], bbox[3] - bbox[1]

def draw_text_with_shadow(draw, position, text, font, fill, shadow_color=None, shadow_offset=3, shadow_opacity=80):
“”“Draw text with soft shadow for better readability”””
x, y = position


if shadow_color is None:
    shadow_color = (60, 60, 60)

# Draw soft shadow
draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color + (shadow_opacity,))
# Draw main text
draw.text((x, y), text, font=font, fill=fill)


def draw_rounded_rectangle(draw, coords, radius, fill, outline=None, outline_width=0):
“”“Draw a rounded rectangle”””
x1, y1, x2, y2 = coords


draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)

draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)

if outline:
    draw.arc([x1, y1, x1 + radius * 2, y1 + radius * 2], 180, 270, fill=outline, width=outline_width)
    draw.arc([x2 - radius * 2, y1, x2, y1 + radius * 2], 270, 360, fill=outline, width=outline_width)
    draw.arc([x1, y2 - radius * 2, x1 + radius * 2, y2], 90, 180, fill=outline, width=outline_width)
    draw.arc([x2 - radius * 2, y2 - radius * 2, x2, y2], 0, 90, fill=outline, width=outline_width)
    draw.line([x1 + radius, y1, x2 - radius, y1], fill=outline, width=outline_width)
    draw.line([x1 + radius, y2, x2 - radius, y2], fill=outline, width=outline_width)
    draw.line([x1, y1 + radius, x1, y2 - radius], fill=outline, width=outline_width)
    draw.line([x2, y1 + radius, x2, y2 - radius], fill=outline, width=outline_width)


def wrap_text(draw, text, font, max_width, is_rtl=False):
“””
Word wrap text to fit within max_width.
Handles both LTR and RTL text properly.
“””
words = text.split()
lines = []
current_line = “”


for word in words:
    test_line = current_line + " " + word if current_line else word
    bbox = draw.textbbox((0, 0), test_line, font=font)
    if bbox[2] - bbox[0] <= max_width:
        current_line = test_line
    else:
        if current_line:
            lines.append(current_line)
        current_line = word

if current_line:
    lines.append(current_line)

return lines


def calculate_text_x_position(text_width, canvas_width, padding, alignment):
“”“Calculate X position based on alignment”””
if alignment == “left”:
return padding
elif alignment == “right”:
return canvas_width - text_width - padding
else:  # center
return (canvas_width - text_width) // 2

# =============================================================================

# LOGO POSITIONING (9 POSITIONS)

# =============================================================================

def calculate_logo_position(position, logo_width, logo_height, canvas_width, canvas_height,
padding, safe_top_px, safe_bottom_px):
“””
Calculate logo position based on 9-point grid:


top_left    |  top_centre    |  top_right
------------+----------------+-----------
middle_left |  centre        |  middle_right
------------+----------------+-----------
bottom_left |  bottom_centre |  bottom_right
"""

# Horizontal positions
left_x = padding
centre_x = (canvas_width - logo_width) // 2
right_x = canvas_width - logo_width - padding

# Vertical positions (respecting safe zones)
top_y = safe_top_px + padding
middle_y = (canvas_height - logo_height) // 2
bottom_y = safe_bottom_px - logo_height - padding

positions = {
    # Top row
    "top_left": (left_x, top_y),
    "top_centre": (centre_x, top_y),
    "top_center": (centre_x, top_y),  # US spelling alias
    "top_right": (right_x, top_y),
    
    # Middle row
    "middle_left": (left_x, middle_y),
    "centre": (centre_x, middle_y),
    "center": (centre_x, middle_y),  # US spelling alias
    "middle_right": (right_x, middle_y),
    
    # Bottom row
    "bottom_left": (left_x, bottom_y),
    "bottom_centre": (centre_x, bottom_y),
    "bottom_center": (centre_x, bottom_y),  # US spelling alias
    "bottom_right": (right_x, bottom_y),
}

return positions.get(position, positions["top_left"])


# =============================================================================

# REQUEST MODEL

# =============================================================================

class AdRequest(BaseModel):
background_image_url: str
headline: str
subheadline: Optional[str] = None
cta_text: Optional[str] = “Shop Now”
logo_url: Optional[str] = None
format: Optional[str] = “instagram_feed”


# Colours
primary_color: Optional[str] = "#000000"
secondary_color: Optional[str] = "#FFFFFF"
accent_color: Optional[str] = "#FFD700"
text_color: Optional[str] = "#FFFFFF"

# Positioning - EXPANDED OPTIONS
headline_position: Optional[str] = "bottom"  # top, middle, bottom
text_alignment: Optional[str] = "auto"  # auto, left, center, right (auto detects RTL)

# Logo - 9 POSITION OPTIONS
logo_position: Optional[str] = "top_left"  # top_left, top_centre, top_right, middle_left, centre, middle_right, bottom_left, bottom_centre, bottom_right
logo_background: Optional[str] = None  # none, white, dark, blur
logo_scale: Optional[float] = 1.0  # Scale factor for logo size (0.5 = half, 2.0 = double)

# Overlay
add_overlay: Optional[bool] = True
overlay_opacity: Optional[float] = 0.3

# Fonts
headline_font_url: Optional[str] = None
body_font_url: Optional[str] = None

# Text styling
uppercase_headline: Optional[bool] = True  # Set to False for Arabic (doesn't have uppercase)
uppercase_cta: Optional[bool] = True


# =============================================================================

# API ENDPOINTS

# =============================================================================

@app.get(”/”)
def root():
return {
“status”: “Peach System Creative API v3.0”,
“features”: [
“Arabic text support (RTL, letter shaping)”,
“9-position logo placement”,
“Auto-detect text alignment for RTL languages”,
“Custom font support”,
“Platform-aware safe zones”
],
“formats”: {
“square”: “1080x1080 (Instagram/Facebook Feed)”,
“vertical”: “1080x1920 (Stories/Reels - 20% top, 15% bottom safe)”,
“instagram_feed”: “1080x1080”,
“instagram_story”: “1080x1920 (20% top, 15% bottom safe)”,
“instagram_reel”: “1080x1920 (18% top, 20% bottom safe)”,
“facebook_feed”: “1080x1080”,
“facebook_story”: “1080x1920”,
“facebook_reel”: “1080x1920”,
“facebook_landscape”: “1200x628”,
“tiktok”: “1080x1920 (20% top, 22% bottom safe)”,
},
“endpoints”: [”/generate-ad”, “/health”, “/formats”],
“arabic_support”: ARABIC_SUPPORT
}

@app.get(”/health”)
def health():
return {“status”: “healthy”, “arabic_support”: ARABIC_SUPPORT}

@app.get(”/formats”)
def get_formats():
“”“Return all available format presets with their specifications”””
return {
“formats”: {
name: {
“dimensions”: f”{preset[‘width’]}x{preset[‘height’]}”,
“width”: preset[“width”],
“height”: preset[“height”],
“safe_top_percent”: int(preset[“safe_top”] * 100),
“safe_bottom_percent”: int(preset[“safe_bottom”] * 100),
“safe_top_pixels”: int(preset[“height”] * preset[“safe_top”]),
“safe_bottom_pixels”: int(preset[“height”] * preset[“safe_bottom”]),
“aspect”: preset.get(“aspect”, “unknown”)
}
for name, preset in FORMAT_PRESETS.items()
},
“recommended”: {
“instagram_facebook_feed”: “square”,
“stories”: “vertical”,
“reels”: “reel”,
“tiktok”: “tiktok”
}
}

@app.post(”/generate-ad”)
async def generate_ad(request: AdRequest):
try:
# Get format settings
format_settings = FORMAT_PRESETS.get(request.format, FORMAT_PRESETS[“instagram_feed”])
canvas_width = format_settings[“width”]
canvas_height = format_settings[“height”]
safe_top = format_settings[“safe_top”]
safe_bottom = format_settings[“safe_bottom”]


    # Download background image
    try:
        response = requests.get(request.background_image_url, timeout=30)
        response.raise_for_status()
        background = Image.open(BytesIO(response.content)).convert("RGBA")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download background image: {str(e)}")
    
    # Resize background to fill canvas (cover mode)
    bg_ratio = background.width / background.height
    canvas_ratio = canvas_width / canvas_height
    
    if bg_ratio > canvas_ratio:
        new_height = canvas_height
        new_width = int(canvas_height * bg_ratio)
    else:
        new_width = canvas_width
        new_height = int(canvas_width / bg_ratio)
    
    background = background.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Centre crop to canvas size
    left = (new_width - canvas_width) // 2
    top = (new_height - canvas_height) // 2
    background = background.crop((left, top, left + canvas_width, top + canvas_height))
    
    # Create canvas
    canvas = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))
    canvas.paste(background, (0, 0))
    
    # Add semi-transparent overlay for text readability
    if request.add_overlay:
        overlay = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, int(255 * request.overlay_opacity)))
        canvas = Image.alpha_composite(canvas, overlay)
    
    draw = ImageDraw.Draw(canvas)
    
    # Calculate safe zones
    safe_top_px = int(canvas_height * safe_top)
    safe_bottom_px = int(canvas_height * (1 - safe_bottom))
    content_height = safe_bottom_px - safe_top_px
    padding = int(canvas_width * 0.05)
    
    # Convert colours
    text_color = hex_to_rgb(request.text_color)
    primary_color = hex_to_rgb(request.primary_color)
    accent_color = hex_to_rgb(request.accent_color)
    
    # =================================================================
    # PROCESS TEXT (Arabic support)
    # =================================================================
    
    # Detect if text is RTL
    headline_is_rtl = contains_rtl(request.headline)
    subheadline_is_rtl = contains_rtl(request.subheadline) if request.subheadline else False
    
    # Process Arabic text for proper rendering
    processed_headline = process_arabic_text(request.headline)
    processed_subheadline = process_arabic_text(request.subheadline) if request.subheadline else None
    processed_cta = process_arabic_text(request.cta_text) if request.cta_text else None
    
    # Apply uppercase only for non-Arabic text
    if request.uppercase_headline and not headline_is_rtl:
        processed_headline = processed_headline.upper()
    
    if request.uppercase_cta and request.cta_text and not contains_rtl(request.cta_text):
        processed_cta = processed_cta.upper()
    
    # Determine text alignment
    text_alignment = get_text_alignment(request.headline, request.text_alignment)
    
    # =================================================================
    # CALCULATE FONT SIZES
    # =================================================================
    
    headline_length = len(request.headline)
    if headline_length <= 15:
        headline_size = int(canvas_width * 0.09)
    elif headline_length <= 25:
        headline_size = int(canvas_width * 0.075)
    elif headline_length <= 40:
        headline_size = int(canvas_width * 0.065)
    else:
        headline_size = int(canvas_width * 0.055)
    
    subheadline_size = int(canvas_width * 0.055)
    cta_size = int(canvas_width * 0.04)
    
    # =================================================================
    # LOAD FONTS
    # =================================================================
    
    if request.headline_font_url:
        headline_font_path = download_custom_font(request.headline_font_url, "headline")
        if headline_font_path:
            headline_font = ImageFont.truetype(headline_font_path, headline_size)
        else:
            headline_font = get_font(headline_size, bold=True)
    else:
        headline_font = get_font(headline_size, bold=True)
    
    if request.body_font_url:
        body_font_path = download_custom_font(request.body_font_url, "body")
        if body_font_path:
            subheadline_font = ImageFont.truetype(body_font_path, subheadline_size)
            cta_font = ImageFont.truetype(body_font_path, cta_size)
        else:
            subheadline_font = get_font(subheadline_size, bold=True)
            cta_font = get_font(cta_size, bold=True)
    else:
        subheadline_font = get_font(subheadline_size, bold=True)
        cta_font = get_font(cta_size, bold=True)
    
    # =================================================================
    # CALCULATE TEXT POSITIONING
    # =================================================================
    
    if request.headline_position == "top":
        text_y_start = safe_top_px + padding
    elif request.headline_position == "middle":
        text_y_start = safe_top_px + (content_height // 3)
    else:  # bottom
        text_y_start = safe_bottom_px - int(content_height * 0.45)
    
    max_text_width = canvas_width - (padding * 2)
    
    # =================================================================
    # DRAW HEADLINE
    # =================================================================
    
    headline_lines = wrap_text(draw, processed_headline, headline_font, max_text_width, headline_is_rtl)
    
    current_y = text_y_start
    for line in headline_lines:
        text_width, text_height = get_text_size(draw, line, headline_font)
        x = calculate_text_x_position(text_width, canvas_width, padding, text_alignment)
        draw_text_with_shadow(draw, (x, current_y), line, headline_font, text_color, shadow_offset=3, shadow_opacity=60)
        current_y += text_height + 15
    
    # =================================================================
    # DRAW SUBHEADLINE
    # =================================================================
    
    if processed_subheadline:
        current_y += 15
        sub_alignment = get_text_alignment(request.subheadline, request.text_alignment)
        subheadline_lines = wrap_text(draw, processed_subheadline, subheadline_font, max_text_width, subheadline_is_rtl)
        
        for line in subheadline_lines:
            text_width, text_height = get_text_size(draw, line, subheadline_font)
            x = calculate_text_x_position(text_width, canvas_width, padding, sub_alignment)
            draw_text_with_shadow(draw, (x, current_y), line, subheadline_font, text_color, shadow_offset=2, shadow_opacity=50)
            current_y += text_height + 8
    
    # =================================================================
    # DRAW CTA BUTTON
    # =================================================================
    
    if processed_cta:
        cta_width, cta_height = get_text_size(draw, processed_cta, cta_font)
        
        button_padding_x = 50
        button_padding_y = 25
        button_width = cta_width + button_padding_x * 2
        button_height = cta_height + button_padding_y * 2
        
        button_x = (canvas_width - button_width) // 2
        button_y = current_y + 30
        
        # Draw button background
        draw_rounded_rectangle(
            draw,
            [button_x, button_y, button_x + button_width, button_y + button_height],
            radius=button_height // 2,
            fill=accent_color + (255,)
        )
        
        # Draw button text - centred
        text_x = button_x + (button_width - cta_width) // 2
        text_y = button_y + (button_height - cta_height) // 2 - int(cta_height * 0.15)
        draw.text((text_x, text_y), processed_cta, font=cta_font, fill=primary_color)
    
    # =================================================================
    # ADD LOGO (9-POSITION SUPPORT)
    # =================================================================
    
    if request.logo_url:
        try:
            logo_response = requests.get(request.logo_url, timeout=15)
            logo_response.raise_for_status()
            logo = Image.open(BytesIO(logo_response.content)).convert("RGBA")
            
            # Calculate logo size based on format
            if request.format in ["instagram_feed", "facebook_feed"]:
                logo_max_width = int(canvas_width * 0.35)
                logo_max_height = int(canvas_height * 0.15)
            else:
                logo_max_width = int(canvas_width * 0.30)
                logo_max_height = int(canvas_height * 0.10)
            
            # Apply scale factor
            logo_max_width = int(logo_max_width * request.logo_scale)
            logo_max_height = int(logo_max_height * request.logo_scale)
            
            logo_ratio = logo.width / logo.height
            if logo.width > logo_max_width:
                new_width = logo_max_width
                new_height = int(logo_max_width / logo_ratio)
            else:
                new_width = logo.width
                new_height = logo.height
            
            if new_height > logo_max_height:
                new_height = logo_max_height
                new_width = int(logo_max_height * logo_ratio)
            
            logo = logo.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Calculate position using 9-point grid
            logo_x, logo_y = calculate_logo_position(
                request.logo_position,
                new_width,
                new_height,
                canvas_width,
                canvas_height,
                padding,
                safe_top_px,
                safe_bottom_px
            )
            
            # Add logo background if requested
            if request.logo_background:
                bg_padding = 15
                if request.logo_background == "white":
                    bg_color = (255, 255, 255, 230)
                elif request.logo_background == "dark":
                    bg_color = (0, 0, 0, 180)
                elif request.logo_background == "blur":
                    bg_color = (255, 255, 255, 120)
                    bg_padding = 25
                else:
                    bg_color = None
                
                if bg_color:
                    bg_layer = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
                    bg_draw = ImageDraw.Draw(bg_layer)
                    draw_rounded_rectangle(
                        bg_draw,
                        [logo_x - bg_padding, logo_y - bg_padding,
                         logo_x + new_width + bg_padding, logo_y + new_height + bg_padding],
                        radius=15,
                        fill=bg_color
                    )
                    canvas = Image.alpha_composite(canvas, bg_layer)
            
            # Paste logo with transparency
            canvas.paste(logo, (logo_x, logo_y), logo)
            
        except Exception as e:
            print(f"Logo processing failed: {e}")
    
    # =================================================================
    # FINALISE AND RETURN
    # =================================================================
    
    final_image = canvas.convert("RGB")
    
    buffer = BytesIO()
    final_image.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return {
        "success": True,
        "image_base64": image_base64,
        "format": request.format,
        "dimensions": f"{canvas_width}x{canvas_height}",
        "text_direction": "rtl" if headline_is_rtl else "ltr",
        "arabic_processed": headline_is_rtl and ARABIC_SUPPORT
    }
    
except HTTPException:
    raise
except Exception as e:
    raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")


if *name* == “*main*”:
import uvicorn
uvicorn.run(app, host=“0.0.0.0”, port=8000)
