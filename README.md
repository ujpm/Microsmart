# MicroSmart (v1.0) 🔬

MicroSmart is an AI-powered microscope assistant delivered via a Telegram bot. This tool is designed to provide fast, preliminary analysis of microscopic samples.

Version 1.0 is the **Blood Analyst**. It can receive a photo of a blood smear and return a preliminary analysis, including cell counts (RBC, WBC, Platelets) and potential flags for abnormalities.

---

## ⚙️ How It Works (Architecture)

The system is built on a simple, scalable microservice architecture:

1.  **User (Telegram)**: A user sends a photo to the MicroSmart Telegram Bot.
2.  **Telegram Bot (`telegram_bot.py`)**: This Python script (using `python-telegram-bot`) receives the image. It does *not* do any analysis.
3.  **Backend API (`api_server.py`)**: The bot securely forwards the image to a FastAPI backend server.
4.  **AI Model (`model/best.pt`)**: The API server loads a pre-trained YOLOv8 model, performs object detection on the image, and counts the detected cells.
5.  **JSON Report**: The API server returns a `JSON` object with the counts and flags back to the bot.
6.  **Report (Telegram)**: The bot formats this JSON into a user-friendly Markdown report and sends it back to the user in the chat.

---

## 💻 Technology Stack

* **AI Model**: Python, `ultralytics` (YOLOv8), Google Colab (for training).
* **Backend**: Python, `FastAPI`, `uvicorn`.
* **Bot Frontend**: Python, `python-telegram-bot`.
* **Image Processing**: `opencv-python-headless`.
* **Environment**: `python-dotenv` for secure key management.
* **Deployment**: Currently running in GitHub Codespaces.

---

## 🚀 Setup & Running

Here's how to set up and run the MicroSmart v1.0 from scratch.

### 1. Prerequisites

* A trained YOLOv8 model file (`best.pt`).
* A Telegram Bot Token from `@BotFather`.
* Python 3.10+

### 2. Local Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/Microsmart.git](https://github.com/your-username/Microsmart.git)
    cd Microsmart
    ```

2.  **Install System Dependencies:**
    OpenCV requires an underlying system library.
    ```bash
    sudo apt-get update && sudo apt-get install -y libgl1
    ```

3.  **Install Python Libraries:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Add Your Model:**
    Place your trained `best.pt` file into the `/model` directory.

5.  **Create Environment File:**
    Create a file named `.env` in the root directory. Add your secret keys here:
    ```ini
    TELEGRAM_TOKEN=YOUR_BOT_TOKEN_FROM_@BOTFATHER
    API_URL=[http://127.0.0.1:8000/analyze/blood](http://127.0.0.1:8000/analyze/blood)
    ```
    *(Note: This `API_URL` is for running both services on your local machine. See the Codespaces note below for cloud deployment.)*

### 3. How to Run

This system requires **two terminals** to run simultaneously.

1.  **Terminal 1: Start the API Server**
    ```bash
    python api_server.py
    ```
    *You should see `Uvicorn running on http://0.0.0.0:8000`.*

2.  **Terminal 2: Start the Telegram Bot**
    ```bash
    python telegram_bot.py
    ```
    *You should see `Bot is polling for messages...`.*

Now, you can go to your Telegram bot and send it an image to analyze.

---

## ☁️ GitHub Codespaces Deployment

This project is set up to run in GitHub Codespaces. The instructions are almost identical, with two key differences:

1.  **Port Visibility**: When you run `api_server.py`, Codespaces will forward port 8000. You must go to the **"PORTS"** tab, right-click the `8000` port, and set **"Port Visibility"** to **`Public`**.
2.  **`.env` File**: The `API_URL` in your `.env` file must be the **public Codespace URL** provided in the "PORTS" tab. It will look like this:
    ```ini
    API_URL=[https://your-codespace-name-8000.preview.app.github.dev/analyze/blood](https://your-codespace-name-8000.preview.app.github.dev/analyze/blood)
    ```

---

## 🗺️ Future Roadmap

* **Phase 2: Stool Sample Analysis**
    * Train a new model to detect parasite eggs (*Ascaris, Giardia*, etc.).
    * Add a new `/analyze/stool` endpoint to the API.
    * Add a `/stool` command to the bot.
* **Phase 3: Urine Sample Analysis**
    * Train a new model for urine sediment (crystals, casts, cells).
    * Add a new `/analyze/urine` endpoint to the API.
    * Add a `/urine` command to the bot.