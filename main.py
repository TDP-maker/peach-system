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

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Format presets with safe zones
FORMAT_PRESETS = {
    "instagram_story": {"width": 1080, "height": 1920, "safe_top": 0.15, "safe_bottom": 0.20},
    "instagram_feed": {"width": 1080, "height": 1080, "safe_top": 0.05, "safe_bottom": 0.05},
    "facebook_feed": {"width": 1200, "height": 628, "safe_top": 0.05, "safe_bottom": 0.05},
    "facebook_story": {"width": 1080, "height": 1920, "safe_top": 0.15, "safe_bottom": 0.20},
    "tiktok": {"width": 1080, "height": 1920, "safe_top": 0.20, "safe_bottom": 0.25},
}

# Font URLs - using Google Fonts
FONTS = {
    "bold": "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
    "regular": "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
}

def download_font(font_name="bold"):
    """Download and cache font"""
    font_path = f"/tmp/{font_name}_font.ttf"
    if not os.path.exists(font_path):
        try:
            # Use raw githubusercontent for reliability
            url = "https://raw.githubusercontent.com/googlefonts/Montserrat/main/fonts/ttf/Montserrat-Bold.ttf"
            headers = {'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                with open(font_path, 'wb') as f:
                    f.write(response.read())
        except Exception as e:
            print(f"Font download failed: {e}")
            # Try alternative CDN
            try:
                alt_url = "https://cdn.jsdelivr.net/fontsource/fonts/montserrat@latest/latin-700-normal.ttf"
                req = urllib.request.Request(alt_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    with open(font_path, 'wb') as f:
                        f.write(response.read())
            except Exception as e2:
                print(f"Alt font download also failed: {e2}")
                return None
    return font_path

def download_custom_font(font_url, font_id):
    """Download custom font from URL (e.g., Airtable attachment)"""
    # Use hash of URL to cache different fonts properly
    import hashlib
    url_hash = hashlib.md5(font_url.encode()).hexdigest()[:8]
    font_path = f"/tmp/custom_{font_id}_{url_hash}.ttf"
    
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
    """Download regular weight font"""
    font_path = "/tmp/regular_font.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://raw.githubusercontent.com/googlefonts/Montserrat/main/fonts/ttf/Montserrat-SemiBold.ttf"
            headers = {'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                with open(font_path, 'wb') as f:
                    f.write(response.read())
        except Exception as e:
            print(f"Font download failed: {e}")
            return None
    return font_path

def get_font(size, bold=True, custom_font_url=None):
    """Get font at specified size with proper fallback"""
    
    # If custom font URL provided, download and use it
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
            # Fall through to default fonts
    
    font_path = download_font() if bold else download_font_regular()
    if font_path and os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as e:
            print(f"Font load error: {e}")
    
    # Better fallback - try system fonts
    fallback_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for fallback in fallback_fonts:
        if os.path.exists(fallback):
            try:
                return ImageFont.truetype(fallback, size)
            except:
                continue
    
    # Last resort - default font (will be small but works)
    return ImageFont.load_default()

def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def get_text_size(draw, text, font):
    """Get text bounding box size"""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def draw_text_with_shadow(draw, position, text, font, fill, shadow_color=None, shadow_offset=3, shadow_opacity=80):
    """Draw text with soft shadow for better readability"""
    x, y = position
    
    # If no shadow color specified, use a soft gray (not harsh black)
    if shadow_color is None:
        shadow_color = (60, 60, 60)  # Soft dark gray instead of black
    
    # Draw soft shadow with lower opacity
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color + (shadow_opacity,))
    # Draw main text
    draw.text((x, y), text, font=font, fill=fill)

def draw_rounded_rectangle(draw, coords, radius, fill, outline=None, outline_width=0):
    """Draw a rounded rectangle"""
    x1, y1, x2, y2 = coords
    
    # Draw main rectangle
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
    
    # Draw corners
    draw.ellipse([x1, y1, x1 + radius * 2, y1 + radius * 2], fill=fill)
    draw.ellipse([x2 - radius * 2, y1, x2, y1 + radius * 2], fill=fill)
    draw.ellipse([x1, y2 - radius * 2, x1 + radius * 2, y2], fill=fill)
    draw.ellipse([x2 - radius * 2, y2 - radius * 2, x2, y2], fill=fill)
    
    if outline:
        # Draw outline
        draw.arc([x1, y1, x1 + radius * 2, y1 + radius * 2], 180, 270, fill=outline, width=outline_width)
        draw.arc([x2 - radius * 2, y1, x2, y1 + radius * 2], 270, 360, fill=outline, width=outline_width)
        draw.arc([x1, y2 - radius * 2, x1 + radius * 2, y2], 90, 180, fill=outline, width=outline_width)
        draw.arc([x2 - radius * 2, y2 - radius * 2, x2, y2], 0, 90, fill=outline, width=outline_width)
        draw.line([x1 + radius, y1, x2 - radius, y1], fill=outline, width=outline_width)
        draw.line([x1 + radius, y2, x2 - radius, y2], fill=outline, width=outline_width)
        draw.line([x1, y1 + radius, x1, y2 - radius], fill=outline, width=outline_width)
        draw.line([x2, y1 + radius, x2, y2 - radius], fill=outline, width=outline_width)

class AdRequest(BaseModel):
    background_image_url: str
    headline: str
    subheadline: Optional[str] = None
    cta_text: Optional[str] = "Shop Now"
    logo_url: Optional[str] = None
    font_url: Optional[str] = None  # Custom font .ttf file URL
    format: Optional[str] = "instagram_feed"
    primary_color: Optional[str] = "#000000"
    secondary_color: Optional[str] = "#FFFFFF"
    accent_color: Optional[str] = "#FFD700"
    headline_position: Optional[str] = "bottom"  # top, middle, bottom
    logo_position: Optional[str] = "top_left"  # top_left, top_right, bottom_left, bottom_right
    logo_background: Optional[str] = None  # none, white, dark, blur
    text_color: Optional[str] = "#FFFFFF"
    add_overlay: Optional[bool] = True  # Add dark overlay for text readability
    overlay_opacity: Optional[float] = 0.3
    headline_font_url: Optional[str] = None  # URL to custom headline font (.ttf)
    body_font_url: Optional[str] = None  # URL to custom body font (.ttf)

@app.get("/")
def root():
    return {"status": "Peach System Creative API v2.0", "endpoints": ["/generate-ad", "/health"]}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/generate-ad")
async def generate_ad(request: AdRequest):
    try:
        # Get format settings
        format_settings = FORMAT_PRESETS.get(request.format, FORMAT_PRESETS["instagram_feed"])
        canvas_width = format_settings["width"]
        canvas_height = format_settings["height"]
        safe_top = format_settings["safe_top"]
        safe_bottom = format_settings["safe_bottom"]
        
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
            # Image is wider - fit height, crop width
            new_height = canvas_height
            new_width = int(canvas_height * bg_ratio)
        else:
            # Image is taller - fit width, crop height
            new_width = canvas_width
            new_height = int(canvas_width / bg_ratio)
        
        background = background.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Center crop to canvas size
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
        
        # Convert colors
        text_color = hex_to_rgb(request.text_color)
        primary_color = hex_to_rgb(request.primary_color)
        secondary_color = hex_to_rgb(request.secondary_color)
        accent_color = hex_to_rgb(request.accent_color)
        
        # Calculate font sizes based on canvas - DYNAMIC for headline
        headline_length = len(request.headline)
        if headline_length <= 15:
            headline_size = int(canvas_width * 0.09)  # Short headlines
        elif headline_length <= 25:
            headline_size = int(canvas_width * 0.075)  # Medium headlines
        elif headline_length <= 40:
            headline_size = int(canvas_width * 0.065)  # Longer headlines
        else:
            headline_size = int(canvas_width * 0.055)  # Very long headlines
        
        subheadline_size = int(canvas_width * 0.055)  # 5.5% of width - should be ~60px
        cta_size = int(canvas_width * 0.04)  # CTA button text
        
        # Load fonts - use custom if provided, otherwise default
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
        
        # Calculate text positioning based on headline_position
        if request.headline_position == "top":
            text_y_start = safe_top_px + padding
        elif request.headline_position == "middle":
            text_y_start = safe_top_px + (content_height // 3)
        else:  # bottom
            text_y_start = safe_bottom_px - int(content_height * 0.45)
        
        # Word wrap headline if needed
        def wrap_text(text, font, max_width):
            words = text.split()
            lines = []
            current_line = ""
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
        
        max_text_width = canvas_width - (padding * 2)
        headline_lines = wrap_text(request.headline.upper(), headline_font, max_text_width)
        
        # Draw headline
        current_y = text_y_start
        for line in headline_lines:
            text_width, text_height = get_text_size(draw, line, headline_font)
            x = (canvas_width - text_width) // 2  # Center
            draw_text_with_shadow(draw, (x, current_y), line, headline_font, text_color, shadow_offset=3, shadow_opacity=60)
            current_y += text_height + 15
        
        # Draw subheadline if provided
        if request.subheadline:
            current_y += 15
            subheadline_lines = wrap_text(request.subheadline, subheadline_font, max_text_width)
            for line in subheadline_lines:
                text_width, text_height = get_text_size(draw, line, subheadline_font)
                x = (canvas_width - text_width) // 2
                draw_text_with_shadow(draw, (x, current_y), line, subheadline_font, text_color, shadow_offset=2, shadow_opacity=50)
                current_y += text_height + 8
        
        # Draw CTA button
        if request.cta_text:
            cta_text = request.cta_text.upper()
            cta_width, cta_height = get_text_size(draw, cta_text, cta_font)
            
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
            
            # Draw button text - CENTERED with baseline adjustment
            text_x = button_x + (button_width - cta_width) // 2
            text_y = button_y + (button_height - cta_height) // 2 - int(cta_height * 0.15)
            draw.text((text_x, text_y), cta_text, font=cta_font, fill=primary_color)
        
        # Add logo if provided
        if request.logo_url:
            try:
                logo_response = requests.get(request.logo_url, timeout=15)
                logo_response.raise_for_status()
                logo = Image.open(BytesIO(logo_response.content)).convert("RGBA")
                
                # Resize logo - adjust size based on format
                if request.format in ["instagram_feed", "facebook_feed"]:
                    # Square formats - logo can be bigger, less safe zone needed
                    logo_max_width = int(canvas_width * 0.35)
                    logo_max_height = int(canvas_height * 0.15)
                else:
                    # Story/reel formats - keep logo smaller due to UI overlays
                    logo_max_width = int(canvas_width * 0.30)
                    logo_max_height = int(canvas_height * 0.10)
                
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
                
                # Position logo - adjust for format
                logo_padding = padding
                if request.format in ["instagram_feed", "facebook_feed"]:
                    # Square formats - position closer to edge
                    top_offset = logo_padding
                else:
                    # Story formats - respect safe zone
                    top_offset = safe_top_px + logo_padding
                
                if request.logo_position == "top_left":
                    logo_x, logo_y = logo_padding, top_offset
                elif request.logo_position == "top_right":
                    logo_x, logo_y = canvas_width - new_width - logo_padding, top_offset
                elif request.logo_position == "bottom_left":
                    logo_x, logo_y = logo_padding, safe_bottom_px - new_height - logo_padding
                else:  # bottom_right
                    logo_x, logo_y = canvas_width - new_width - logo_padding, safe_bottom_px - new_height - logo_padding
                
                # Add logo background if requested (for visibility on busy backgrounds)
                if hasattr(request, 'logo_background') and request.logo_background:
                    bg_padding = 10
                    if request.logo_background == "white":
                        bg_color = (255, 255, 255, 200)
                    elif request.logo_background == "dark":
                        bg_color = (0, 0, 0, 150)
                    elif request.logo_background == "blur":
                        # Create soft glow effect
                        bg_color = (255, 255, 255, 100)
                        bg_padding = 20
                    else:
                        bg_color = None
                    
                    if bg_color:
                        # Draw rounded rectangle behind logo
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
        
        # Convert to RGB for JPEG compatibility
        final_image = canvas.convert("RGB")
        
        # Save to bytes
        buffer = BytesIO()
        final_image.save(buffer, format="PNG", quality=95)
        buffer.seek(0)
        
        # Encode to base64
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return {
            "success": True,
            "image_base64": image_base64,
            "format": request.format,
            "dimensions": f"{canvas_width}x{canvas_height}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
