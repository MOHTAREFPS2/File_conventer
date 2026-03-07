import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pypdf import PdfReader, PdfWriter
import os
import time
import re
import subprocess
import sqlite3
import hashlib
from datetime import datetime, timedelta

# ضع توكن البوت الخاص بك هنا
TOKEN = "8792450275:AAH8GiaNoIySkJHDKQ4R6kLVQQ20qLedLos"
bot = telebot.TeleBot(TOKEN)

# قاموس لحفظ حالة كل مستخدم لتنظيم الخطوات
user_data = {}

# إعداد قاعدة البيانات لحفظ الملفات المحولة
def init_db():
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS converted_files
                 (file_hash TEXT PRIMARY KEY, pdf_file_id TEXT, last_used TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# دالة لإنشاء بصمة رقمية للملف
def get_file_hash(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = InlineKeyboardMarkup(row_width=1)
    
    btn1 = InlineKeyboardButton("تحويل ملف Office إلى PDF", callback_data="office_to_pdf",style="success")
    btn2 = InlineKeyboardButton("استخراج النصوص من ملف PDF", callback_data="extract_text",style="primary")
    btn3 = InlineKeyboardButton("قص صفحات محددة من ملفات PDF", callback_data="crop_pdf",style="danger")
    
    markup.add(btn1, btn2, btn3)
    bot.send_message(message.chat.id, "أهلاً بك!\nاختر إحدى الخدمات الأكاديمية التالية:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    action = call.data
    
    user_data[chat_id] = {'action': action}
    
    if action == "office_to_pdf":
        msg = bot.send_message(chat_id, "يرجى إرسال ملف Office (Word, PowerPoint, Excel) للتحويل...")
        bot.register_next_step_handler(msg, process_file_upload)
        
    elif action in ["extract_text", "crop_pdf"]:
        caption = "ملاحظة: يجب على الطالب ان يعتمد على ترقيم برنامج الPDF الذي يستخدمه و ليس على رقم صفحة الملف نفسه"
        
        try:
            with open("note.jpg", "rb") as photo:
                bot.send_photo(chat_id, photo, caption=caption)
        except FileNotFoundError:
            bot.send_message(chat_id, f"[تنبيه: صورة note.jpg غير موجودة في السيرفر]\n\n{caption}")
            
        msg = bot.send_message(chat_id, "يرجى إرسال ملف الـ PDF الآن:")
        bot.register_next_step_handler(msg, process_file_upload)

def process_file_upload(message):
    chat_id = message.chat.id
    
    if not message.document:
        msg = bot.send_message(chat_id, "الرجاء إرسال ملف صالح كـ Document.")
        bot.register_next_step_handler(msg, process_file_upload)
        return

    # حد أقصى 20 ميجابايت لحماية موارد السيرفر ومراعاة قيود تيليجرام
    file_size = message.document.file_size
    limit_mb = 50
    if file_size > limit_mb * 1024 * 1024:
        bot.send_message(chat_id, f"عذراً، حجم الملف يتجاوز الحد المسموح به ({limit_mb}MB).\nملاحظة: تم وضع هذا الحد بسبب حدود الموارد.")
        return

    action = user_data.get(chat_id, {}).get('action')
    
    bot.send_message(chat_id, "جاري تحميل الملف، يرجى الانتظار...")
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    original_ext = os.path.splitext(message.document.file_name)[1].lower()
    local_filename = f"file_{chat_id}_{message.message_id}{original_ext}"
    
    with open(local_filename, 'wb') as new_file:
        new_file.write(downloaded_file)
        
    user_data[chat_id]['file_path'] = local_filename

    if action == "office_to_pdf":
        convert_office_to_pdf(chat_id, local_filename)
    else:
        msg = bot.send_message(chat_id, "تم استلام الملف بنجاح.\nيرجى كتابة نطاق الصفحات بالصيغة التالية (مثال: من 1 الى 10):")
        bot.register_next_step_handler(msg, process_page_range)

def process_page_range(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    pattern = r"^من\s+(\d+)\s+(الى|إلى)\s+(\d+)$"
    match = re.search(pattern, text)
    
    if not match:
        msg = bot.send_message(chat_id, "صيغة غير صحيحة! يرجى الكتابة بالضبط هكذا: من 1 الى 10")
        bot.register_next_step_handler(msg, process_page_range)
        return
        
    start_page = int(match.group(1))
    end_page = int(match.group(3))
    
    if start_page > end_page or start_page < 1:
        msg = bot.send_message(chat_id, "أرقام الصفحات غير منطقية. حاول مرة أخرى:")
        bot.register_next_step_handler(msg, process_page_range)
        return
        
    action = user_data.get(chat_id, {}).get('action')
    file_path = user_data.get(chat_id, {}).get('file_path')
    
    if action == "extract_text":
        extract_pdf_text(chat_id, file_path, start_page, end_page)
    elif action == "crop_pdf":
        crop_pdf_pages(chat_id, file_path, start_page, end_page)

def extract_pdf_text(chat_id, file_path, start_page, end_page):
    bot.send_message(chat_id, "جاري استخراج النصوص (قد يستغرق الأمر بعض الوقت لتقليل الضغط)...")
    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        
        if end_page > total_pages:
            end_page = total_pages
            
        extracted_text = ""
        pages_processed = 0
        
        start_idx = start_page - 1
        end_idx = end_page - 1
        
        for i, page_num in enumerate(range(start_idx, end_idx + 1)):
            page = reader.pages[page_num]
            text = page.extract_text()
            if text:
                extracted_text += f"\n--- صفحة {page_num + 1} ---\n{text}\n"
                
            pages_processed += 1
            
            if pages_processed % 5 == 0 and page_num != end_idx:
                time.sleep(3)
                
        txt_filename = f"extracted_{chat_id}.txt"
        with open(txt_filename, "w", encoding="utf-8") as txt_file:
            txt_file.write(extracted_text)
            
        with open(txt_filename, "rb") as final_file:
            bot.send_document(chat_id, final_file, caption="تم استخراج النصوص بنجاح.")
            
        os.remove(txt_filename)
        
    except Exception as e:
        bot.send_message(chat_id, "حدث خطأ أثناء معالجة الملف.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def crop_pdf_pages(chat_id, file_path, start_page, end_page):
    bot.send_message(chat_id, "جاري قص الصفحات...")
    try:
        reader = PdfReader(file_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)
        
        if end_page > total_pages:
            end_page = total_pages
            
        start_idx = start_page - 1
        end_idx = end_page - 1
        
        for page_num in range(start_idx, end_idx + 1):
            writer.add_page(reader.pages[page_num])
            
        output_filename = f"cropped_{chat_id}.pdf"
        with open(output_filename, "wb") as output_pdf:
            writer.write(output_pdf)
            
        with open(output_filename, "rb") as final_pdf:
            bot.send_document(chat_id, final_pdf, caption=f"تم قص الصفحات من {start_page} إلى {end_page}.")
            
        os.remove(output_filename)
        
    except Exception as e:
        bot.send_message(chat_id, "حدث خطأ أثناء قص الملف.")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# معرف المجموعة التي أنشأتها (يجب أن يبدأ بـ @)
GROUP_USERNAME = "@file_of_conventor_bot"

def convert_office_to_pdf(chat_id, file_path):
    file_hash = get_file_hash(file_path)
    
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute("SELECT pdf_file_id FROM converted_files WHERE file_hash = ?", (file_hash,))
    result = c.fetchone()
    
    if result:
        # الملف موجود مسبقاً
        pdf_file_id = result[0]
        bot.send_message(chat_id, "تم العثور على الملف مسبقاً! جاري إرساله فوراً...")
        try:
            bot.send_document(chat_id, pdf_file_id, caption="تم الإرسال بنجاح✅.")
            # تحديث تاريخ الاستخدام (اختياري الآن ولكن مفيد للإحصائيات)
            c.execute("UPDATE converted_files SET last_used = ? WHERE file_hash = ?", (datetime.now(), file_hash))
            conn.commit()
            
            conn.close()
            os.remove(file_path)
            return
            
        except Exception as e:
            # إذا قمت أنت بحذف الملف من المجموعة، سيتم تنفيذ هذا الجزء
            c.execute("DELETE FROM converted_files WHERE file_hash = ?", (file_hash,))
            conn.commit()
            # سيتجاهل الخطأ ويكمل لعملية التحويل من جديد
            
    bot.send_message(chat_id, "جاري التحويل... قد تستغرق العملية بضع ثوانٍ.")
    try:
        output_dir = os.path.dirname(os.path.abspath(file_path)) or "."
        command = ['libreoffice', '--headless', '--convert-to', 'pdf', file_path, '--outdir', output_dir]
        subprocess.run(command, check=True)
        
        pdf_filename = os.path.splitext(file_path)[0] + ".pdf"
        
        if os.path.exists(pdf_filename):
            with open(pdf_filename, "rb") as pdf_file:
                # 1. إرسال الملف إلى المجموعة أولاً لضمان حفظه
                group_msg = bot.send_document(GROUP_USERNAME, pdf_file, caption=f"نسخة محفوظة\nبصمة الملف: {file_hash}")
                
                # 2. أخذ المعرف السري الآمن من رسالة المجموعة وحفظه في قاعدة البيانات
                saved_file_id = group_msg.document.file_id
                c.execute("INSERT OR REPLACE INTO converted_files (file_hash, pdf_file_id, last_used) VALUES (?, ?, ?)",
                          (file_hash, saved_file_id, datetime.now()))
                conn.commit()
                
                # 3. إرسال نفس الملف للطالب بسرعة فائقة
                bot.send_document(chat_id, saved_file_id, caption="تم تحويل الملف بنجاح.")
                
            os.remove(pdf_filename)
        else:
            bot.send_message(chat_id, "فشل التحويل. تأكد من أن الملف سليم.")
            
    except Exception as e:
        bot.send_message(chat_id, "حدث خطأ أثناء التحويل. يرجى المحاولة لاحقاً.")
    finally:
        conn.close()
        if os.path.exists(file_path):
            os.remove(file_path)

# ملاحظة: يمكنك حذف دالة cleanup_old_cache من الكود القديم لأنك لن تحتاجها بعد الآن.

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
