import httpx  # <-- NEW: Replaced 'requests'
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
    ConversationHandler
)

# Load variables from your .env file
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_URL_CHECK = os.getenv("API_URL_CHECK") 
API_URL_BATCH = os.getenv("API_URL_BATCH")

# --- URL & Text Configuration ---
LEARN_MORE_URL = "https://portifolio-cgu.pages.dev/"
CONTRIBUTE_URL = "https://github.com/ujpm/"

# --- Conversation States ---
UPLOADING_IMAGES, Q_AND_A = range(2)

# Check if the variables are loaded
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found! Check your .env file.")
if not API_URL_CHECK:
    raise ValueError("API_URL_CHECK not found! Check your .env file.")
if not API_URL_BATCH:
    raise ValueError("API_URL_BATCH not found! Check your .env file.")

# --- NEW: Asynchronous HTTP client for the bot ---
client = httpx.AsyncClient()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    welcome_text = """
Hello! Welcome to **MicroSmart** 🔬

I'm your AI-powered microscopy sidekick, here to give you **lightning-fast preliminary analysis** of those *pesky* microscopic samples.

Ready to put me to work? Choose an option below!
"""
    keyboard = [
        [InlineKeyboardButton("Learn More 🌐", url=LEARN_MORE_URL)],
        [InlineKeyboardButton("Developer 👨‍💻", callback_data="developer_info")],
        [InlineKeyboardButton("Try It Now 🚀", callback_data="start_analysis")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

    if 'image_batch' in context.user_data:
        context.user_data.clear()
    return ConversationHandler.END


async def start_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """STARTS the ConversationHandler."""
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

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

    return UPLOADING_IMAGES

async def show_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows a helper message with tips."""
    text = """
**Tips for a Great Analysis:**
1.  **Use 100x Oil Immersion:** Our calculations assume this magnification.
2.  **Find the Monolayer:** Analyze the 'feathered edge' where cells are in a single, even layer.
3.  **Focus is Key:** Ensure cells are sharp and clear. This is the #1 reason for rejection.
4.  **Clean Lens:** A smudge can look like a platelet clump!
"""
    await update.callback_query.answer(text, show_alert=True)
    return UPLOADING_IMAGES

async def handle_image_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles photos during the UPLOADING_IMAGES state.
    Calls the /check_image API.
    """
    photo_file = await update.message.photo[-1].get_file()
    
    file_bytes_io = io.BytesIO()
    await photo_file.download_to_memory(file_bytes_io)
    file_bytes_io.seek(0)
    
    files_to_send = {'file': ('user_image.jpg', file_bytes_io, 'image/jpeg')}
    
    try:
        # !! FIX: Use 'await client.post' instead of 'requests.post' !!
        response = await client.post(API_URL_CHECK, files=files_to_send, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK":
                context.user_data['image_batch'].append(photo_file.file_id)
                num_images = len(context.user_data['image_batch'])
                text = f"✅ Image {num_images} received. For best results, we recommend 5-10 photos.\n\nPress **DONE** to analyze the **{num_images}** image(s) sent so far."
                
            else:
                reason = data.get("reason", "Unknown error")
                num_images = len(context.user_data['image_batch'])
                text = f"❌ Image rejected: **{reason}**\n\n**Tip:** Please try a different photo. Press **DONE** to analyze the **{num_images}** image(s) you've sent, or **Cancel**."
        
        else:
            text = f"❌ Image upload failed. Server error (Code: {response.status_code})."

    except httpx.RequestError as e:
        print(f"Error connecting to check_image API: {e}")
        text = "❌ Error: Could not connect to the analysis server. Please tell the admin."
    
    num_images = len(context.user_data['image_batch'])
    keyboard = [
        [InlineKeyboardButton(f"DONE ({num_images} images)", callback_data="analysis_done")],
        [InlineKeyboardButton("Cancel Analysis", callback_data="analysis_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    
    return UPLOADING_IMAGES

async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User is finished. Call the /analyze_batch endpoint.
    """
    await update.callback_query.answer()
    
    file_ids = context.user_data.get('image_batch', [])
    
    if not file_ids:
        await update.callback_query.message.reply_text("You haven't sent any clear photos yet! Please send a photo or press Cancel.")
        return UPLOADING_IMAGES

    await update.callback_query.edit_message_text(
        f"Analyzing your **{len(file_ids)}** image(s), please wait... 🔬⏳"
    )
    
    try:
        # !! FIX: Use 'await client.post' and send JSON !!
        response = await client.post(
            API_URL_BATCH, 
            json={"file_ids": file_ids}, 
            timeout=60.0  # Allow longer timeout for batch analysis
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # --- Parse the new "Rich Info JSON" ---
            concentrations = data.get("aggregatedAnalysis", {}).get("finalConcentrations", {})
            flags = data.get("flags", [])
            num_images = data.get("imageCount", len(file_ids))
            
            # --- Build the new report with concentrations ---
            report = f"🔬 *Aggregated Report ({num_images} fields)* 🔬\n\n"
            report += "*Estimated Concentrations:*\n"
            report += f"  - WBC: *{concentrations.get('WBC_x10e9_L', 'N/A')}* x 10⁹/L\n"
            report += f"  - RBC: *{concentrations.get('RBC_x10e12_L', 'N/A')}* x 10¹²/L\n"
            report += f"  - Platelets: *{concentrations.get('PLT_x10e9_L', 'N/A')}* x 10⁹/L\n\n"
            
            if flags:
                report += "⚠️ *Potential Flags (based on averages):*\n"
                for flag in flags:
                    report += f"  - {flag}\n"
            else:
                report += "✅ *No immediate issues flagged.*"
            
            report += "\n\n*Disclaimer: This is an AI-powered estimate, not a diagnosis. Please correlate with clinical findings.*"

            await update.callback_query.edit_message_text(report, parse_mode="Markdown")

            # --- Ask for LLM chat ---
            keyboard = [
                [InlineKeyboardButton("🧠 Discuss with AI", callback_data="start_llm_chat")],
                [InlineKeyboardButton("Start New Analysis", callback_data="start_analysis")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.message.reply_text(
                "Your report is ready. Would you like to discuss these results?", 
                reply_markup=reply_markup
            )
            
        else:
            # Provide more debug info to the user
            await update.callback_query.edit_message_text(f"Sorry, the analysis server returned an error (Code: {response.status_code}). Response: {response.text}")

    except httpx.ReadTimeout:
        await update.callback_query.edit_message_text("The analysis is taking too long (timeout). Please try again with fewer images.")
    except httpx.RequestError as e:
        print(f"Error connecting to batch_analyze API: {e}")
        await update.callback_query.edit_message_text("Error: Could not connect to the analysis server for the final report.")
    except Exception as e:
        print(f"An unexpected error in handle_done: {e}")
        await update.callback_query.edit_message_text("An unexpected error occurred. Please start over.")
    
    context.user_data.clear()
    return ConversationHandler.END

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
    return ConversationHandler.END 

# --- Other Bot Commands ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /start to see options or /analyze to begin a new session.")

async def developer_info(update: Update, context:ContextTypes.DEFAULT_TYPE):
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

    # --- ConversationHandler for the main analysis flow ---
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
            CommandHandler("start", start_command)
        ],
        # Allow the bot to be used by multiple users at once
        conversation_timeout=600 # 10 minutes
    )
    
    app.add_handler(analysis_conv)
    
    # --- Other handlers ---
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(developer_info, pattern="^developer_info$"))
    app.add_handler(CallbackQueryHandler(start_llm_chat, pattern="^start_llm_chat$"))
    
    app.add_error_handler(error_handler)
    
    print("Bot is polling for messages...")
    
    # --- NEW: Add a shutdown hook to close the httpx client ---
    app.run_polling()

if __name__ == "__main__":
    main()