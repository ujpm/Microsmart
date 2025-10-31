import requests
import io
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler  # <-- NEW: For multi-step sessions
)

# Load variables from your .env file
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_URL_ANALYZE = os.getenv("API_URL")  # Renamed for clarity
API_URL_CHECK = os.getenv("API_URL_CHECK") # <-- NEW: URL for quality check

# --- URL & Text Configuration ---
LEARN_MORE_URL = "https://portifolio-cgu.pages.dev/"
CONTRIBUTE_URL = "https://github.com/ujpm/"

# --- NEW: Conversation States ---
# We define states to track where the user is in the conversation
UPLOADING_IMAGES, Q_AND_A = range(2)

# Check if the variables are loaded
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found! Check your .env file.")
if not API_URL_ANALYZE:
    raise ValueError("API_URL not found! Check your .env file.")
if not API_URL_CHECK:
    raise ValueError("API_URL_CHECK not found! Check your .env file.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    welcome_text = """
Hello! Welcome to **MicroSmart** 🔬

(This project was started by a frustrated lab tech... just saying.)

I'm your AI-powered microscopy sidekick, here to give you **lightning-fast preliminary analysis** of those *pesky* microscopic samples.

Ready to put me to work? Choose an option below!
"""
    keyboard = [
        [InlineKeyboardButton("Learn More 🌐", url=LEARN_MORE_URL)],
        [InlineKeyboardButton("Developer 👨‍💻", callback_data="developer_info")],
        [InlineKeyboardButton("Try It Now 🚀", callback_data="start_analysis")] # Changed to start analysis
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        # Handle case where /start is pressed mid-conversation
        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

# --- NEW: Start of the analysis session ---
async def start_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    STARTS the ConversationHandler.
    Asks the user to start uploading images.
    """
    # Clear any old data
    context.user_data['image_batch'] = []
    
    text = """
Starting a new blood smear analysis...

For best results, **100x oil immersion** images are recommended.

Please upload **5-10 clear photos** from different fields.
Press **DONE** when you are finished.
"""
    keyboard = [
        [InlineKeyboardButton("How to take a good photo 📸", callback_data="show_tutorial")],
        [InlineKeyboardButton("DONE (0 images)", callback_data="analysis_done")],
        [InlineKeyboardButton("Cancel Analysis", callback_data="analysis_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # If user clicked a button (like "Try It Now")
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else: # If user sent /analyze command
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    return UPLOADING_IMAGES # This tells ConversationHandler to move to the 'UPLOADING_IMAGES' state

# --- NEW: Handler for "How to take a good photo" ---
async def show_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows a helper message with tips."""
    text = """
**Tips for a Great Analysis:**
1.  **Use 100x Oil Immersion:** Our calculations assume this magnification.
2.  **Find the Monolayer:** Analyze the 'feathered edge' where cells are in a single, even layer.
3.  **Focus is Key:** Ensure cells are sharp and clear. This is the #1 reason for rejection.
4.  **Clean Lens:** A smudge can look like a platelet clump!
"""
    # Answer the button click
    await update.callback_query.answer(text, show_alert=True)
    return UPLOADING_IMAGES # Stay in the same state

# --- NEW: The main image upload loop ---
async def handle_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles all photos sent *during* the UPLOADING_IMAGES state.
    Will call the /check_image API.
    """
    photo_file = await update.message.photo[-1].get_file()
    
    # Download photo to memory
    file_bytes_io = io.BytesIO()
    await photo_file.download_to_memory(file_bytes_io)
    file_bytes_io.seek(0)
    
    files_to_send = {'file': ('user_image.jpg', file_bytes_io, 'image/jpeg')}
    
    # --- Real API Quality Check ---
    try:
        response = requests.post(API_URL_CHECK, files=files_to_send, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK":
                # Add the file_id (a string) to our batch list
                context.user_data['image_batch'].append(photo_file.file_id)
                
                num_images = len(context.user_data['image_batch'])
                text = f"✅ Image {num_images} received. For best results, we recommend 5-10 photos.\n\nPress **DONE** to analyze the **{num_images}** image(s) sent so far."
                
            else: # API returned an error
                reason = data.get("reason", "Unknown error")
                num_images = len(context.user_data['image_batch'])
                text = f"❌ Image rejected: **{reason}**\n\n**Tip:** Please try a different photo. Press **DONE** to analyze the **{num_images}** image(s) you've sent, or **Cancel**."
        
        else:
            text = f"❌ Image upload failed. The server returned an error (Code: {response.status_code}). Please try again."

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to check_image API: {e}")
        text = "❌ Error: Could not connect to the analysis server. Please tell the admin."
    
    # --- Update the buttons ---
    num_images = len(context.user_data['image_batch'])
    keyboard = [
        [InlineKeyboardButton(f"DONE ({num_images} images)", callback_data="analysis_done")],
        [InlineKeyboardButton("Cancel Analysis", callback_data="analysis_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    return UPLOADING_IMAGES # Stay in the loop

# --- NEW: Handle the "DONE" button press ---
async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User is finished uploading. Run the analysis.
    """
    await update.callback_query.answer()
    
    image_batch = context.user_data.get('image_batch', [])
    
    if not image_batch:
        await update.callback_query.message.reply_text("You haven't sent any clear photos yet! Please send a photo or press Cancel.")
        return UPLOADING_IMAGES

    # --- Analysis Logic ---
    # Phase 1: We will only analyze the *last* image sent.
    # Phase 2 (later): We will send the *whole batch* to /analyze_batch
    
    await update.callback_query.edit_message_text("Processing your image(s), please wait... ⏳")
    
    # Get the file_id of the last good image
    last_file_id = image_batch[-1]
    
    try:
        # Get the file from Telegram's servers using its file_id
        photo_file = await context.bot.get_file(last_file_id)
        
        file_bytes_io = io.BytesIO()
        await photo_file.download_to_memory(file_bytes_io)
        file_bytes_io.seek(0)
        
        files_to_send = {'file': ('user_image.jpg', file_bytes_io, 'image/jpeg')}
        
        # --- Call the *original* analysis endpoint ---
        response = requests.post(API_URL_ANALYZE, files=files_to_send, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            counts = data.get('counts', {})
            flags = data.get('flags', [])
            
            report = "🔬 *Analysis Report (Based on last image)* 🔬\n\n"
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
                
            await update.callback_query.edit_message_text(report, parse_mode="Markdown")

            # --- NEW: Ask for LLM chat ---
            keyboard = [
                [InlineKeyboardButton("🧠 Discuss with AI", callback_data="start_llm_chat")],
                [InlineKeyboardButton("Start New Analysis", callback_data="start_analysis")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.message.reply_text("Your report is ready. Would you like to discuss these results?", reply_markup=reply_markup)
            
        else:
            await update.callback_query.edit_message_text(f"Sorry, the analysis server returned an error (Code: {response.status_code}). Please try again.")

    except requests.exceptions.Timeout:
        await update.callback_query.edit_message_text("The analysis is taking too long. Please try again.")
    except Exception as e:
        print(f"Error in handle_done: {e}")
        await update.callback_query.edit_message_text("Error: Could not retrieve image for analysis. Please start over.")
    
    # Clean up and end the conversation
    context.user_data.clear()
    return ConversationHandler.END

# --- NEW: Handle the "Cancel" button press ---
async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the current analysis session."""
    await update.callback_query.answer()
    
    context.user_data.clear()
    
    await update.callback_query.edit_message_text(
        "Analysis cancelled. Send /start or /analyze to begin a new one."
    )
    return ConversationHandler.END


# --- Placeholder LLM functions ---
async def start_llm_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Placeholder for starting the LLM Q&A."""
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("This feature is coming soon! Press /start to run a new analysis.")
    # In the future, this will return Q_AND_A state
    return ConversationHandler.END # For now, just end


# --- Other Bot Commands ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to see options or /analyze to begin a new session.")

async def developer_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        f"MicroSmart is an open-source project. You can contribute on GitHub:\n{CONTRIBUTE_URL}"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error {context.error}")


def main():
    """Starts the bot."""
    print("Bot is starting...")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # --- NEW: ConversationHandler for the main analysis flow ---
    analysis_conv = ConversationHandler(
        entry_points=[
            CommandHandler("analyze", start_analysis),
            CallbackQueryHandler(start_analysis, pattern="^start_analysis$")
        ],
        states={
            UPLOADING_IMAGES: [
                MessageHandler(filters.PHOTO, handle_image_upload),
                CallbackQueryHandler(show_tutorial, pattern="^show_tutorial$"),
                CallbackQueryHandler(handle_done, pattern="^analysis_done$")
            ],
            # Q_AND_A state will be added in Phase 3
        },
        fallbacks=[
            CallbackQueryHandler(handle_cancel, pattern="^analysis_cancel$"),
            CommandHandler("start", start_command) # Allow /start to reset everything
        ]
    )
    
    app.add_handler(analysis_conv)
    
    # --- Other handlers ---
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(developer_info, pattern="^developer_info$"))
    
    # This handler is now *outside* the conversation, for the "Discuss" button
    app.add_handler(CallbackQueryHandler(start_llm_chat, pattern="^start_llm_chat$"))
    
    app.add_error_handler(error_handler)
    
    print("Bot is polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()