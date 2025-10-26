import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import io

# --- CONFIGURATION ---
# 1. Paste your bot's TOKEN here
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN_HERE" 

# 2. Paste your Codespace API URL here. 
#    (It's the one that showed '{"status":"MicroSmart API is running!"}')
#    Make sure it ends with '/analyze/blood'
API_URL = "https://infamous-hobgoblin-jx9vgvvrjv52qrwx-8000.app.github.dev/analyze/blood"
# ---------------------


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "Hello! I am the MicroSmart AI assistant. 🔬\n\n"
        "Send me a picture of a blood smear, and I will analyze it for you."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles when a user sends a photo."""
    
    # Let the user know you've received the image
    await update.message.reply_text("Processing your image, please wait... ⏳")
    
    # 1. Get the photo file from Telegram (we take the highest resolution)
    try:
        photo_file = await update.message.photo[-1].get_file()
    except Exception as e:
        print(f"Error getting file: {e}")
        await update.message.reply_text("Sorry, I had trouble downloading your image. Please try again.")
        return

    # 2. Download the photo as a byte stream in memory
    file_bytes_io = io.BytesIO()
    await photo_file.download_to_memory(file_bytes_io)
    file_bytes_io.seek(0) # Go to the beginning of the stream
    
    # 3. Prepare the file to send to the API
    #    The API is expecting a file named 'file'
    files_to_send = {'file': ('user_image.jpg', file_bytes_io, 'image/jpeg')}
    
    try:
        # 4. Send the file to your API and set a timeout
        response = requests.post(API_URL, files=files_to_send, timeout=60) # 60 sec timeout
        
        if response.status_code == 200:
            # 5. Format the JSON data from the API into a nice report
            data = response.json()
            counts = data.get('counts', {})
            flags = data.get('flags', [])
            
            # Use Markdown for formatting
            report = "🔬 *Analysis Report* 🔬\n\n"
            report += "*Cell Counts:*\n"
            report += f"  - Red Blood Cells: *{counts.get('RBC', 0)}*\n"
            report += f"  - White Blood Cells: *{counts.get('WBC', 0)}*\n"
            report += f"  - Platelets: *{counts.get('Platelet', 0)}*\n\n"
            
            if flags:
                report += "⚠️ *Potential Flags:*\n"
                for flag in flags:
                    report += f"  - {flag}\n"
            else:
                report += "✅ *No immediate issues flagged.*"
                
            await update.message.reply_text(report, parse_mode="Markdown")
            
        else:
            # Handle errors from the API server
            await update.message.reply_text(f"Sorry, the analysis server returned an error (Code: {response.status_code}). Please try again.")

    except requests.exceptions.Timeout:
        await update.message.reply_text("The analysis is taking too long and timed out. Please try again with a clearer or smaller image.")
    except requests.exceptions.RequestException as e:
        # Handle network errors
        print(f"Error connecting to API: {e}")
        await update.message.reply_text("Error: Could not connect to the analysis server. Please tell the admin.")

def main():
    """Starts the bot."""
    print("Bot is starting...")
    
    # Create the Application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image)) # Listens for photos

    # Start the bot
    print("Bot is polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()