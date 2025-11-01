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
import google.api_core.exceptions
import asyncio

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
    # --- FIX #1: Use the model name you confirmed works ---
    llm_model = genai.GenerativeModel('models/gemini-flash-latest')
    print("Gemini model configured successfully.")
except Exception as e:
    print(f"Error configuring Gemini: {e}")
    llm_model = None

client = httpx.AsyncClient()


# --- "Health Check" Command (Unchanged, we know this works) ---
async def check_brain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    A standalone command to diagnose the Gemini API.
    """
    if not llm_model:
        await update.message.reply_text("Brain check failed: `llm_model` is not loaded. Check server logs.")
        return
        
    await update.message.reply_text("🧠 Checking connection to Gemini API... please wait.")
    
    try:
        # Use the native async method
        response = await llm_model.generate_content_async(
            "Hello. Are you working? Respond with only the word 'OK'."
        )
        
        if "OK" in response.text:
            await update.message.reply_text("✅ <b>Brain check SUCCESS!</b> The Gemini API is responding.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"⚠️ Brain check inconclusive. API responded, but not as expected.\n\nGot: <code>{response.text}</code>", parse_mode=ParseMode.HTML)
            
    except google.api_core.exceptions.PermissionDenied as e:
        print(f"Brain Check ERROR (PermissionDenied): {e}")
        await update.message.reply_text("❌ <b>Brain check FAILED (Permission Denied).</b>\n\nIt looks like the API key is invalid or doesn't have the right permissions. Check your Google Cloud project.", parse_mode=ParseMode.HTML)
    except google.api_core.exceptions.ResourceExhausted as e:
        print(f"Brain Check ERROR (ResourceExhausted): {e}")
        await update.message.reply_text("❌ <b>Brain check FAILED (Resource Exhausted).</b>\n\nWe are being rate-limited or the free quota has been hit. Check your Google API billing.", parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Brain Check ERROR (Unknown): {e}")
        await update.message.reply_text(f"❌ <b>Brain check FAILED (Unknown Error).</b>\n\nAn unexpected error occurred. Check the server logs.\n<code>{e}</code>", parse_mode=ParseMode.HTML)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Handles the /start command """
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
    """ STARTS the ConversationHandler for analysis. """
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
    """ Handles photos during the UPLOADING_IMAGES state. """
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
    """ User is finished. Call the /analyze_batch endpoint. """
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

# --- Real LLM Chat Functions ---

async def start_llm_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    STARTS the Q&A Conversation.
    """
    await update.callback_query.answer()
    
    if not llm_model:
        await update.callback_query.edit_message_text("Sorry, the AI 'Brain' is not connected. Please contact the admin. (Run /check_brain for details).")
        return ConversationHandler.END

    if 'llm_context' not in context.user_data:
        await update.callback_query.edit_message_text("There is no report to discuss. Please run a new /analyze session first.")
        return ConversationHandler.END

    # We are still creating the history list, but we won't use it
    # in handle_llm_chat. This is just to keep the state clean.
    system_prompt = f"""
You are MicroSmart, a helpful AI assistant for medical lab students.
The user is asking you questions. Respond as a helpful assistant.
"""
    
    context.user_data['llm_history'] = [
        {'role': 'user', 'parts': [system_prompt]},
        {'role': 'model', 'parts': ["Understood. I am ready to help the user."]}
    ]
    
    keyboard = [
        [InlineKeyboardButton("End Chat 💬", callback_data="end_llm_chat")],
        [InlineKeyboardButton("Start New Analysis 🚀", callback_data="start_analysis_new")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "I'm ready. What would you like to know?\n\n(Send /end to finish our chat, or use the button.)", 
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    
    return Q_AND_A 

async def handle_llm_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles all text messages *during* the Q_AND_A state.
    """
    if 'llm_history' not in context.user_data: # We check for history just to make sure we're in a valid session
        await update.message.reply_text("My apologies, I've lost our chat context. Please start a new analysis with /analyze.")
        return ConversationHandler.END

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="TYPING")
    
    print(f"[LLM] User question (diagnostic mode): {update.message.text}")

    try:
        # --- THIS IS THE DIAGNOSTIC TEST ---
        # We are *ignoring* the history list and sending the user's
        # message as a simple STRING, just like /check_brain.
        
        response = await llm_model.generate_content_async(
            update.message.text  # <-- We are sending the raw text only
        )
        
        # We are NOT saving the history. This is a "dumb" bot for testing.
        
        # Send the response to the user
        await update.message.reply_text(response.text, parse_mode=ParseMode.HTML)
        
    except google.api_core.exceptions.PermissionDenied as e:
        print(f"LLM Chat ERROR (PermissionDenied): {e}")
        await update.message.reply_text("❌ <b>Chat Error (Permission Denied).</b>\n\nIt looks like the API key is invalid or doesn't have the right permissions. Please tell the admin.", parse_mode=ParseMode.HTML)
    except google.api_core.exceptions.ResourceExhausted as e:
        print(f"LLM Chat ERROR (ResourceExhausted): {e}")
        await update.message.reply_text("❌ <b>Chat Error (ResourceExhausted).</b>\n\nWe are being rate-limited or the free quota has been hit. Please tell the admin.", parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Error communicating with Gemini: {e}")
        await update.message.reply_text("Sorry, I had trouble thinking of a response. Please try asking again.")

    return Q_AND_A

async def end_llm_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /end command or "End Chat" button to exit the Q&A session.
    """
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Happy to help! Our chat is finished.\n\nSend /analyze to start a new analysis.")
    else:
        await update.message.reply_text("Happy to help! Our chat is finished.\n\nSend /analyze to start a new analysis.")
    
    context.user_data.pop('llm_context', None)
    context.user_data.pop('llm_history', None) 
    
    return ConversationHandler.END

# --- Other Bot Commands ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "I am MicroSmart v1.0, an AI assistant.\n\n"
        "I can analyze blood smear photos. Use the /analyze command or the 'Try It Now' "
        "button to start a new session. For more info, use /start."
    )

async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "We'd love your feedback! To send it, please type:\n"
        "<code>/feedback</code> <i>followed by your message</i>.\n\n"
        "Example: <code>/feedback This bot is amazing!</code>",
        parse_mode=ParseMode.HTML
    )

async def contribute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"You can contribute to this project on GitHub:\n{CONTRIBUTE_URL}\n\n"
        "We are also actively looking for data partners!"
    )

async def developer_info(update: Update, context:ContextTypes.DEFAULT_TYPE):
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
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()

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
    app.add_handler(CommandHandler("check_brain", check_brain_command))
    
    app.add_handler(CallbackQueryHandler(developer_info, pattern="^developer_info$"))
    app.add_handler(CallbackQueryHandler(start_llm_chat, pattern="^start_llm_chat$"))
    
    app.add_error_handler(error_handler)
    
    print("Bot is polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()