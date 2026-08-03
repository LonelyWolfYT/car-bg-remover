import io
import os
import requests
import numpy as np
from PIL import Image
import cv2
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FiveM Car Background Remover API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def remove_green_screen_background(pil_image: Image.Image) -> Image.Image:
    """
    Ultra-lightweight high-speed Chroma Key Green Screen removal & spill reduction.
    Uses ~30MB RAM (Perfect for Render Free Tier).
    """
    img_rgba = pil_image.convert("RGBA")
    np_img = np.array(img_rgba)
    
    # Extract channels
    r = np_img[:, :, 0].astype(np.int16)
    g = np_img[:, :, 1].astype(np.int16)
    b = np_img[:, :, 2].astype(np.int16)
    
    # Convert to HSV color space for accurate green detection
    rgb_bgr = cv2.cvtColor(np_img[:, :, :3], cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2HSV)
    
    # Define green screen HSV boundaries (bright neon green studio screen)
    lower_green = np.array([35, 45, 45])
    upper_green = np.array([85, 255, 255])
    
    green_mask = cv2.inRange(hsv, lower_green, upper_green)
    
    # Smooth edges using Gaussian Blur on the mask
    mask_blurred = cv2.GaussianBlur(green_mask, (5, 5), 0)
    
    # Calculate transparency alpha (0 = transparent, 255 = opaque)
    alpha = 255 - mask_blurred
    np_img[:, :, 3] = alpha
    
    # Remove green spill / reflections cast onto car paint specular highlights
    green_spill = (g > r) & (g > b) & (np_img[:, :, 3] > 50)
    np_img[green_spill, 1] = np.maximum(r[green_spill], b[green_spill])
    
    return Image.fromarray(np_img, "RGBA")

def crop_transparent_padding(pil_image: Image.Image, padding: int = 20) -> Image.Image:
    """
    Crops empty transparent padding so the car fills the image cleanly.
    """
    bbox = pil_image.getbbox()
    if not bbox:
        return pil_image
    
    left, upper, right, lower = bbox
    width, height = pil_image.size
    
    left = max(0, left - padding)
    upper = max(0, upper - padding)
    right = min(width, right + padding)
    lower = min(height, lower + padding)
    
    return pil_image.crop((left, upper, right, lower))

@app.get("/")
def read_root():
    return {"status": "online", "service": "FiveM Car Background Remover API"}

@app.get("/healthz")
def health_check():
    return {"status": "healthy"}

@app.post("/process-car")
async def process_car_image(
    file: UploadFile = File(None),
    files: UploadFile = File(None),
    webhook: str = Form(None),
    model: str = Form("Vehicle"),
    player: str = Form("Player")
):
    try:
        upload_file = file or files
        if not upload_file:
            raise HTTPException(status_code=400, detail="No screenshot image uploaded")

        contents = await upload_file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        input_image = Image.open(io.BytesIO(contents))
        
        # 1. Remove Green Screen Background
        transparent_car = remove_green_screen_background(input_image)
        
        # 2. Auto-crop surrounding empty space
        final_image = crop_transparent_padding(transparent_car, padding=15)
        
        # Save output image to memory buffer
        img_byte_arr = io.BytesIO()
        final_image.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)
        
        # 3. Upload transparent PNG to Discord Webhook
        target_webhook = webhook or os.getenv("DISCORD_WEBHOOK_URL")
        webhook_status = False
        
        if target_webhook and target_webhook.startswith("http"):
            filename = f"{model.upper()}_transparent.png"
            
            payload = {
                "embeds": [
                    {
                        "title": f"🚗 Vehicle Image: {model.upper()}",
                        "description": f"Transparent PNG image created for **{model}**.\nRequested by player: `{player}`",
                        "color": 3447003,
                        "image": {"url": f"attachment://{filename}"},
                        "footer": {"text": "FiveM Car BG Remover | Antigravity"}
                    }
                ]
            }
            
            files_dict = {
                'file': (filename, img_byte_arr.getvalue(), 'image/png'),
                'payload_json': (None, requests.compat.json.dumps(payload), 'application/json')
            }
            
            resp = requests.post(target_webhook, files=files_dict)
            if resp.status_code in [200, 204]:
                webhook_status = True
            else:
                print(f"[ERROR] Discord Webhook Failed: {resp.status_code} - {resp.text}")

        return JSONResponse(content={
            "success": True,
            "model": model,
            "webhook_sent": webhook_status,
            "message": "Car transparent PNG created and uploaded to Discord!"
        })

    except Exception as e:
        print(f"[ERROR] Processing exception: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
