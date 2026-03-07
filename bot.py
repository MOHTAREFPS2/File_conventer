import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from pypdf import PdfReader, PdfWriter
import os
import time
import re
import subprocess
import sqlite3
import hashlib
from datetime import datetime

# ================= الإعدادات الأساسية =================
TOKEN = "8792450275:AAH8GiaNoIySkJHDKQ4R6kLVQQ20qLedLos"
GROUP_USERNAME = "@file_of_conventor_bot"
ADMIN_ID = 5531978627

bot = telebot.TeleBot(TOKEN)
user_data = {}

# ================= الإيموجيات المميزة =================
e_star = '<tg-emoji emoji-id="5438496463044752972">⭐️</tg-emoji>'
e_pdf = '<tg-emoji emoji-id="6030802440624804868">📄</tg-emoji>'
e_file = '<tg-emoji emoji-id="5359351124996419193">📂</tg-emoji>'
e_edit = '<tg-emoji emoji-id="5334882760735598374">📝</tg-emoji>'
e_gear = '<tg-emoji emoji-id="5341715473882955310">⚙️</tg-emoji>'
e_done = '<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji>'
e_cancel = '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji>'
e_warn = '<tg-emoji emoji-id="5420323339723881652">⚠️</tg-emoji>'
e_rocket = '<tg-emoji emoji-id="5296369303661067030">🚀</tg-emoji>'

# ================= قاعدة البيانات =================
def init_db():
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    # جدول الملفات
    c.execute('''CREATE TABLE IF NOT EXISTS converted_files (file_hash TEXT PRIMARY KEY, pdf_file_id TEXT, last_used TIMESTAMP)''')
    # جدول المستخدمين للإحصائيات
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT)''')
    conn.commit()
    conn.close()

init_db()

def save_user(message):
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
              (message.from_user.id, message.from_user.first_name, message.from_user.username))
    conn.commit()
    conn.close()

def get_file_hash(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()

def cancel_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ إلغاء العملية والعودة", callback_data="cancel_action"))
    return markup

# ================= أوامر الإدارة الخاصة بك =================
@bot.message_handler(commands=['clear'])
def clear_cache(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute("DELETE FROM converted_files")
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"تم تنظيف ذاكرة التخزين المؤقت للملفات بنجاح {e_done}", parse_mode='HTML')

@bot.message_handler(commands=['stats'])
def get_stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    
    with open("users_stats.txt", "w", encoding="utf-8") as f:
        f.write("قائمة مستخدمي البوت:\n\n")
        for u in users:
            f.write(f"ID: {u[0]} | Name: {u[1]} | Username: @{u[2]}\n")
            
    with open("users_stats.txt", "rb") as doc:
        bot.send_document(message.chat.id, doc, caption=f"إحصائيات المستخدمين ({len(users)} مستخدم)")
    os.remove("users_stats.txt")

@bot.message_handler(commands=['broadcast'])
def broadcast_step1(message):
    if message.from_user.id != ADMIN_ID:
        return
    msg = bot.send_message(message.chat.id, "أرسل الرسالة التي تريد إذاعتها لجميع المستخدمين الآن:")
    bot.register_next_step_handler(msg, broadcast_step2)

def broadcast_step2(message):
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    
    success = 0
    for u in users:
        try:
            bot.send_message(u[0], message.text)
            success += 1
        except:
            pass
    bot.send_message(message.chat.id, f"تم إرسال الإذاعة إلى {success} مستخدم بنجاح {e_done}", parse_mode='HTML')

# ================= واجهة الترحيب والشرح =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    save_user(message)
    markup = InlineKeyboardMarkup(row_width=1)
    
    btn1 = InlineKeyboardButton("تحويل ملف Office إلى PDF", callback_data="office_to_pdf",style="success")
    btn2 = InlineKeyboardButton("استخراج النصوص من ملف PDF", callback_data="extract_text",style="primary")
    btn3 = InlineKeyboardButton("قص صفحات محددة من ملفات PDF", callback_data="crop_pdf",style="danger")
    markup.add(btn1, btn2, btn3)
    
    welcome_text = (
        f"أهلاً بك في البوت الأكاديمي {e_star}\n\n"
        f"<b>إليك شرح مبسط لخدمات البوت:</b>\n"
        f"1️⃣ <b>تحويل ملف Office إلى PDF:</b>\nيرفع لك ملفات (Word, PowerPoint) ويحولها لملف {e_pdf} جاهز للطباعة والقراءة بثوانٍ.\n\n"
        f"2️⃣ <b>استخراج النصوص من ملف PDF:</b>\nيستخرج لك الكلام المكتوب داخل المحاضرة بشكل نصي {e_edit} لكي تتمكن من نسخه وتعديله براحتك.\n\n"
        f"3️⃣ <b>قص صفحات محددة من ملف PDF:</b>\nيأخذ المحاضرة الطويلة ويستخرج لك منها الصفحات التي تحددها أنت فقط في ملف جديد {e_file}.\n\n"
        f"👇 <b>اختر الخدمة التي تناسبك الآن:</b>"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='HTML')

# ================= معالجة الأزرار والعمليات =================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    action = call.data
    
    if action == "cancel_action":
        bot.clear_step_handler_by_chat_id(chat_id)
        user_data.pop(chat_id, None)
        bot.edit_message_text(f"تم إلغاء العملية بنجاح {e_cancel}", chat_id, call.message.message_id, parse_mode='HTML')
        send_welcome(call.message)
        return
        
    user_data[chat_id] = {'action': action}
    
    if action == "office_to_pdf":
        msg = bot.send_message(chat_id, f"يرجى إرسال ملف Office (Word, PowerPoint, Excel) للتحويل...\n\n(لإلغاء العملية اضغط الزر أدناه)", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_file_upload)
        
    elif action in ["extract_text", "crop_pdf"]:
        caption = f"{e_warn} <b>ملاحظة هامة:</b> يجب على الطالب أن يعتمد على ترقيم برنامج الـ PDF الذي يستخدمه وليس على رقم صفحة الملف نفسه."
        try:
            with open("note.jpg", "rb") as photo:
                bot.send_photo(chat_id, photo, caption=caption, parse_mode='HTML')
        except FileNotFoundError:
            pass
            
        msg = bot.send_message(chat_id, f"يرجى إرسال ملف الـ PDF الآن...\n\n(لإلغاء العملية اضغط الزر أدناه)", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_file_upload)

def process_file_upload(message):
    chat_id = message.chat.id
    
    if not message.document:
        msg = bot.send_message(chat_id, f"الرجاء إرسال ملف صالح كـ Document {e_warn}", reply_markup=cancel_markup(), parse_mode='HTML')
        bot.register_next_step_handler(msg, process_file_upload)
        return

    file_size = message.document.file_size
    limit_mb = 20
    if file_size > limit_mb * 1024 * 1024:
        bot.send_message(chat_id, f"عذراً، حجم الملف يتجاوز الحد المسموح به ({limit_mb}MB) {e_warn}\nملاحظة: تم وضع هذا الحد بسبب حدود الموارد.", parse_mode='HTML')
        send_welcome(message)
        return

    action = user_data.get(chat_id, {}).get('action')
    status_msg = bot.send_message(chat_id, f"جاري تحميل الملف {e_gear}\n[■■□□□□□□□□] 20%", parse_mode='HTML')
    
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    original_ext = os.path.splitext(message.document.file_name)[1].lower()
    local_filename = f"file_{chat_id}_{message.message_id}{original_ext}"
    
    with open(local_filename, 'wb') as new_file:
        new_file.write(downloaded_file)
        
    user_data[chat_id]['file_path'] = local_filename

    if action == "office_to_pdf":
        bot.edit_message_text(f"تم التحميل! جاري المعالجة {e_gear}\n[■■■■□□□□□□] 40%", chat_id, status_msg.message_id, parse_mode='HTML')
        convert_office_to_pdf(chat_id, local_filename, status_msg.message_id, message)
    else:
        bot.delete_message(chat_id, status_msg.message_id)
        msg = bot.send_message(chat_id, f"تم استلام الملف بنجاح {e_done}.\nيرجى كتابة نطاق الصفحات بالصيغة التالية (مثال: من 1 الى 10):", reply_markup=cancel_markup(), parse_mode='HTML')
        bot.register_next_step_handler(msg, process_page_range)

def process_page_range(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    pattern = r"^من\s+(\d+)\s+(الى|إلى)\s+(\d+)$"
    match = re.search(pattern, text)
    
    if not match:
        msg = bot.send_message(chat_id, f"صيغة غير صحيحة! يرجى الكتابة بالضبط هكذا: من 1 الى 10 {e_warn}", reply_markup=cancel_markup(), parse_mode='HTML')
        bot.register_next_step_handler(msg, process_page_range)
        return
        
    start_page = int(match.group(1))
    end_page = int(match.group(3))
    
    if start_page > end_page or start_page < 1:
        msg = bot.send_message(chat_id, f"أرقام الصفحات غير منطقية. حاول مرة أخرى: {e_warn}", reply_markup=cancel_markup(), parse_mode='HTML')
        bot.register_next_step_handler(msg, process_page_range)
        return
        
    action = user_data.get(chat_id, {}).get('action')
    file_path = user_data.get(chat_id, {}).get('file_path')
    
    if action == "extract_text":
        extract_pdf_text(chat_id, file_path, start_page, end_page, message)
    elif action == "crop_pdf":
        crop_pdf_pages(chat_id, file_path, start_page, end_page, message)

# ================= وظائف المعالجة المركزية =================
def extract_pdf_text(chat_id, file_path, start_page, end_page, original_message):
    bot.send_message(chat_id, f"جاري استخراج النصوص (قد يستغرق الأمر بعض الوقت لتقليل الضغط) {e_gear}", parse_mode='HTML')
    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        if end_page > total_pages: end_page = total_pages
            
        extracted_text = ""
        pages_processed = 0
        start_idx, end_idx = start_page - 1, end_page - 1
        
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
            bot.send_document(chat_id, final_file, caption=f"تم استخراج النصوص بنجاح {e_done}", parse_mode='HTML')
        os.remove(txt_filename)
    except Exception as e:
        bot.send_message(chat_id, f"حدث خطأ أثناء معالجة الملف {e_warn}", parse_mode='HTML')
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        send_welcome(original_message) # العودة للقائمة

def crop_pdf_pages(chat_id, file_path, start_page, end_page, original_message):
    bot.send_message(chat_id, f"جاري قص الصفحات {e_gear}", parse_mode='HTML')
    try:
        reader = PdfReader(file_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)
        if end_page > total_pages: end_page = total_pages
            
        start_idx, end_idx = start_page - 1, end_page - 1
        for page_num in range(start_idx, end_idx + 1):
            writer.add_page(reader.pages[page_num])
            
        output_filename = f"cropped_{chat_id}.pdf"
        with open(output_filename, "wb") as output_pdf:
            writer.write(output_pdf)
            
        with open(output_filename, "rb") as final_pdf:
            bot.send_document(chat_id, final_pdf, caption=f"تم قص الصفحات من {start_page} إلى {end_page} {e_done}", parse_mode='HTML')
        os.remove(output_filename)
    except Exception as e:
        bot.send_message(chat_id, f"حدث خطأ أثناء قص الملف {e_warn}", parse_mode='HTML')
    finally:
        if os.path.exists(file_path): os.remove(file_path)
        send_welcome(original_message) # العودة للقائمة

def convert_office_to_pdf(chat_id, file_path, msg_id, original_message):
    file_hash = get_file_hash(file_path)
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute("SELECT pdf_file_id FROM converted_files WHERE file_hash = ?", (file_hash,))
    result = c.fetchone()
    
    if result:
        pdf_file_id = result[0]
        bot.edit_message_text(f"تم العثور على الملف مسبقاً! جاري إرساله فوراً {e_rocket}\n[■■■■■■■■■■] 100%", chat_id, msg_id, parse_mode='HTML')
        try:
            bot.send_document(chat_id, pdf_file_id, caption=f"تم التحويل والإرسال بلمح البصر (نسخة محفوظة) {e_done}", parse_mode='HTML')
            c.execute("UPDATE converted_files SET last_used = ? WHERE file_hash = ?", (datetime.now(), file_hash))
            conn.commit()
            conn.close()
            os.remove(file_path)
            send_welcome(original_message)
            return
        except Exception as e:
            c.execute("DELETE FROM converted_files WHERE file_hash = ?", (file_hash,))
            conn.commit()
            
    bot.edit_message_text(f"يتم الآن تحويل الصيغة عبر المحرك {e_gear}\n[■■■■■■□□□□] 60%", chat_id, msg_id, parse_mode='HTML')
    try:
        output_dir = os.path.dirname(os.path.abspath(file_path)) or "."
        command = ['libreoffice', '--headless', '--convert-to', 'pdf', file_path, '--outdir', output_dir]
        subprocess.run(command, check=True)
        
        pdf_filename = os.path.splitext(file_path)[0] + ".pdf"
        
        if os.path.exists(pdf_filename):
            bot.edit_message_text(f"اكتمل التحويل! جاري رفع الملف {e_done}\n[■■■■■■■■■■] 100%", chat_id, msg_id, parse_mode='HTML')
            with open(pdf_filename, "rb") as pdf_file:
                group_msg = bot.send_document(GROUP_USERNAME, pdf_file, caption=f"نسخة محفوظة\nبصمة الملف: {file_hash}")
                saved_file_id = group_msg.document.file_id
                
                c.execute("INSERT OR REPLACE INTO converted_files (file_hash, pdf_file_id, last_used) VALUES (?, ?, ?)",
                          (file_hash, saved_file_id, datetime.now()))
                conn.commit()
                bot.send_document(chat_id, saved_file_id, caption=f"تم تحويل الملف بنجاح {e_pdf}", parse_mode='HTML')
            os.remove(pdf_filename)
        else:
            bot.send_message(chat_id, f"فشل التحويل. تأكد من أن الملف سليم {e_warn}", parse_mode='HTML')
    except Exception as e:
        bot.send_message(chat_id, f"حدث خطأ أثناء التحويل. يرجى المحاولة لاحقاً {e_warn}", parse_mode='HTML')
    finally:
        conn.close()
        if os.path.exists(file_path): os.remove(file_path)
        send_welcome(original_message) # العودة للقائمة

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
