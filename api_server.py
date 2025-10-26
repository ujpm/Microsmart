import uvicorn
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File
from ultralytics import YOLO
import io

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


@app.post("/analyze/blood")
async def analyze_blood_smear(file: UploadFile = File(...)):
    """
    Receives an image, runs analysis, and returns cell counts.
    """
    if not model:
        return {"error": "Model is not loaded. Check server logs."}

    # 1. Read the image file from the upload
    contents = await file.read()

    # 2. Convert the image data to a format OpenCV can read
    # Using np.frombuffer is more efficient
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"error": "Could not decode image."}

    # 3. Run the model on the image
    results = model(img)

    # 4. Count the results
    counts = {name: 0 for name in CLASS_NAMES} # Initialize counts to 0

    try:
        # results[0].boxes.cls gives a tensor of class indices
        for cls_index in results[0].boxes.cls:
            class_name = CLASS_NAMES[int(cls_index)]
            counts[class_name] += 1
    except Exception as e:
        return {"error": f"Failed to process model results: {e}"}

    # 5. Create a report and flags (you can make these rules smarter later)
    flags = []
    wbc_count = counts.get('WBC', 0)
    platelet_count = counts.get('Platelet', 0)

    if wbc_count > 15: # Example: High WBC count
        flags.append(f"Potential Leukocytosis (High WBC count: {wbc_count}).")
    if wbc_count < 3: # Example: Low WBC count
        flags.append(f"Potential Leukopenia (Low WBC count: {wbc_count}).")
    if platelet_count < 10: # Example: Low platelet count
         flags.append(f"Potential Thrombocytopenia (Low Platelet count: {platelet_count}).")

    # 6. Return the final JSON response
    return {
        "counts": counts,
        "flags": flags,
        "report": "Analysis complete."
    }


if __name__ == "__main__":
    # Runs the server on port 8000, accessible from anywhere
    print("Starting API server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)