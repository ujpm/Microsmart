import httpx
import io
import os
import cv2
import requests
import numpy as np
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

# --- UPDATED Image Handler ---
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles when a user sends a photo for analysis."""
    
    await update.message.reply_text("Processing your image, please wait... ⏳")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
    except Exception as e:
        print(f"Error getting file: {e}")
        await update.message.reply_text("Sorry, I had trouble downloading your image. Please try again.")
        return

    # 1. Download the photo as bytes
    file_bytes_io = io.BytesIO()
    await photo_file.download_to_memory(file_bytes_io)
    file_bytes_io.seek(0)
    file_bytes = file_bytes_io.read() # Get raw bytes
    
    # --- NEW: Image Resizing Step (from our previous conversation) ---
    try:
        nparr = np.frombuffer(file_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            await update.message.reply_text("Sorry, I couldn't read this image file. Is it corrupted?")
            return

        MAX_DIMENSION = 1280
        height, width = img.shape[:2]
        
        if height > MAX_DIMENSION or width > MAX_DIMENSION:
            await update.message.reply_text("Image is large, resizing for analysis...")
            if height > width:
                scale = MAX_DIMENSION / float(height)
            else:
                scale = MAX_DIMENSION / float(width)
            new_dim = (int(width * scale), int(height * scale))
            img = cv2.resize(img, new_dim, interpolation=cv2.INTER_AREA)

        success, resized_image_buffer = cv2.imencode('.jpg', img)
        if not success:
            await update.message.reply_text("Sorry, I had an error processing the image.")
            return
        resized_image_bytes = resized_image_buffer.tobytes()
        
    except Exception as e:
        print(f"Error resizing image: {e}")
        await update.message.reply_text("Sorry, I had an error processing your image file.")
        return
    # --- End of Resizing Step ---

    files_to_send = {'file': ('user_image.jpg', resized_image_bytes, 'image/jpeg')}
    
    try:
        response = requests.post(API_URL_CHECK, files=files_to_send, timeout=120) # 120 sec timeout
        
        if response.status_code == 200:
            data = response.json()
            counts = data.get('counts', {})
            
            # --- NEW: Rich Report Formatting (Level 2) ---
            
            # Define reference ranges (you can adjust these)
            ref_rbc = (300, 400)
            ref_wbc = (4, 10)
            ref_platelet = (20, 50)

            # Get counts
            rbc_count = counts.get('RBC', 0)
            wbc_count = counts.get('WBC', 0)
            platelet_count = counts.get('Platelet', 0)

            # Build the report string using HTML tags
            report = "🔬 <b>Analysis Report</b> 🔬\n\n"
            report += "<b><u>Cellular Counts (per field)</u></b>\n" # Bold + Underline
            report += f"  🩸 RBC: <code>{rbc_count}</code> <i>(Ref: {ref_rbc[0]}-{ref_rbc[1]})</i>\n"
            report += f"  ⚪️ WBC: <code>{wbc_count}</code> <i>(Ref: {ref_wbc[0]}-{ref_wbc[1]})</i>\n"
            report += f"  🔵 Platelets: <code>{platelet_count}</code> <i>(Ref: {ref_platelet[0]}-{ref_platelet[1]})</i>\n\n"

            # Build flags
            flags_list = []
            if wbc_count > ref_wbc[1]:
                flags_list.append(f"Potential Leukocytosis (High WBC: <code>{wbc_count}</code>)")
            if wbc_count < ref_wbc[0]:
                flags_list.append(f"Potential Leukopenia (Low WBC: <code>{wbc_count}</code>)")
            if platelet_count < ref_platelet[0]:
                flags_list.append(f"Potential Thrombocytopenia (Low Platelets: <code>{platelet_count}</code>)")

            if flags_list:
                report += "⚠️ <b>Potential Flags</b>\n"
                for flag in flags_list:
                    report += f"  - {flag}\n"
            else:
                report += "✅ <b>All counts within reference ranges.</b>\n"
                
            report += "\n" # Add a space
            report += "<blockquote><i>Disclaimer: This is an automated analysis for a hackathon project, not a medical diagnosis. Please consult a qualified professional.</i></blockquote>"
                
            # Send the report using parse_mode="HTML"
            await update.message.reply_text(report, parse_mode="HTML")
            
        else:
            await update.message.reply_text(f"Sorry, the analysis server returned an error (Code: {response.status_code}). Please try again.")

    except requests.exceptions.Timeout:
        await update.message.reply_text("The analysis is taking too long. The server may be waking up. Please try again.")
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to API: {e}")
        await update.message.reply_text("Error: Could not connect to the analysis server. Please tell the admin.")
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
        response = await client.post(
            API_URL_BATCH, 
            json={"file_ids": file_ids}, 
            timeout=60.0
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # --- NEW: Parse the individual reports ---
            individual_reports = data.get("individualImageReports", [])
            concentrations = data.get("aggregatedAnalysis", {}).get("finalConcentrations", {})
            flags = data.get("flags", [])
            num_images = data.get("imageCount", len(file_ids))
            
            # --- NEW: Build the first part of the report (per-image) ---
            report = "🔬 *Per-Field Counts:*\n"
            for img_report in individual_reports:
                counts = img_report.get("counts", {})
                report += f"  - Image {img_report.get('image_index')}: "
                report += f"WBC: {counts.get('WBC', 0)}, "
                report += f"RBC: {counts.get('RBC', 0)}, "
                report += f"PLT: {counts.get('Platelet', 0)}\n"
            
            # --- Build the second part (aggregated) ---
            report += f"\n🔬 *Aggregated Report ({num_images} fields)* 🔬\n\n"
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
            
            # Store the rich JSON for the LLM
            context.user_data['llm_context'] = data

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
            await update.callback_query.edit_message_text(f"Sorry, the analysis server returned an error (Code: {response.status_code}). Response: {response.text}")

    except httpx.ReadTimeout:
        await update.callback_query.edit_message_text("The analysis is taking too long (timeout). Please try again with fewer images.")
    except httpx.RequestError as e:
        print(f"Error connecting to batch_analyze API: {e}")
        await update.callback_query.edit_message_text("Error: Could not connect to the analysis server for the final report.")
    except Exception as e:
        print(f"An unexpected error in handle_done: {e}")
        await update.callback_query.edit_message_text("An unexpected error occurred. Please start over.")
    
    # End the UPLOADING state, but don't clear user_data
    # It will be cleared when a new analysis starts or LLM chat ends
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
    
    # Check if we have report data to discuss
    if 'llm_context' in context.user_data:
        # TODO: Implement Phase 3 (LLM Q&A)
        await update.callback_query.edit_message_text("This feature is coming in Phase 3! Press /start to run a new analysis.")
        context.user_data.clear() # Clear context after discussion
        return ConversationHandler.END
    else:
        await update.callback_query.edit_message_text("There is no report to discuss. Please run a new /analyze session first.")
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

    analysis_conv = ConversationHandler(
        entry_points=[
            CommandHandler("analyze", start_analysis),
            CallbackQueryHandler(start_analysis, pattern="^start_analysis$")
        ],
        states={
            UPLOADING_IMAGES: [
                MessageHandler(filters.PHOTO, handle_image),
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
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(developer_info, pattern="^developer_info$"))
    app.add_handler(CallbackQueryHandler(start_llm_chat, pattern="^start_llm_chat$"))
    
    app.add_error_handler(error_handler)
    
    print("Bot is polling for messages...")
    app.run_polling()

if __name__ == "__main__":
    main()