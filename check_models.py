import google.generativeai as genai
import os
from dotenv import load_dotenv

# Load .env file to get your key
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not found in .env file.")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        
        print("--- Finding all available models for your API key... ---")
        
        # This is the "Call ListModels" step
        for m in genai.list_models():
            # We check if the model supports the 'generateContent' method
            if 'generateContent' in m.supported_generation_methods:
                print(f"Model found: {m.name}")
                
        print("--- End of list ---")

    except Exception as e:
        print(f"An error occurred: {e}")