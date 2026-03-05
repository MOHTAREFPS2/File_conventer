import os
import subprocess
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8792450275:AAFhitrzTCcgqh6PDYq0uu-YyTp0fuBFIy0"

DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "output"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

ALLOWED = ["ppt","pptx","doc","docx","xls","xlsx","odt","odp"]

WELCOME = """
📄 مرحباً بك في بوت تحويل الملفات إلى PDF

هذا البوت يقوم بتحويل ملفات:

• PowerPoint
• Word
• Excel
• OpenDocument

إلى ملف PDF مع الحفاظ على:
✔ الألوان
✔ الخطوط
✔ التنسيق

━━━━━━━━━━━━━━━

📌 طريقة الاستخدام

1️⃣ أرسل الملف مباشرة للبوت  
2️⃣ انتظر عدة ثواني  
3️⃣ سيصلك ملف PDF جاهز

━━━━━━━━━━━━━━━

📂 الصيغ المدعومة

ppt  
pptx  
doc  
docx  
xls  
xlsx  
odt  
odp  

━━━━━━━━━━━━━━━

⚠️ ملاحظات

• الحد الأقصى للحجم يعتمد على تيليجرام  
• الملفات يتم حذفها تلقائياً بعد التحويل  

━━━━━━━━━━━━━━━

🚀 أرسل ملفك الآن
"""

HELP = """
ℹ️ تعليمات استخدام البوت

الخطوات:

1️⃣ أرسل أي ملف من الصيغ المدعومة  
2️⃣ سيقوم البوت بتحويله إلى PDF  
3️⃣ سيتم إرسال الملف الناتج لك

الأوامر المتاحة:

/start - رسالة الترحيب  
/help - عرض التعليمات

الصيغ المدعومة:

PPT
PPTX
DOC
DOCX
XLS
XLSX
ODT
ODP
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)

async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):

    doc = update.message.document
    name = doc.file_name
    ext = name.split(".")[-1].lower()

    if ext not in ALLOWED:
        await update.message.reply_text("❌ هذه الصيغة غير مدعومة.")
        return

    await update.message.reply_text("⏳ جاري تحميل الملف...")

    file = await doc.get_file()

    input_path = os.path.join(DOWNLOAD_DIR, name)
    await file.download_to_drive(input_path)

    await update.message.reply_text("⚙️ جاري تحويل الملف إلى PDF...")

    subprocess.run([
        "soffice",
        "--headless",
        "--convert-to","pdf",
        "--outdir",OUTPUT_DIR,
        input_path
    ])

    pdf_name = name.rsplit(".",1)[0] + ".pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_name)

    if os.path.exists(pdf_path):

        await update.message.reply_text("📤 تم التحويل بنجاح. جاري الإرسال...")

        await update.message.reply_document(open(pdf_path,"rb"))

        os.remove(input_path)
        os.remove(pdf_path)

    else:
        await update.message.reply_text("❌ حدث خطأ أثناء التحويل")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(MessageHandler(filters.Document.ALL, convert))

print("BOT STARTED")

app.run_polling()