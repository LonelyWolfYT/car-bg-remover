import io
import os
import requests
import numpy as np
from PIL import Image
import cv2
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from rembg import remove, new_session

app = FastAPI(title="FiveM Car Background Remover API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy initialize rembg session to allow instant server startup & port binding
rembg_session = None

def get_rembg_session():
    global rembg_session
    if rembg_session is None:
        rembg_session = new_session("u2net")
    return rembg_session

def clean_green_chroma_and_spill(pil_image: Image.Image) -> Image.Image:
    """
    Cleans up green screen chroma background and green spill reflections on vehicle body.
    """
    img_np = np.array(pil_image.convert("RGBA"))
    r, g, b, a = img_np[:, :, 0], img_np[:, :, 1], img_np[:, :, 2], img_np[:, :, 3]
    
    # Convert RGB to HSV to locate green screen mask
    rgb = img_np[:, :, :3]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    
    # Define green screen HSV range (bright neon green)
    lower_green = np.array([35, 50, 50])
    upper_green = np.array([85, 255, 255])
    
    green_mask = cv2.inRange(hsv, lower_green, upper_green)
    
    # Set alpha to 0 for green screen pixels
    img_np[green_mask > 0, 3] = 0
    
    # Desaturate minor green spill on semi-transparent edge pixels
    green_spill_mask = (g > r) & (g > b) & (img_np[:, :, 3] > 0)
    img_np[green_spill_mask, 1] = np.maximum(img_np[green_spill_mask, 0], img_np[green_spill_mask, 2])

    return Image.fromarray(img_np, "RGBA")

def crop_transparent_padding(pil_image: Image.Image, padding: int = 20) -> Image.Image:
    """
    Crops empty transparent space around the isolated car.
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
        # Support both 'file' and 'files' form key (screenshot-basic uses 'files')
        upload_file = file or files
        if not upload_file:
            raise HTTPException(status_code=400, detail="No screenshot image uploaded")

        contents = await upload_file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        input_image = Image.open(io.BytesIO(contents)).convert("RGBA")
        
        # 1. AI Background Removal using rembg
        removed_bg = remove(input_image, session=get_rembg_session())
        
        # 2. Secondary Green Chroma & Spill Cleaning
        cleaned_image = clean_green_chroma_and_spill(removed_bg)
        
        # 3. Auto-crop tight bounding box around the vehicle
        final_image = crop_transparent_padding(cleaned_image, padding=15)
        
        # Save output image to in-memory bytes buffer
        img_byte_arr = io.BytesIO()
        final_image.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)
        
        # 4. If Discord Webhook URL provided, send transparent PNG to Discord
        target_webhook = webhook or os.getenv("DISCORD_WEBHOOK_URL")
        webhook_status = False
        
        if target_webhook and target_webhook.startswith("http"):
            filename = f"{model.upper()}_transparent.png"
            
            payload = {
                "embeds": [
                    {
                        "title": f"🚗 Vehicle Cutout: {model.upper()}",
                        "description": f"Transparent PNG image generated for vehicle **{model}**.\nRequested by: `{player}`",
                        "color": 3447003, # Hex color (Blue)
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

        img_byte_arr.seek(0)
        return JSONResponse(content={
            "success": True,
            "model": model,
            "webhook_sent": webhook_status,
            "message": "Car image processed and transparent PNG created successfully!"
        })

    except Exception as e:
        print(f"[ERROR] Exception during processing: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
