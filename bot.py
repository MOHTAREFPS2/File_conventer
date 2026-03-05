import os
import asyncio
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from pypdf import PdfReader, PdfWriter

TOKEN = "8792450275:AAFhitrzTCcgqh6PDYq0uu-YyTp0fuBFIy0"

DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "output"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

ALLOWED = ["ppt", "pptx", "doc", "docx", "xls", "xlsx", "odt", "odp"]
MAX_FILE_SIZE = 20 * 1024 * 1024

WELCOME = """
<b>📄 مرحباً بك في بوت إدارة وتحويل الملفات</b>

أرسل أي ملف وسيظهر لك زر لاختيار الإجراء المناسب.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode='HTML')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    name = doc.file_name
    
    if doc.file_size > MAX_FILE_SIZE:
        await update.message.reply_text("<b>❌ حجم الملف يتجاوز الحد الأقصى (20 ميجابايت).</b>", parse_mode='HTML')
        return

    if not name or "." not in name:
        await update.message.reply_text("<b>❌ صيغة الملف غير معروفة.</b>", parse_mode='HTML')
        return
        
    ext = name.split(".")[-1].lower()

    if ext == "pdf":
        keyboard = [
            [
                InlineKeyboardButton("🔴 قص الصفحات", callback_data="btn_cut"),
                InlineKeyboardButton("🟢 إستخراج النصوص", callback_data="btn_extract")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("<b>اختر الإجراء المطلوب لهذا الملف (PDF):</b>", reply_markup=reply_markup, reply_to_message_id=update.message.message_id, parse_mode='HTML')
        
    elif ext in ALLOWED:
        keyboard = [[InlineKeyboardButton("🔵 تحويل إلى PDF", callback_data="btn_convert")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("<b>الملف جاهز للتحويل:</b>", reply_markup=reply_markup, reply_to_message_id=update.message.message_id, parse_mode='HTML')
    else:
        await update.message.reply_text("<b>❌ هذه الصيغة غير مدعومة.</b>", parse_mode='HTML')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    original_msg = query.message.reply_to_message

    if not original_msg or not original_msg.document:
        await query.edit_message_text("<b>❌ تعذر العثور على الملف الأصلي. يرجى إرساله مجدداً.</b>", parse_mode='HTML')
        return

    doc = original_msg.document
    name = doc.file_name

    if action == "btn_convert":
        await convert_process(query, doc, name)
    elif action == "btn_extract":
        await extract_process(query, doc)
    elif action == "btn_cut":
        await query.edit_message_text("<b>✂️ لقص هذا الملف، قم بالرد (Reply) على الملف الأصلي واكتب الأمر بهذا الشكل:</b>\n\n<code>/cut 1-5</code>\n<i>(لتحديد الصفحات من 1 إلى 5)</i>", parse_mode='HTML')

async def convert_process(query, doc, name):
    await query.edit_message_text("<b>⚙️ جاري التحويل إلى PDF... يرجى الانتظار.</b>", parse_mode='HTML')
    input_path = ""
    pdf_path = ""
    
    try:
        file = await doc.get_file()
        unique_id = str(uuid.uuid4().hex)[:8]
        unique_name = f"{unique_id}_{name}"
        input_path = os.path.join(DOWNLOAD_DIR, unique_name)
        
        await file.download_to_drive(input_path)

        process = await asyncio.create_subprocess_exec(
            "soffice", "--headless", "--convert-to", "pdf", "--outdir", OUTPUT_DIR, input_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        if process.returncode != 0:
            await query.edit_message_text("<b>❌ فشل التحويل. تأكد من أن الملف غير تالف.</b>", parse_mode='HTML')
            return

        pdf_name = unique_name.rsplit(".", 1)[0] + ".pdf"
        pdf_path = os.path.join(OUTPUT_DIR, pdf_name)
        
        # للحفاظ على الاسم الأصلي تماماً كما طلبت
        original_final_name = name.rsplit(".", 1)[0] + ".pdf"

        if os.path.exists(pdf_path):
            await query.edit_message_text("<b>📤 تم التحويل بنجاح! جاري الإرسال...</b>", parse_mode='HTML')
            with open(pdf_path, 'rb') as pdf_file:
                await query.message.reply_document(document=pdf_file, filename=original_final_name)
            await query.message.delete()
        else:
            await query.edit_message_text("<b>❌ حدث خطأ: لم يتم العثور على الملف النهائي.</b>", parse_mode='HTML')

    except Exception as e:
         await query.edit_message_text(f"<b>❌ خطأ غير متوقع:</b>\n<code>{str(e)}</code>", parse_mode='HTML')
    finally:
        if input_path and os.path.exists(input_path): os.remove(input_path)
        if pdf_path and os.path.exists(pdf_path): os.remove(pdf_path)

async def extract_process(query, doc):
    await query.edit_message_text("<b>📝 جاري قراءة الملف واستخراج النصوص...</b>", parse_mode='HTML')
    input_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.pdf")

    try:
        file = await doc.get_file()
        await file.download_to_drive(input_path)

        reader = PdfReader(input_path)
        extracted_text = ""
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                extracted_text += f"\n<b>--- صفحة {i+1} ---</b>\n{text}\n"

        if not extracted_text.strip():
            await query.edit_message_text("<b>⚠️ الملف لا يحتوي على نصوص قابلة للاستخراج (قد يكون صوراً ممسوحة ضوئياً).</b>", parse_mode='HTML')
            return

        await query.edit_message_text("<b>✅ تم استخراج النص بنجاح:</b>", parse_mode='HTML')
        
        chunk_size = 3500
        for i in range(0, len(extracted_text), chunk_size):
            await query.message.reply_text(f"<code>{extracted_text[i:i+chunk_size]}</code>", parse_mode='HTML')

    except Exception as e:
        await query.edit_message_text(f"<b>❌ حدث خطأ أثناء الاستخراج:</b>\n<code>{str(e)}</code>", parse_mode='HTML')
    finally:
        if os.path.exists(input_path): os.remove(input_path)

async def cut_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("<b>❌ الرجاء إرسال أمر القص كرد (Reply) على ملف PDF المطلوب.</b>", parse_mode='HTML')
        return
        
    doc = update.message.reply_to_message.document
    command_text = update.message.text.replace("/cut", "").strip()
    try:
        start_page, end_page = map(int, command_text.split("-"))
    except:
        await update.message.reply_text("<b>❌ صيغة خاطئة.</b>\nالاستخدام الصحيح: <code>/cut 1-5</code>", parse_mode='HTML')
        return

    status_msg = await update.message.reply_text("<b>✂️ جاري قص الملف...</b>", parse_mode='HTML')
    input_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex}.pdf")
    output_path = os.path.join(OUTPUT_DIR, f"Cut_{doc.file_name}")

    try:
        file = await doc.get_file()
        await file.download_to_drive(input_path)

        reader = PdfReader(input_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)

        if start_page < 1 or end_page > total_pages or start_page > end_page:
            await status_msg.edit_text(f"<b>❌ نطاق الصفحات غير صحيح.</b>\nالملف يحتوي على {total_pages} صفحة.", parse_mode='HTML')
            return

        for i in range(start_page - 1, end_page):
            writer.add_page(reader.pages[i])

        with open(output_path, "wb") as f_out:
            writer.write(f_out)

        with open(output_path, "rb") as f_send:
            await update.message.reply_document(document=f_send, filename=doc.file_name) # نفس الاسم الأصلي
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"<b>❌ حدث خطأ أثناء القص:</b>\n<code>{str(e)}</code>", parse_mode='HTML')
    finally:
        if os.path.exists(input_path): os.remove(input_path)
        if os.path.exists(output_path): os.remove(output_path)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cut", cut_pdf))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("BOT STARTED WITH BUTTONS!")
    app.run_polling()
