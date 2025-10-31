import os
import uvicorn
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, Body
from ultralytics import YOLO
import io
import requests
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

# --- Configuration ---
BLUR_THRESHOLD = 100.0
HARMONIZE_SIZE = (640, 640)

# !! NEW: Clinical Conversion Factor !!
# This is an estimation. We assume a 100x oil field view.
# Example: 10 WBCs/field * 2000 = 20,000 WBCs/µL or 20.0 x 10⁹/L
# We will use this to convert average-per-field to concentration.
WBC_CONVERSION_FACTOR = 2000 
RBC_CONVERSION_FACTOR = 15000 # This is a rough estimate, real RBC counts are done differently
PLATELET_CONVERSION_FACTOR = 15000 # This is a common estimation
# ---------------------

# Load .env file to get the Telegram token
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"httpsfs://api.telegram.org/bot{TELEGRAM_TOKEN}"

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

# --- Helper Function to Download from Telegram ---
async def download_file_from_telegram(file_id: str) -> io.BytesIO:
    """
    Downloads a file from Telegram's servers using its file_id.
    """
    # 1. Get the file_path from Telegram
    get_file_path_url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
    response = requests.get(get_file_path_url)
    if response.status_code != 200:
        print(f"Error getting file path: {response.text}")
        return None
    
    file_path = response.json()['result']['file_path']
    
    # 2. Download the file content
    file_download_url = f"httpsfs://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    file_response = requests.get(file_download_url)
    if file_response.status_code != 200:
        print(f"Error downloading file: {file_response.text}")
        return None
        
    return io.BytesIO(file_response.content)

# --- Pydantic Model for /analyze_batch ---
class BatchRequest(BaseModel):
    file_ids: List[str]

# --- API Endpoints ---

@app.get("/")
def read_root():
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
    NEW: Analyzes a whole batch of images from their Telegram file_ids.
    """
    if not model:
        return {"error": "Model is not loaded. Check server logs."}
    
    file_ids = request.file_ids
    if not file_ids:
        return {"error": "No file_ids provided."}

    total_counts = {name: 0 for name in CLASS_NAMES}
    total_blur_score = 0
    best_image_blur_score = 0
    best_image_plotted = None # We will implement plotting later
    
    # 1. Loop through all file_ids, download, and analyze
    for file_id in file_ids:
        file_bytes_io = await download_file_from_telegram(file_id)
        if not file_bytes_io:
            continue # Skip this image if download failed
            
        contents = file_bytes_io.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            continue

        # 2. Harmonize
        img_harmonized = cv2.resize(img, HARMONIZE_SIZE)

        # 3. Run model
        results = model(img_harmonized)

        # 4. Tally counts
        try:
            for cls_index in results[0].boxes.cls:
                class_name = CLASS_NAMES[int(cls_index)]
                total_counts[class_name] += 1
        except Exception as e:
            print(f"Error processing model results: {e}")
            
        # 5. Check for "best" image (we'll use this for plotting later)
        gray = cv2.cvtColor(img_harmonized, cv2.COLOR_BGR2GRAY)
        blur_value = cv2.Laplacian(gray, cv2.CV_64F).var()
        total_blur_score += blur_value
        if blur_value > best_image_blur_score:
            best_image_blur_score = blur_value
            # best_image_plotted = results[0].plot() # We'll add this in the next phase
    
    num_images = len(file_ids)
    
    # 6. Calculate Averages
    avg_counts = {name: (total_counts[name] / num_images) for name in CLASS_NAMES}
    
    # 7. !! NEW: Calculate Final Concentration !!
    wbc_concentration = (avg_counts['WBC'] * WBC_CONVERSION_FACTOR) / 1000 # To get 10^9/L
    rbc_concentration = (avg_counts['RBC'] * RBC_CONVERSION_FACTOR) / 1000000 # To get 10^12/L
    plt_concentration = (avg_counts['Platelet'] * PLATELET_CONVERSION_FACTOR) / 1000 # To get 10^9/L
    
    # 8. Generate Flags (based on concentration)
    flags = []
    # Note: These ranges are for adults.
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
        "imageCount": num_images,
        "imageQualityReport": {
            "averageBlurScore": total_blur_score / num_images,
            "imagesRejected": 0, # The bot filters rejections, so this is 0
            "rejectionReasons": []
        },
        "bestImage": {
            "file_id": file_ids[0], # Placeholder
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
        "llmSuggestions": [ # For Phase 3
            "What is 'Leukopenia'?",
            "What are the normal ranges for these counts?"
        ]
    }
    
    return report_data


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000)) 
    print(f"Starting API server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)