import os
import uvicorn
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Body
from ultralytics import YOLO
import io
import httpx  # <-- NEW: Replaced 'requests'
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

# --- Configuration ---
BLUR_THRESHOLD = 100.0
HARMONIZE_SIZE = (640, 640)
WBC_CONVERSION_FACTOR = 2000 
RBC_CONVERSION_FACTOR = 15000
PLATELET_CONVERSION_FACTOR = 15000
# ---------------------

# Load .env file to get the Telegram token
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# !! FIX: Changed 'httpfs://' to 'https://' !!
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Initialize the FastAPI app
app = FastAPI(title="MicroSmart API")

# Load your trained "brain" from the 'model' folder
try:
    model = YOLO("model/best.pt")
    print("Model loaded successfully!")
except Exception as e:
    print(f"ERROR: Could not load model. {e}")
    model = None

# Define the class names your model knows
CLASS_NAMES = ['RBC', 'WBC', 'Platelet']

# --- NEW: Asynchronous HTTP client ---
# We create a single, reusable client for better performance
client = httpx.AsyncClient()

# --- Helper Function to Download from Telegram (now fully async) ---
async def download_file_from_telegram(file_id: str) -> io.BytesIO:
    """
    Downloads a file from Telegram's servers using its file_id.
    """
    try:
        # 1. Get the file_path from Telegram
        get_file_path_url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
        
        # !! FIX: Use 'await client.get' instead of 'requests.get' !!
        response = await client.get(get_file_path_url, timeout=10)
        
        if response.status_code != 200:
            print(f"Error getting file path: {response.text}")
            return None
        
        file_path = response.json()['result']['file_path']
        
        # 2. Download the file content
        file_download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        
        # !! FIX: Use 'await client.get' !!
        file_response = await client.get(file_download_url, timeout=10)
        
        if file_response.status_code != 200:
            print(f"Error downloading file: {file_response.text}")
            return None
            
        return io.BytesIO(file_response.content)
        
    except httpx.RequestError as e:
        print(f"An error occurred while requesting Telegram API: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error in download_file_from_telegram: {e}")
        return None

# --- Pydantic Model for /analyze_batch ---
class BatchRequest(BaseModel):
    file_ids: List[str]

# --- API Endpoints ---

@app.get("/")
async def read_root():
    """A simple endpoint to check if the server is running."""
    return {"status": "MicroSmart API is running!"}


@app.post("/check_image")
async def check_image_quality(file: UploadFile = File(...)):
    """
    Checks a single image for quality (harmonization and blur check).
    """
    contents = await file.read()
    
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"status": "ERROR", "reason": "Could not decode image."}

    img_harmonized = cv2.resize(img, HARMONIZE_SIZE)
    gray = cv2.cvtColor(img_harmonized, cv2.COLOR_BGR2GRAY)
    blur_value = cv2.Laplacian(gray, cv2.CV_64F).var()

    if blur_value < BLUR_THRESHOLD:
        return {
            "status": "ERROR", 
            "reason": f"Image appears too blurry (Score: {blur_value:.2f}). Please refocus."
        }

    return {"status": "OK", "blur_score": blur_value}


@app.post("/analyze_batch")
async def analyze_batch(request: BatchRequest = Body(...)):
    """
    Analyzes a whole batch of images from their Telegram file_ids.
    """
    if not model:
        return {"error": "Model is not loaded. Check server logs."}
    
    file_ids = request.file_ids
    if not file_ids:
        return {"error": "No file_ids provided."}

    total_counts = {name: 0 for name in CLASS_NAMES}
    total_blur_score = 0
    best_image_blur_score = -1.0
    
    images_processed = 0
    
    # 1. Loop through all file_ids, download, and analyze
    for file_id in file_ids:
        file_bytes_io = await download_file_from_telegram(file_id)
        if not file_bytes_io:
            print(f"Skipping file_id {file_id}, download failed.")
            continue # Skip this image if download failed
            
        contents = file_bytes_io.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            print(f"Skipping file_id {file_id}, could not decode.")
            continue

        images_processed += 1
        img_harmonized = cv2.resize(img, HARMONIZE_SIZE)
        
        # Run model
        results = model(img_harmonized)

        # Tally counts
        try:
            for cls_index in results[0].boxes.cls:
                class_name = CLASS_NAMES[int(cls_index)]
                total_counts[class_name] += 1
        except Exception as e:
            print(f"Error processing model results: {e}")
            
        # Check for "best" image
        gray = cv2.cvtColor(img_harmonized, cv2.COLOR_BGR2GRAY)
        blur_value = cv2.Laplacian(gray, cv2.CV_64F).var()
        total_blur_score += blur_value
        if blur_value > best_image_blur_score:
            best_image_blur_score = blur_value
    
    # 6. Calculate Averages
    if images_processed == 0:
        return {"error": "All images failed to download or decode."}
        
    avg_counts = {name: (total_counts[name] / images_processed) for name in CLASS_NAMES}
    
    # 7. Calculate Final Concentration
    wbc_concentration = (avg_counts['WBC'] * WBC_CONVERSION_FACTOR) / 1000 
    rbc_concentration = (avg_counts['RBC'] * RBC_CONVERSION_FACTOR) / 1000000
    plt_concentration = (avg_counts['Platelet'] * PLATELET_CONVERSION_FACTOR) / 1000 
    
    # 8. Generate Flags
    flags = []
    if wbc_concentration > 11.0:
        flags.append(f"Potential Leukocytosis (High WBC: {wbc_concentration:.1f} x 10⁹/L).")
    if wbc_concentration < 4.5:
        flags.append(f"Potential Leukopenia (Low WBC: {wbc_concentration:.1f} x 10⁹/L).")
    if plt_concentration < 150:
        flags.append(f"Potential Thrombocytopenia (Low Platelet: {plt_concentration:.0f} x 10⁹/L).")
    if plt_concentration > 450:
        flags.append(f"Potential Thrombocytosis (High Platelet: {plt_concentration:.0f} x 10⁹/L).")

    # 9. Build the Rich JSON Report
    report_data = {
        "sessionId": f"session_{os.urandom(4).hex()}",
        "imageCount": images_processed,
        "imageQualityReport": {
            "averageBlurScore": total_blur_score / images_processed,
            "imagesRejected": len(file_ids) - images_processed, 
            "rejectionReasons": [] # Bot handles this, but API could add more
        },
        "bestImage": {
            "file_id": file_ids[0], 
            "reason": "This feature is coming soon."
        },
        "aggregatedAnalysis": {
            "averageCountsPerField": avg_counts,
            "finalConcentrations": {
                "WBC_x10e9_L": f"{wbc_concentration:.1f}",
                "RBC_x10e12_L": f"{rbc_concentration:.2f}",
                "PLT_x10e9_L": f"{plt_concentration:.0f}"
            }
        },
        "flags": flags,
        "llmSuggestions": [
            "What is 'Leukopenia'?",
            "What are the normal ranges for these counts?"
        ]
    }
    
    return report_data

# On shutdown, close the HTTP client
@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000)) 
    print(f"Starting API server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)