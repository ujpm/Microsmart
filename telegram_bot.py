import httpx
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
from telegram.constants import ParseMode # <-- NEW: Import ParseMode

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

client = httpx.AsyncClient()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /start command with the new welcome message and buttons.
    """
    # --- NEW: Formatted with <blockquote> and <b> ---
    welcome_text = """
Hello! Welcome to <b>MicroSmart</b> 🔬

I'm your AI-powered microscopy sidekick, here to give you <b>lightning-fast preliminary analysis</b> of those <i>pesky</i> microscopic samples.

<blockquote>
<b>🚧 Status: v1.0 "The Blood Analyst"</b>

I've mastered blood smears (for now)! I can:
* Count Red Blood Cells, White Blood Cells & Platelets.
* Flag anything that looks suspicious (like high/low counts).
* Give you an <b>estimated concentration</b> (e.g., <code>4.5 x 10⁹/L</code>) based on your images.

<b>🔮 The Grand Vision</b>

My training never stops! Soon I'll be learning to tackle:
* <b>Stool samples</b> (parasite egg hunt 🪱)
* <b>Urine sediment</b> (the great crystal hunt 💎)
* <b>Gram stains</b> (bacterial party identification 🦠)

<b>🤝 Join the Revolution!</b>

This is an open-source mission to make lab work less tedious. We're actively looking for collaborators.
</blockquote>

Ready to put me to work? Choose an option below!
"""
    keyboard = [
        [InlineKeyboardButton("Learn More 🌐", url=LEARN_MORE_URL)],
        [InlineKeyboardButton("Developer 👨‍💻", callback_data="developer_info")],
        [InlineKeyboardButton("Try It Now 🚀", callback_data="start_analysis")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    if 'image_batch' in context.user_data:
        context.user_data.clear()
    return ConversationHandler.END


async def start_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    STARTS the ConversationHandler for analysis.
    """
    context.user_data['image_batch'] = []
    
    # --- NEW: Formatted with <i> and <b> ---
    text = """
<i>Starting a new blood smear analysis...</i> 🩸

For best results, <b>100x oil immersion</b> images are recommended.

Please upload <b>5-10 clear photos</b> from different fields.
Press <b>DONE</b> when you are finished.
"""
    keyboard = [
        [InlineKeyboardButton("How to take a good photo 📸", callback_data="show_tutorial")],
        [InlineKeyboardButton("DONE (0 images)", callback_data="analysis_done")],
        [InlineKeyboardButton("Cancel Analysis ❌", callback_data="analysis_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

    return UPLOADING_IMAGES

async def show_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows a helper message with tips."""
    # --- NEW: Formatted with <b> ---
    text = """
<b>Tips for a Great Analysis:</b>
1.  <b>Use 100x Oil Immersion:</b> 🔬 Our calculations assume this magnification.
2.  <b>Find the Monolayer:</b> Analyze the 'feathered edge' where cells are in a single, even layer.
3.  <b>Focus is Key:</b> 🎯 Ensure cells are sharp and clear. This is the #1 reason for rejection.
4.  <b>Clean Lens:</b> A smudge can look like a platelet clump!
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
        response = await client.post(API_URL_CHECK, files=files_to_send, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "OK":
                context.user_data['image_batch'].append(photo_file.file_id)
                num_images = len(context.user_data['image_batch'])
                # --- NEW: Formatted with <b> and <code> ---
                text = f"✅ <b>Image {num_images} received.</b> For best results, we recommend 5-10 photos.\n\nPress <b>DONE</b> to analyze the <code>{num_images}</code> image(s) sent so far."
                
            else:
                reason = data.get("reason", "Unknown error")
                num_images = len(context.user_data['image_batch'])
                # --- NEW: Formatted with <b> and <code> ---
                text = f"❌ <b>Image rejected:</b> <code>{reason}</code>\n\n<b>Tip:</b> Please try a different photo. Press <b>DONE</b> to analyze the <code>{num_images}</code> image(s) you've sent, or <b>Cancel</b>."
        
        else:
            text = f"❌ Image upload failed. Server error (Code: <code>{response.status_code}</code>)."

    except httpx.RequestError as e:
        print(f"Error connecting to check_image API: {e}")
        text = "❌ Error: Could not connect to the analysis server. Please tell the admin."
    
    num_images = len(context.user_data['image_batch'])
    keyboard = [
        [InlineKeyboardButton(f"DONE ({num_images} images) ✅", callback_data="analysis_done")],
        [InlineKeyboardButton("Cancel Analysis ❌", callback_data="analysis_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
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
        f"Analyzing your <b>{len(file_ids)}</b> image(s), please wait... 🔬⏳",
        parse_mode=ParseMode.HTML
    )
    
    try:
        response = await client.post(
            API_URL_BATCH, 
            json={"file_ids": file_ids}, 
            timeout=60.0
        )
        
        if response.status_code == 200:
            data = response.json()
            
            individual_reports = data.get("individualImageReports", [])
            concentrations = data.get("aggregatedAnalysis", {}).get("finalConcentrations", {})
            flags = data.get("flags", [])
            num_images = data.get("imageCount", len(file_ids))
            
            # --- NEW: Heavily Formatted HTML Report ---
            report = "<i>🔬 Per-Field Counts:</i>\n"
            if not individual_reports:
                report += "<blockquote><i>No individual counts available.</i></blockquote>\n"
            else:
                report += "<blockquote>" # Start blockquote for all images
                for img_report in individual_reports:
                    counts = img_report.get("counts", {})
                    report += f"<i>Image {img_report.get('image_index')}:</i> "
                    report += f"WBC: <code>{counts.get('WBC', 0)}</code>, "
                    report += f"RBC: <code>{counts.get('RBC', 0)}</code>, "
                    report += f"PLT: <code>{counts.get('Platelet', 0)}</code>\n"
                report += "</blockquote>" # End blockquote
            
            report += "\n<pre>--------------------</pre>\n" # Horizontal line
            report += f"🧪 <b>Aggregated Report ({num_images} fields)</b> 🧪\n\n"
            report += "<b>Estimated Concentrations:</b>\n"
            report += f"  ⚪️ WBC: <b>{concentrations.get('WBC_x10e9_L', 'N/A')}</b> x 10⁹/L\n"
            report += f"  🔴 RBC: <b>{concentrations.get('RBC_x10e12_L', 'N/A')}</b> x 10¹²/L\n"
            report += f"  🩹 Platelets: <b>{concentrations.get('PLT_x10e9_L', 'N/A')}</b> x 10⁹/L\n\n"
            
            if flags:
                report += "⚠️ <b>Potential Flags (based on averages):</b>\n<blockquote>"
                for flag in flags:
                    report += f"<i>{flag}</i>\n"
                report += "</blockquote>"
            else:
                report += "✅ <i>No immediate issues flagged.</i>"
            
            report += "\n<pre>--------------------</pre>\n" # Horizontal line
            # Your blockquote for the disclaimer
            report += "<blockquote><i>Disclaimer: This is an AI-powered estimate, not a diagnosis. Please correlate with clinical findings.</i></blockquote>"

            await update.callback_query.edit_message_text(report, parse_mode=ParseMode.HTML)
            
            context.user_data['llm_context'] = data

            keyboard = [
                [InlineKeyboardButton("🧠 Discuss with AI", callback_data="start_llm_chat")],
                [InlineKeyboardButton("Start New Analysis 🚀", callback_data="start_analysis_new")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.message.reply_text(
                "Your report is ready. Would you like to discuss these results?", 
                reply_markup=reply_markup
            )
            
        else:
            await update.callback_query.edit_message_text(f"Sorry, the analysis server returned an error (Code: <code>{response.status_code}</code>). Response: <code>{response.text}</code>", parse_mode=ParseMode.HTML)

    except httpx.ReadTimeout:
        await update.callback_query.edit_message_text("The analysis is taking too long (timeout). Please try again with fewer images.")
    except httpx.RequestError as e:
        print(f"Error connecting to batch_analyze API: {e}")
        await update.callback_query.edit_message_text("Error: Could not connect to the analysis server for the final report.")
    except Exception as e:
        print(f"An unexpected error in handle_done: {e}")
        await update.callback_query.edit_message_text("An unexpected error occurred. Please start over.")
    
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
    
    if 'llm_context' in context.user_data:
        # TODO: Implement Phase 3 (LLM Q&A)
        await update.callback_query.edit_message_text("This feature is coming in Phase 3! Press /start to run a new analysis.")
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.callback_query.edit_message_text("There is no report to discuss. Please run a new /analyze session first.")
        return ConversationHandler.END

# --- Your NEW command handlers ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command."""
    await update.message.reply_text(
        "I am MicroSmart v1.0, an AI assistant.\n\n"
        "I can analyze blood smear photos. Use the /analyze command or the 'Try It Now' "
        "button to start a new session. For more info, use /start."
    )

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /feedback command."""
    await update.message.reply_text(
        "We'd love your feedback! To send it, please type:\n"
        "<code>/feedback</code> <i>followed by your message</i>.\n\n"
        "Example: <code>/feedback This bot is amazing!</code>",
        parse_mode=ParseMode.HTML
    )

async def contribute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /contribute command."""
    await update.message.reply_text(
        f"You can contribute to this project on GitHub:\n{CONTRIBUTE_URL}\n\n"
        "We are also actively looking for data partners!"
    )

async def developer_info(update: Update, context:ContextTypes.DEFAULT_TYPE):
    """Handles the 'Developer 👨‍💻' button click."""
    await update.callback_query.answer()
    
    # --- YOUR NEW POLISHED TEXT ---
    text = f"""
Hello from Rwanda! 🇷🇼 I'm JP, the developer.

By day, I'm a Biomedical Science student. By night, I'm a coder trying to convince my computer to understand hematology. MicroSmart is the result!

Want to help make this even smarter (or just see how the magic works)? It's all open-source. You can find the code and my other projects on GitHub!
"""
    keyboard = [
        [InlineKeyboardButton("View on GitHub 🌐", url=CONTRIBUTE_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.reply_text(text, reply_markup=reply_markup)


# --- Error Handler ---
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
            CallbackQueryHandler(start_analysis, pattern="^start_analysis$"),
            CallbackQueryHandler(start_analysis, pattern="^start_analysis_new$") 
        ],
        states={
            UPLOADING_IMAGES: [
                MessageHandler(filters.PHOTO, handle_image_upload),
                CallbackQueryHandler(show_tutorial, pattern="^show_tutorial$"),
                CallbackQueryHandler(handle_done, pattern="^analysis_done$")
            ],
            # Q_AND_A: [ ... will be added in Phase 3 ... ]
        },
        fallbacks=[
            CallbackQueryHandler(handle_cancel, pattern="^analysis_cancel$"),
            CommandHandler("start", start_command)
        ],
        conversation_timeout=600 
    )
    
    app.add_handler(analysis_conv)
    
    # --- Add all other handlers (NEW and OLD) ---
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("contribute", contribute_command))
    
    # Button handlers that are NOT part of the conversation
    app.add_handler(CallbackQueryHandler(developer_info, pattern="^developer_info$"))
    app.add_handler(CallbackQueryHandler(start_llm_chat, pattern="^start_llm_chat$"))
    
    app.add_error_handler(error_handler)
    
    print("Bot is polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()