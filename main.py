from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
from rembg import remove
import requests
from io import BytesIO
import base64

app = FastAPI()

# Ad format presets
FORMATS = {
    "instagram_story": {"width": 1080, "height": 1920, "safe_top": 0.20, "safe_bottom": 0.15},
    "instagram_feed": {"width": 1080, "height": 1080, "safe_top": 0.05, "safe_bottom": 0.05},
    "facebook_feed": {"width": 1200, "height": 628, "safe_top": 0.05, "safe_bottom": 0.05},
    "reels": {"width": 1080, "height": 1920, "safe_top": 0.20, "safe_bottom": 0.25},
}

class AdRequest(BaseModel):
    product_image_url: str
    headline: str = ""
    cta_text: str = "Shop Now"
    brand_color: str = "#FF5733"
    text_color: str = "#FFFFFF"
    format: str = "instagram_feed"
    remove_background: bool = True

@app.get("/")
def root():
    return {"status": "Peach System Ad Generator is running 🍑"}

@app.post("/generate-ad")
def generate_ad(request: AdRequest):
    try:
        # Get format settings
        fmt = FORMATS.get(request.format, FORMATS["instagram_feed"])
        
        # Download product image
        response = requests.get(request.product_image_url)
        product_img = Image.open(BytesIO(response.content)).convert("RGBA")
        
        # Remove background if requested
        if request.remove_background:
            product_img = remove(product_img)
        
        # Create branded background
        background = Image.new("RGBA", (fmt["width"], fmt["height"]), request.brand_color)
        
        # Resize product to fit (60% of width)
        product_width = int(fmt["width"] * 0.6)
        ratio = product_width / product_img.width
        product_height = int(product_img.height * ratio)
        product_img = product_img.resize((product_width, product_height), Image.LANCZOS)
        
        # Center product
        x = (fmt["width"] - product_width) // 2
        y = (fmt["height"] - product_height) // 2
        
        # Paste product onto background
        background.paste(product_img, (x, y), product_img)
        
        # Add text
        draw = ImageDraw.Draw(background)
        
        # Try to load font, fallback to default
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        except:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Add headline at top (in safe zone)
        if request.headline:
            headline_y = int(fmt["height"] * fmt["safe_top"] * 0.3)
            draw.text((fmt["width"]//2, headline_y), request.headline, 
                     fill=request.text_color, font=font_large, anchor="mt")
        
        # Add CTA button at bottom
        cta_y = int(fmt["height"] * (1 - fmt["safe_bottom"] * 0.7))
        button_width = 300
        button_height = 60
        button_x = (fmt["width"] - button_width) // 2
        
        # Draw button
        draw.rounded_rectangle(
            [button_x, cta_y, button_x + button_width, cta_y + button_height],
            radius=30,
            fill=request.text_color
        )
        
        # Add CTA text
        draw.text((fmt["width"]//2, cta_y + button_height//2), request.cta_text,
                 fill=request.brand_color, font=font_small, anchor="mm")
        
        # Convert to bytes
        img_bytes = BytesIO()
        background.convert("RGB").save(img_bytes, format="PNG")
        img_bytes.seek(0)
        
        # Return base64 encoded image
        img_base64 = base64.b64encode(img_bytes.getvalue()).decode()
        
        return {
            "success": True,
            "image_base64": img_base64,
            "format": request.format,
            "dimensions": f"{fmt['width']}x{fmt['height']}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/formats")
def get_formats():
    return FORMATS
