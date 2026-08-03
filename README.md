# FiveM Car Background Remover - Python Web API & Hosting Guide

This Python Web API receives screenshots taken from FiveM via `/carpic`, automatically isolates the car, removes the green screen background & HUD elements, crops the transparent PNG, and uploads it to your Discord Webhook.

---

## Free Hosting Options

### Option 1: Deploy on Render.com (Recommended - 100% Free)

1. Create a free account on [Render.com](https://render.com).
2. Create a new GitHub repository and push the contents of the `python_api` folder (`app.py`, `requirements.txt`, `Dockerfile`) to it.
3. On Render Dashboard:
   - Click **New +** -> **Web Service**.
   - Connect your GitHub repository.
   - Select **Docker** as the Runtime (it will automatically use the `Dockerfile`).
   - Choose the **Free** instance plan.
   - Click **Create Web Service**.
4. Once deployed, copy your Render Web Service URL (e.g. `https://car-bg-remover.onrender.com`).
5. Open `lw-carbgremover/config.lua` in your FiveM server resources:
   ```lua
   Config.PythonApiUrl = "https://car-bg-remover.onrender.com/process-car"
   ```

---

### Option 2: Deploy on Hugging Face Spaces (Free)

1. Create a free account on [HuggingFace.co](https://huggingface.co).
2. Go to **Spaces** -> **Create new Space**.
3. Choose **Docker** as the SDK (Blank / Dockerfile).
4. Upload `app.py`, `requirements.txt`, `Dockerfile`.
5. Hugging Face will build and host your API for free.
6. Use your Hugging Face Space URL + `/process-car` in `config.lua`.

---

### Option 3: Run Locally or on VPS (For Testing)

1. Make sure Python 3.10+ is installed.
2. Open terminal in the `python_api` directory:
   ```bash
   pip install -r requirements.txt
   python app.py
   ```
3. The API will start at `http://localhost:5000`.
4. Update `config.lua`:
   ```lua
   Config.PythonApiUrl = "http://localhost:5000/process-car"
   ```
   *(Note: For remote FiveM players, use your server IP or ngrok/domain URL instead of localhost)*

---

## FiveM Usage

1. Start `screenshot-basic` in your `server.cfg`:
   ```cfg
   ensure screenshot-basic
   ensure lw-carbgremover
   ```
2. Set your Discord Webhook URL in `lw-carbgremover/config.lua`.
3. In game, type:
   ```
   /carpic t20
   ```
   or any car model name (e.g. `/carpic adder`, `/carpic zentorno`).
4. The car will spawn at the green screen location `(11.7221, 712.6237, 342.3886)`, take a picture, send it to the Python API, remove the background, and deliver the transparent PNG to your Discord Webhook!
