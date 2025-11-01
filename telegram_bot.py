import httpx
import io
import os
import json
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
from telegram.constants import ParseMode
import google.generativeai as genai

# Load variables from your .env file
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_URL_CHECK = os.getenv("API_URL_CHECK") 
API_URL_BATCH = os.getenv("API_URL_BATCH")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found! Check your .env file.")

# --- Configure Gemini ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    llm_model = genai.GenerativeModel('gemini-1.5-flash')
    print("Gemini model configured successfully.")
except Exception as e:
    print(f"Error configuring Gemini: {e}")
    llm_model = None

client = httpx.AsyncClient()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /start command with the new welcome message and buttons.
    """
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
                text = f"✅ <b>Image {num_images} received.</b> For best results, we recommend 5-10 photos.\n\nPress <b>DONE</b> to analyze the <code>{num_images}</code> image(s) sent so far."
                
            else:
                reason = data.get("reason", "Unknown error")
                num_images = len(context.user_data['image_batch'])
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
            
            report = "<i>🔬 Per-Field Counts:</i>\n"
            if not individual_reports:
                report += "<blockquote><i>No individual counts available.</i></blockquote>\n"
            else:
                report += "<blockquote>"
                for img_report in individual_reports:
                    counts = img_report.get("counts", {})
                    report += f"<i>Image {img_report.get('image_index')}:</i> "
                    report += f"WBC: <code>{counts.get('WBC', 0)}</code>, "
                    report += f"RBC: <code>{counts.get('RBC', 0)}</code>, "
                    report += f"PLT: <code>{counts.get('Platelet', 0)}</code>\n"
                report += "</blockquote>"
            
            report += "\n<pre>--------------------</pre>\n"
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
            
            report += "\n<pre>--------------------</pre>\n"
            report += "<blockquote><i>Disclaimer: This is an AI-powered estimate, not a diagnosis. Please correlate with clinical findings.</i></blockquote>"

            await update.callback_query.edit_message_text(report, parse_mode=ParseMode.HTML)
            
            context.user_data['llm_context'] = data
            context.user_data['llm_report_text'] = report 

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

# --- NEW: Real LLM Chat Functions ---

async def start_llm_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    STARTS the Q&A Conversation.
    This is triggered by the '🧠 Discuss with AI' button.
    """
    await update.callback_query.answer()
    
    if not llm_model:
        await update.callback_query.edit_message_text("Sorry, the AI 'Brain' is not connected. Please contact the admin.")
        return ConversationHandler.END

    if 'llm_context' not in context.user_data:
        await update.callback_query.edit_message_text("There is no report to discuss. Please run a new /analyze session first.")
        return ConversationHandler.END

    system_prompt = f"""
You are MicroSmart, a helpful AI assistant for medical lab students and technicians in Rwanda.
You are discussing a blood smear analysis report that your 'eyes' (a YOLOv8 model) just generated.
NEVER give a diagnosis.
NEVER give medical advice.
ALWAYS be helpful, educational, and safe.
When asked about flags (like 'Leukopenia'), explain what the term means clinically (e.g., 'a low number of white blood cells') and what it *might* suggest (e.g., 'it can be caused by...'), but DO NOT diagnose the patient.
Use simple HTML formatting (<b>, <i>, <code>) in your responses.

The report you are discussing is here:
{json.dumps(context.user_data['llm_context'], indent=2)}
"""
    
    try:
        context.user_data['llm_chat'] = llm_model.start_chat(history=[
            {'role': 'user', 'parts': [system_prompt]},
            {'role': 'model', 'parts': ["Understood. I am ready to help the user understand this report. I will not provide a diagnosis."]}
        ])
    except Exception as e:
        print(f"Error starting Gemini chat: {e}")
        await update.callback_query.edit_message_text("Sorry, I had trouble connecting to the AI 'Brain'. Please try again later.")
        return ConversationHandler.END
    
    # --- FIX: Added the keyboard here as you requested ---
    keyboard = [
        [InlineKeyboardButton("End Chat 💬", callback_data="end_llm_chat")],
        [InlineKeyboardButton("Start New Analysis 🚀", callback_data="start_analysis_new")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "I have your report in front of me. What would you like to know?\n\n(Send /end to finish our chat, or use the button.)", 
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    
    return Q_AND_A

async def handle_llm_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles all text messages *during* the Q_AND_A state.
    Sends the user's question to Gemini and returns the answer.
    """
    if 'llm_chat' not in context.user_data:
        await update.message.reply_text("My apologies, I've lost our chat context. Please start a new analysis with /analyze.")
        return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="TYPING")
    
    print(f"[LLM] User question: {update.message.text}") # For debugging

    try:
        chat = context.user_data['llm_chat']
        
        # --- FIX: Run the blocking 'send_message' in a thread ---
        # This stops it from freezing the bot.
        response = await context.application.create_task(
            chat.send_message,
            update.message.text
        )
        
        await update.message.reply_text(response.text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        print(f"Error communicating with Gemini: {e}")
        await update.message.reply_text("Sorry, I had trouble thinking of a response. Please try asking again.")

    return Q_AND_A # Stay in the Q&A state

async def end_llm_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /end command or "End Chat" button to exit the Q&A session.
    """
    # Check if it's a button press or a command
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Happy to help! Our chat is finished.\n\nSend /analyze to start a new analysis.")
    else:
        await update.message.reply_text("Happy to help! Our chat is finished.\n\nSend /analyze to start a new analysis.")
    
    context.user_data.pop('llm_context', None)
    context.user_data.pop('llm_report_text', None)
    context.user_data.pop('llm_chat', None)
    
    return ConversationHandler.END

# --- Other Bot Commands ---
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
    return ConversationHandler.END


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error {context.error}")


def main():
    """Starts the bot."""
    print("Bot is starting...")
    
    # --- FIX: Add httpx_client to the Application builder ---
    # This allows `create_task` to work properly
    app = Application.builder().token(TELEGRAM_TOKEN).httpx_client(client).build()

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
            Q_AND_A: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_llm_chat),
                CommandHandler("end", end_llm_chat),
                # --- FIX: Added the callback for the "End Chat" button ---
                CallbackQueryHandler(end_llm_chat, pattern="^end_llm_chat$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(handle_cancel, pattern="^analysis_cancel$"),
            CommandHandler("start", start_command),
            CommandHandler("end", end_llm_chat)
        ],
        conversation_timeout=600 
    )
    
    app.add_handler(analysis_conv)
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("contribute", contribute_command))
    
    app.add_handler(CallbackQueryHandler(developer_info, pattern="^developer_info$"))
    app.add_handler(CallbackQueryHandler(start_llm_chat, pattern="^start_llm_chat$"))
    
    app.add_error_handler(error_handler)
    
    print("Bot is polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()