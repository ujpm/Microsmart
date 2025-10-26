import requests
import io
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup  # <-- NEW
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler  # <-- NEW
)

# Load variables from your .env file
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_URL = os.getenv("API_URL")

# --- URL & Text Configuration ---

LEARN_MORE_URL = "https://portifolio-cgu.pages.dev/"
CONTRIBUTE_URL = "https://github.com/ujpm/"

# Check if the variables are loaded
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found! Check your .env file.")
if not API_URL:
    raise ValueError("API_URL not found! Check your .env file.")

# --- NEW: /start command handler ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command with the new welcome message and buttons."""
    
    welcome_text = """
Hello! Welcome to **MicroSmart** 🔬

(This project was started by a frustrated lab tech... just saying.)

I'm your AI-powered microscopy sidekick, here to give you **lightning-fast preliminary analysis** of those *pesky* microscopic samples.


**🚧 Status: v1.0 "The Blood Analyst"**

I've mastered blood smears (for now)! Upload a clear photo and I'll:
* Count Red Blood Cells, White Blood Cells & Platelets.
* Flag anything that looks suspicious (like high/low counts).
* *Try* not to judge your microscope photography skills. 😉


**🔮 The Grand Vision**

My training never stops! Soon I'll be learning to tackle:
* **Stool samples** (parasite egg hunt 🪱)
* **Urine sediment** (the great crystal hunt 💎)
* **Gram stains** (bacterial party identification 🦠)


**🤝 Join the Revolution!**

This is an open-source mission to make lab work less tedious. We're actively looking for collaborators.

Ready to put me to work? Choose an option below!
"""

    # Define the inline buttons
    keyboard = [
        [InlineKeyboardButton("Learn More 🌐", url=LEARN_MORE_URL)],
        [InlineKeyboardButton("Developer 👨‍💻", callback_data="developer_info")],
        [InlineKeyboardButton("Try It Now 🚀", callback_data="try_now")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send the message
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# --- NEW: /analyze command handler ---
async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /analyze command from the menu."""
    await update.message.reply_text(
        "Ready! Please send me a clear, close-up photo of a blood smear."
    )

# --- NEW: /help command handler ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command."""
    await update.message.reply_text(
        "I am MicroSmart v1.0, an AI assistant.\n\n"
        "I can analyze blood smear photos. Use the /analyze command or the 'Try It Now' "
        "button and send me an image. For more info, use /start."
    )

# --- NEW: /feedback command handler ---
async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /feedback command."""
    await update.message.reply_text(
        "We'd love your feedback! To send it, please type:\n"
        "/feedback *followed by your message*.\n\n"
        "Example: `/feedback This bot is amazing!`"
    )

# --- NEW: /contribute command handler ---
async def contribute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /contribute command."""
    await update.message.reply_text(
        f"You can contribute to this project on GitHub:\n{CONTRIBUTE_URL}\n\n"
        "We are also actively looking for data partners! "
        "Please contact the developer at (your-email@example.com) to partner."
    )

# --- NEW: Button Click Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all button clicks from inline keyboards."""
    query = update.callback_query
    await query.answer()  # Acknowledge the button click

    if query.data == "developer_info":
        await query.message.reply_text(
            f"MicroSmart is an open-source project. You can follow its development "
            f"or contribute on GitHub:\n{CONTRIBUTE_URL}"
        )
    elif query.data == "try_now":
        await query.message.reply_text(
            "Great! Please send me a clear, close-up photo of a blood smear."
        )


# --- Image Handler (Unchanged, but with better comments) ---
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles when a user sends a photo for analysis."""
    
    await update.message.reply_text("Processing your image, please wait... ⏳")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
    except Exception as e:
        print(f"Error getting file: {e}")
        await update.message.reply_text("Sorry, I had trouble downloading your image. Please try again.")
        return

    file_bytes_io = io.BytesIO()
    await photo_file.download_to_memory(file_bytes_io)
    file_bytes_io.seek(0)
    
    files_to_send = {'file': ('user_image.jpg', file_bytes_io, 'image/jpeg')}
    
    try:
        response = requests.post(API_URL, files=files_to_send, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            counts = data.get('counts', {})
            flags = data.get('flags', [])
            
            # This is the "basic" report we will polish next (Level 2)
            report = "🔬 *Analysis Report* 🔬\n\n"
            report += "*Cell Counts:*\n"
            report += f"  - Red Blood Cells: *{counts.get('RBC', 0)}*\n"
            report += f"  - White Blood Cells: *{counts.get('WBC', 0)}*\n"
            report += f"  - Platelets: *{counts.get('Platelet', 0)}*\n\n" # Updated to new name
            
            if flags:
                report += "⚠️ *Potential Flags:*\n"
                for flag in flags:
                    report += f"  - {flag}\n"
            else:
                report += "✅ *No immediate issues flagged.*"
                
            await update.message.reply_text(report, parse_mode="Markdown")
            
        else:
            await update.message.reply_text(f"Sorry, the analysis server returned an error (Code: {response.status_code}). Please try again.")

    except requests.exceptions.Timeout:
        await update.message.reply_text("The analysis is taking too long. Please try again.")
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to API: {e}")
        await update.message.reply_text("Error: Could not connect to the analysis server. Please tell the admin.")


def main():
    """Starts the bot."""
    print("Bot is starting...")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # --- UPDATED: Add all new handlers ---
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("contribute", contribute_command))
    
    app.add_handler(CallbackQueryHandler(button_handler)) # Handles button clicks
    app.add_handler(MessageHandler(filters.PHOTO, handle_image)) # Handles photos

    # Error handler (optional but good)
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"Update {update} caused error {context.error}")
    
    app.add_error_handler(error_handler)
    
    print("Bot is polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()