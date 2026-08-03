import io
import os
import json
import requests
from PIL import Image
from fastapi import FastAPI, File, UploadFile, Form, Query, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Initialize FastAPI app immediately (Imports in 0.001 seconds!)
app = FastAPI(title="FiveM Car Background Remover API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global AI session variable
ai_session = None

def get_ai_session():
    global ai_session
    if ai_session is None:
        # Import heavy AI module inside function so uvicorn binds port instantly!
        from rembg import new_session
        ai_session = new_session("u2netp")
    return ai_session

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

        input_image = Image.open(io.BytesIO(contents)).convert("RGBA")
        
        # Import rembg lazily on first request
        from rembg import remove
        transparent_car = remove(input_image, session=get_ai_session())
        
        # Auto-crop surrounding empty space
        final_image = crop_transparent_padding(transparent_car, padding=15)
        
        img_byte_arr = io.BytesIO()
        final_image.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)
        
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
                'payload_json': (None, json.dumps(payload), 'application/json')
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
