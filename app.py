import io
import os
import requests
import numpy as np
from PIL import Image
import cv2
from fastapi import FastAPI, File, UploadFile, Form, Query, Header, HTTPException
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
    Advanced Flood-Fill Chroma Keying.
    Preserves 100% of silver, white, chrome & grey car paint highlights,
    while removing connected studio green screen background cleanly.
    """
    img_rgba = pil_image.convert("RGBA")
    np_img = np.array(img_rgba)
    h, w = np_img.shape[:2]

    # Convert RGB to HSV for precise green detection
    rgb = np_img[:, :, :3]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)

    # Neon Green Studio HSV bounds:
    # High Saturation (S >= 80) and High Value (V >= 70) ensures white/silver car paint is NEVER selected
    lower_green = np.array([35, 80, 70])
    upper_green = np.array([85, 255, 255])
    
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    # Flood fill starting from all 4 screen edges to remove connected background only
    # This prevents white/silver car body highlights from being cut out
    flood_mask = np.zeros((h + 2, w + 2), np.uint8)
    green_copy = green_mask.copy()
    
    seed_points = [
        (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
        (w // 2, 0), (0, h // 2), (w - 1, h // 2), (w // 4, 0), (3 * w // 4, 0)
    ]
    
    for seed_x, seed_y in seed_points:
        if green_copy[seed_y, seed_x] > 0:
            cv2.floodFill(green_copy, flood_mask, (seed_x, seed_y), 0, flags=4 | (255 << 8))

    # All flood-filled areas (value 255 in flood_mask) belong to outer background
    bg_mask = (flood_mask[1:-1, 1:-1] == 255)

    # Smooth background mask edges with slight blur to remove sharp jagged pixels
    kernel = np.ones((3, 3), np.uint8)
    bg_mask_uint8 = (bg_mask * 255).astype(np.uint8)
    bg_mask_uint8 = cv2.dilate(bg_mask_uint8, kernel, iterations=1)
    
    # Apply transparency to background pixels only
    np_img[bg_mask_uint8 > 0, 3] = 0

    # Mild green spill cleanup ON CAR EDGES ONLY (where car is visible)
    car_pixels = np_img[:, :, 3] > 0
    r = np_img[:, :, 0].astype(np.int16)
    g = np_img[:, :, 1].astype(np.int16)
    b = np_img[:, :, 2].astype(np.int16)

    # Neutralize extreme green reflections on metallic edges without touching car body paint
    green_spill = car_pixels & (g > r + 35) & (g > b + 35)
    np_img[green_spill, 1] = ((r[green_spill] + b[green_spill]) // 2).astype(np.uint8)

    return Image.fromarray(np_img, "RGBA")

def crop_transparent_padding(pil_image: Image.Image, padding: int = 15) -> Image.Image:
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
    model: str = Form(None),
    player: str = Form(None),
    q_webhook: str = Query(None, alias="webhook"),
    q_model: str = Query(None, alias="model"),
    q_player: str = Query(None, alias="player"),
    x_discord_webhook: str = Header(None),
    x_car_model: str = Header(None),
    x_player_name: str = Header(None)
):
    try:
        target_webhook = x_discord_webhook or q_webhook or webhook or os.getenv("DISCORD_WEBHOOK_URL")
        target_model = x_car_model or q_model or model or "Vehicle"
        target_player = x_player_name or q_player or player or "Player"

        upload_file = file or files
        if not upload_file:
            raise HTTPException(status_code=400, detail="No screenshot image uploaded")

        contents = await upload_file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        input_image = Image.open(io.BytesIO(contents))
        
        # 1. Remove Green Screen Background cleanly preserving white/silver car paint
        transparent_car = remove_green_screen_background(input_image)
        
        # 2. Auto-crop surrounding empty space
        final_image = crop_transparent_padding(transparent_car, padding=15)
        
        img_byte_arr = io.BytesIO()
        final_image.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)
        
        # 3. Upload transparent PNG to Discord Webhook
        webhook_status = False
        
        if target_webhook and target_webhook.startswith("http"):
            filename = f"{target_model.upper()}_transparent.png"
            
            payload = {
                "embeds": [
                    {
                        "title": f"🚗 Vehicle Image: {target_model.upper()}",
                        "description": f"Transparent PNG image created for **{target_model}**.\nRequested by player: `{target_player}`",
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
            "model": target_model,
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
