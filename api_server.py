import os
import uvicorn
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form
from ultralytics import YOLO
import io

# --- Configuration ---
# You can tune this threshold. Higher means it requires a sharper image.
BLUR_THRESHOLD = 100.0
# The standard size your model was trained on (YOLOv8 default is 640)
HARMONIZE_SIZE = (640, 640) 
# ---------------------

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

@app.get("/")
def read_root():
    """A simple endpoint to check if the server is running."""
    return {"status": "MicroSmart API is running!"}


@app.post("/check_image")
async def check_image_quality(file: UploadFile = File(...)):
    """
    NEW: Checks a single image for quality (harmonization and blur check).
    """
    contents = await file.read()
    
    # 1. Decode the image
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"status": "ERROR", "reason": "Could not decode image."}

    # 2. Harmonization (Resize)
    # We resize *before* checking blur, as blur is relative to image size.
    img_harmonized = cv2.resize(img, HARMONIZE_SIZE)

    # 3. Quality Check (Blur)
    gray = cv2.cvtColor(img_harmonized, cv2.COLOR_BGR2GRAY)
    blur_value = cv2.Laplacian(gray, cv2.CV_64F).var()

    if blur_value < BLUR_THRESHOLD:
        return {
            "status": "ERROR", 
            "reason": f"Image appears too blurry (Score: {blur_value:.2f}). Please refocus."
        }

    return {"status": "OK", "blur_score": blur_value}


@app.post("/analyze/blood")
async def analyze_blood_smear(file: UploadFile = File(...)):
    """
    This is your original endpoint. It will soon be replaced by /analyze_batch,
    but we keep it for now.
    """
    if not model:
        return {"error": "Model is not loaded. Check server logs."}

    # 1. Read and decode the image
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"error": "Could not decode image."}

    # 2. Harmonize (Resize) before sending to model
    img_harmonized = cv2.resize(img, HARMONIZE_SIZE)

    # 3. Run the model on the harmonized image
    results = model(img_harmonized)

    # 4. Count the results
    counts = {name: 0 for name in CLASS_NAMES}
    try:
        for cls_index in results[0].boxes.cls:
            class_name = CLASS_NAMES[int(cls_index)]
            counts[class_name] += 1
    except Exception as e:
        return {"error": f"Failed to process model results: {e}"}

    # 5. Create flags
    flags = []
    wbc_count = counts.get('WBC', 0)
    platelet_count = counts.get('Platelet', 0)

    if wbc_count > 15:
        flags.append(f"Potential Leukocytosis (High WBC count: {wbc_count}).")
    if wbc_count < 3:
        flags.append(f"Potential Leukopenia (Low WBC count: {wbc_count}).")
    if platelet_count < 10:
         flags.append(f"Potential Thrombocytopenia (Low Platelet count: {platelet_count}).")

    # 6. Return the final JSON response
    return {
        "counts": counts,
        "flags": flags,
        "report": "Analysis complete."
    }


if __name__ == "__main__":
    # Get port from environment, default to 8000 for local
    port = int(os.environ.get("PORT", 8000)) 
    print(f"Starting API server on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)