import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from pypdf import PdfReader, PdfWriter
import os
import time
import re
import subprocess
import sqlite3
import hashlib
import json
from PIL import Image
from datetime import datetime

# ================= الإعدادات الأساسية =================
TOKEN = "8628116455:AAFIP2HFgxHm_HiXg6cBnPp7jaJXqr5NA4s"
GROUP_USERNAME = "@file_of_conventor_bot"
ADMIN_ID = 5531978627

bot = telebot.TeleBot(TOKEN)
user_data = {}

# ================= الإيموجيات المميزة =================
def load_custom_emojis(filepath="custom_emojis.json"):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"تحذير: حدث خطأ في ملف الإيموجيات أو غير موجود: {e}")
        return {}

EMOJIS_DICT = load_custom_emojis()

def apply_custom_emojis(text):
    if not EMOJIS_DICT or not isinstance(text, str):
        return text
    for std_emoji, emoji_id in EMOJIS_DICT.items():
        if std_emoji in text:
            custom_tag = f'<tg-emoji emoji-id="{emoji_id}">{std_emoji}</tg-emoji>'
            text = text.replace(std_emoji, custom_tag)
    return text

# ================= فلتر الرسائل الشامل (Monkey Patching) =================
original_send_message      = bot.send_message
original_edit_message_text = bot.edit_message_text
original_send_document     = bot.send_document

def patched_send_message(chat_id, text, **kwargs):
    kwargs['parse_mode'] = 'HTML'
    return original_send_message(chat_id, apply_custom_emojis(text), **kwargs)

def patched_edit_message_text(text, chat_id=None, message_id=None, inline_message_id=None, **kwargs):
    kwargs['parse_mode'] = 'HTML'
    return original_edit_message_text(
        apply_custom_emojis(text),
        chat_id=chat_id,
        message_id=message_id,
        inline_message_id=inline_message_id,
        **kwargs
    )

def patched_send_document(chat_id, document, **kwargs):
    if kwargs.get('caption'):
        kwargs['caption'] = apply_custom_emojis(kwargs['caption'])
        kwargs['parse_mode'] = 'HTML'
    return original_send_document(chat_id, document, **kwargs)

bot.send_message      = patched_send_message
bot.edit_message_text = patched_edit_message_text
bot.send_document     = patched_send_document

# ================= قاعدة البيانات =================
def init_db():
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS converted_files
                 (file_hash TEXT PRIMARY KEY, pdf_file_id TEXT, last_used TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT)''')
    conn.commit()
    conn.close()

init_db()

def save_user(message):
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
        (message.from_user.id, message.from_user.first_name, message.from_user.username)
    )
    conn.commit()
    conn.close()

def get_file_hash(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

# ================= لوحات الأزرار =================
def cancel_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("❌ إلغاء العملية والعودة", callback_data="cancel_action",style="danger"))
    return markup
    
    # بعد file_action_markup وقبل send_main_menu
def remove_keyboard(chat_id, message_id):
    try:
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=None)
    except Exception:
        pass

def file_action_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✏️ تغيير الاسم", callback_data="pre_rename_yes",style="primary"),
        InlineKeyboardButton("✅ ابقَ كما هو",  callback_data="start_new",style="success")
    )
    return markup

def file_result_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✏️ تغيير الاسم", callback_data="rename_file",style="primary"),
        InlineKeyboardButton("✅بدء عملية جديدة",  callback_data="start_new",style="success")
    )
    return markup
def ask_rename_before_action_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✏️ تغيير الاسم", callback_data="pre_rename_yes",style="primary"),
        InlineKeyboardButton("✅ أبقه كما هو",  callback_data="pre_rename_no",style="primary")
    )
    markup.add(InlineKeyboardButton("❌ إلغاء", callback_data="cancel_action",style="danger"))
    return markup

def pdf_format_markup():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📄 أبعاد A4 (تُجبر لتصبح عمودية)", callback_data="format_a4",style="primary"),
        InlineKeyboardButton("🖥 أبعاد 16:9 (تُجبر لتصبح أفقية)", callback_data="format_16_9",style="primary"),
        InlineKeyboardButton("🖼 أبعاد أصلية (بدون تغيير بالقياسات)", callback_data="format_original",style="primary"),
        InlineKeyboardButton("❌ إلغاء العملية", callback_data="cancel_action",style="danger")
    )
    return markup

# ================= القائمة الرئيسية =================
def send_main_menu(chat_id, is_success=False):
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📄 تحويل ملف Office إلى PDF",         callback_data="office_to_pdf",style="success"),
        InlineKeyboardButton("📝 استخراج النصوص من ملف PDF",        callback_data="extract_text",style="primary"),
        InlineKeyboardButton("✂️ قص صفحات محددة من ملفات PDF",      callback_data="crop_pdf",style="danger"),
        InlineKeyboardButton("🖼 تحويل الصور إلى PDF", callback_data="images_to_pdf",style="success"),
        InlineKeyboardButton("🛠 الإبلاغ عن مشكلة", callback_data="report_problem",style="primary")
    )
    if is_success:
        text = "✅ <b>تمت العملية بنجاح، هل هناك مهمة أخرى تود القيام بها؟</b> 👇"
    else:
                text = (
            "أهلاً بك في البوت الأكاديمي ⭐️\n"
            "رفيقك الذكي لإنجاز مهامك بسرعة واحترافية!\n\n"
            "<b>إليك شرح مبسط لخدمات البوت:</b>\n"
            "1️⃣ <b>تحويل ملف Office إلى PDF:</b>\nيرفع ملفات (Word, PowerPoint) ويحولها لملف 📄 جاهز للطباعة والمذاكرة بثوانٍ.\n\n"
            "2️⃣ <b>تحويل الصور إلى PDF:</b>\nيجمع صور السلايدات أو صفحات الكتب في ملف واحد 🖼، مع القدرة على ضبط وتوحيد أبعاد الصفحات (A4 أو 16:9).\n\n"
            "3️⃣ <b>استخراج النصوص من ملف PDF:</b>\nيستخرج الكلام المكتوب داخل المحاضرة بشكل نصي 📝 لكي تتمكن من نسخه، تعديله، أو ترجمته براحتك.\n\n"
            "4️⃣ <b>قص صفحات من ملف PDF:</b>\nيأخذ المحاضرة الطويلة ويقتطع لك منها الصفحات المهمة فقط في ملف جديد ✂️.\n\n"
            "5️⃣ <b>الإبلاغ عن مشكلة:</b> قناة تواصل مباشرة لإيصال ملاحظاتك للمطور لضمان أفضل تجربة.\n\n"
            "👇 <b>اختر الخدمة التي تحتاجها الآن:</b>"
        )

    bot.send_message(chat_id, text, reply_markup=markup)

# ================= أوامر الإدارة =================
@bot.message_handler(commands=['start'])
def start_command(message):
    save_user(message)
    send_main_menu(message.chat.id, is_success=False)

@bot.message_handler(commands=['clear'])
def clear_cache(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute("DELETE FROM converted_files")
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "✅ تم تنظيف ذاكرة التخزين المؤقت بنجاح.")

@bot.message_handler(commands=['stats'])
def get_stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('bot_cache.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    filename = "users_stats.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("قائمة مستخدمي البوت:\n\n")
        for u in users:
            f.write(f"ID: {u[0]} | Name: {u[1]} | Username: @{u[2]}\n")
    with open(filename, "rb") as doc:
        bot.send_document(message.chat.id, doc, caption=f"إحصائيات المستخدمين ({len(users)} مستخدم)")
    os.remove(filename)

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
        except Exception:
            pass
    bot.send_message(message.chat.id, f"✅ تم إرسال الإذاعة إلى {success} مستخدم بنجاح.")

#ازرار عادية مالت الكيبورد
@bot.message_handler(func=lambda message: message.text in ["✅ إنهاء وإنشاء الـ PDF", "❌ إلغاء العملية"])
def handle_keyboard_buttons(message):
    chat_id = message.chat.id

    if message.text == "✅ إنهاء وإنشاء الـ PDF":
        images = user_data.get(chat_id, {}).get('images', [])
        if not images:
            bot.send_message(chat_id, "⚠️ لم تقم بإرسال أي صور بعد!")
            return
            
        # إخفاء الكيبورد برسالة مؤقتة
        hide_msg = bot.send_message(chat_id, "⚙️ جاري تجهيز الخيارات...", reply_markup=ReplyKeyboardRemove())
        bot.delete_message(chat_id, hide_msg.message_id)
        
        text = (
            "ممتاز! تم استلام الصور بنجاح ✅\n\n"
            "<b>الآن، اختر أبعاد صفحات ملف الـ PDF الذي تريده:</b>\n\n"
            "📄 <b>أبعاد A4:</b> سيتم مط الصورة لتملأ صفحة A4 (ممتاز للملازم والصفحات العمودية).\n"
            "🖥 <b>أبعاد 16:9:</b> سيتم مط الصورة لتصبح بالعرض (ممتاز لسلايدات المحاضرات).\n"
            "🖼 <b>أبعاد أصلية:</b> ستبقى كل صورة بحجمها الحقيقي (ممتاز إذا كانت الصور غير متطابقة).\n\n"
            "👇 <b>اختر التنسيق المناسب لك:</b>"
        )
        bot.send_message(chat_id, text, reply_markup=pdf_format_markup())

    elif message.text == "❌ إلغاء العملية":
        bot.clear_step_handler_by_chat_id(chat_id)
        user_data.pop(chat_id, None)
        bot.send_message(chat_id, "❌ تم إلغاء العملية بنجاح.", reply_markup=ReplyKeyboardRemove())
        send_main_menu(chat_id)

        
# ================= معالجة أزرار الاستدعاء =================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    action  = call.data

    # ← أضف هذا السطر هنا
    remove_keyboard(chat_id, call.message.message_id)
    
    if action == "report_problem":
        msg = bot.send_message(
            chat_id,
            "🛠 <b>الإبلاغ عن مشكلة:</b>\n\nيرجى كتابة وصف دقيق للمشكلة التي واجهتك، وسأقوم بإرسالها للمطور فوراً:\n\n(لإلغاء العملية اضغط الزر أدناه)",
            reply_markup=cancel_markup()
        )
        bot.register_next_step_handler(msg, process_report_problem)
        return
        
    
    if action == "images_to_pdf":
        user_data[chat_id] = {'action': 'collect_images', 'images': []}
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("✅ إنهاء وإنشاء الـ PDF"))
        markup.add(KeyboardButton("❌ إلغاء العملية"))
        bot.send_message(
            chat_id,
            "🖼 <b>أرسل الصور الآن...</b>\n\nيمكنك إرسال صورة واحدة أو تحديد عدة صور وإرسالها معاً كألبوم.\nعندما تنتهي من إرسال <b>كل</b> الصور، اضغط على زر <b>إنهاء وإنشاء الـ PDF</b> في الأسفل⬇️",
            reply_markup=markup
        )
        return
        
    if action in ["format_a4", "format_16_9", "format_original"]:
        bot.edit_message_text("⚙️ جاري معالجة الصور وتكوين ملف الـ PDF...", chat_id, call.message.message_id)
        process_images_to_pdf(chat_id, action) # نرسل التنسيق المختار إلى الدالة
        return
        
    # ── إلغاء العملية ──
    if action == "cancel_action":
        bot.clear_step_handler_by_chat_id(chat_id)
        user_data.pop(chat_id, None)
        bot.edit_message_text("❌ تم إلغاء العملية بنجاح.", chat_id, call.message.message_id)
        send_main_menu(chat_id, is_success=False)
        return
        
    # ── بدء عملية جديدة ──
    if action == "start_new":
        user_data.pop(chat_id, None)
        send_main_menu(chat_id, is_success=True)
        return

    # ── اختيار تغيير الاسم قبل العملية ──
    if action == "pre_rename_yes":
        msg = bot.send_message(
            chat_id,
            "✏️ أرسل الاسم الجديد للملف:\n(الامتداد سيُضاف تلقائياً)",
            reply_markup=cancel_markup()
        )
        bot.register_next_step_handler(msg, process_pre_rename)
        return

    # ── الإبقاء على الاسم كما هو ──
    if action == "pre_rename_no":
        run_main_action(chat_id)
        return

    # ── إعادة تسمية الملف بعد العملية ──
    if action == "rename_file":
        if not call.message.document:
            bot.answer_callback_query(call.id, "⚠️ لم يتم العثور على الملف.")
            return
        file_id  = call.message.document.file_id
        old_name = call.message.document.file_name
        user_data[chat_id] = {'action': 'rename_file', 'rename_file_id': file_id, 'old_name': old_name}
        msg = bot.send_message(
            chat_id,
            f"الاسم الحالي: <b>{old_name}</b>\n\nأرسل الاسم الجديد للملف:\n(سيتم ضبط الصيغة تلقائياً)",
            reply_markup=cancel_markup()
        )
        bot.register_next_step_handler(msg, process_rename_file)
        return

    # ── العمليات الرئيسية ──
    user_data[chat_id] = {'action': action}

    if action == "office_to_pdf":
        msg = bot.send_message(
            chat_id,
            "يرجى إرسال ملف Office (Word, PowerPoint, Excel) للتحويل...\n\n(لإلغاء العملية اضغط الزر أدناه)",
            reply_markup=cancel_markup()
        )
        bot.register_next_step_handler(msg, process_file_upload)

    elif action in ("extract_text", "crop_pdf"):
        caption = "⚠️ <b>ملاحظة هامة:</b> اعتمد على ترقيم برنامج الـ PDF وليس على رقم الصفحة المطبوع في الملف."
        try:
            with open("note.jpg", "rb") as photo:
                bot.send_photo(chat_id, photo, caption=caption, parse_mode='HTML')
        except FileNotFoundError:
            pass
        msg = bot.send_message(
            chat_id,
            "يرجى إرسال ملف الـ PDF الآن...\n\n(لإلغاء العملية اضغط الزر أدناه)",
            reply_markup=cancel_markup()
        )
        bot.register_next_step_handler(msg, process_file_upload)

# ================= معالجة التقاط الصور =================
@bot.message_handler(content_types=['photo', 'document'], func=lambda message: user_data.get(message.chat.id, {}).get('action') == 'collect_images')
def handle_photo_collection(message):
    chat_id = message.chat.id
    try:
        # تحديد ما إذا كانت صورة عادية أو صورة مرسلة كملف للحفاظ على الدقة
        if message.photo:
            file_id = message.photo[-1].file_id # اختيار أعلى دقة للصورة
            ext = ".jpg"
        elif message.document and message.document.mime_type.startswith('image/'):
            file_id = message.document.file_id
            ext = os.path.splitext(message.document.file_name)[1]
        else:
            return # تجاهل أي رسالة ليست صورة

        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        local_filename = f"img_{chat_id}_{message.message_id}{ext}"

        with open(local_filename, 'wb') as f:
            f.write(downloaded_file)

        # إضافة مسار الصورة إلى قائمة الطالب
        user_data[chat_id]['images'].append(local_filename)
        
    except Exception as e:
        print(f"Error saving image: {e}")

# ================= معالجة رفع الملفات =================
def process_file_upload(message):
    chat_id = message.chat.id

    if not message.document:
        msg = bot.send_message(chat_id, "⚠️ الرجاء إرسال ملف صالح كـ Document.", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_file_upload)
        return

    if message.document.file_size > 100 * 1024 * 1024:
        bot.send_message(chat_id, "⚠️ حجم الملف يتجاوز الحد المسموح به (100 MB).")
        return

    status_msg = bot.send_message(chat_id, "⚙️ جاري تحميل الملف...\n[■■□□□□□□□□] 20%")

    file_info       = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    original_ext    = os.path.splitext(message.document.file_name)[1].lower()
    local_filename  = f"file_{chat_id}_{message.message_id}{original_ext}"

    with open(local_filename, 'wb') as f:
        f.write(downloaded_file)

    # حفظ مسار الملف واسمه الأصلي
    user_data[chat_id]['file_path']     = local_filename
    user_data[chat_id]['original_name'] = message.document.file_name

    # بعد التحميل → اسأل المستخدم عن الاسم أولاً
    bot.delete_message(chat_id, status_msg.message_id)
    ask_rename_before_action(chat_id)

def ask_rename_before_action(chat_id):
    current_name = user_data.get(chat_id, {}).get('original_name', 'الملف')
    bot.send_message(
        chat_id,
        f"📄 الاسم الحالي للملف: <b>{current_name}</b>\n\n"
        f"هل تريد تغيير اسم الملف <b>قبل</b> تنفيذ العملية؟",
        reply_markup=ask_rename_before_action_markup()
    )

# ================= معالجة الاسم الجديد (قبل العملية) =================
def process_pre_rename(message):
    chat_id  = message.chat.id
    new_name = message.text.strip()
    old_name = user_data.get(chat_id, {}).get('original_name', '')
    ext      = os.path.splitext(old_name)[1]

    if not new_name.lower().endswith(ext.lower()):
        new_name += ext

    user_data.setdefault(chat_id, {})['final_name'] = new_name
    bot.send_message(chat_id, f"✅ سيتم حفظ الملف باسم: <b>{new_name}</b>")
    run_main_action(chat_id)

# ================= تنفيذ العملية الأصلية =================
def run_main_action(chat_id):
    action    = user_data.get(chat_id, {}).get('action')
    file_path = user_data.get(chat_id, {}).get('file_path')

    if action == "office_to_pdf":
        status_msg = bot.send_message(chat_id, "⚙️ جاري التحويل...\n[■■■■□□□□□□] 40%")
        convert_office_to_pdf(chat_id, file_path, status_msg.message_id)

    elif action in ("extract_text", "crop_pdf"):
        msg = bot.send_message(
            chat_id,
            "✅ تم. أرسل نطاق الصفحات:\n<b>مثال: من 1 الى 10</b>",
            reply_markup=cancel_markup()
        )
        bot.register_next_step_handler(msg, process_page_range)

# ================= معالجة نطاق الصفحات =================
def process_page_range(message):
    chat_id = message.chat.id
    text    = message.text.strip()
    pattern = r"^من\s+(\d+)\s+(الى|إلى)\s+(\d+)$"
    match   = re.search(pattern, text)

    if not match:
        msg = bot.send_message(
            chat_id,
            "⚠️ صيغة غير صحيحة! يرجى الكتابة هكذا:\n<b>من 1 الى 10</b>",
            reply_markup=cancel_markup()
        )
        bot.register_next_step_handler(msg, process_page_range)
        return

    start_page = int(match.group(1))
    end_page   = int(match.group(3))

    if start_page < 1 or start_page > end_page:
        msg = bot.send_message(chat_id, "⚠️ أرقام الصفحات غير منطقية. حاول مرة أخرى.", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_page_range)
        return

    action    = user_data.get(chat_id, {}).get('action')
    file_path = user_data.get(chat_id, {}).get('file_path')

    if action == "extract_text":
        extract_pdf_text(chat_id, file_path, start_page, end_page)
    elif action == "crop_pdf":
        crop_pdf_pages(chat_id, file_path, start_page, end_page)
        
# ================= معالجة بلاغات المستخدمين =================
def process_report_problem(message):
    chat_id = message.chat.id
    report_text = message.text

    if not report_text:
        msg = bot.send_message(chat_id, "⚠️ يرجى إرسال نص يشرح المشكلة.", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_report_problem)
        return

    try:
        # تجميع البلاغ بشكل أنيق للمطور
        admin_msg = (
            f"🚨 <b>تقرير مشكلة جديد:</b>\n\n"
            f"👤 <b>من:</b> {message.from_user.first_name} (@{message.from_user.username or 'بدون يوزر'})\n"
            f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n\n"
            f"📝 <b>المشكلة:</b>\n{report_text}"
        )
        # إرسال الرسالة إلى الـ ADMIN_ID الخاص بك
        bot.send_message(ADMIN_ID, admin_msg)
        
        bot.send_message(chat_id, "✅ تم إرسال بلاغك للمطور بنجاح. شكراً لمساهمتك في تحسين البوت!")
    except Exception as e:
        print(f"[report_error] {e}")
        bot.send_message(chat_id, "⚠️ حدث خطأ أثناء إرسال البلاغ، يرجى المحاولة لاحقاً.")
    
    send_main_menu(chat_id)


# ================= معالجة إعادة التسمية (بعد العملية) =================
def process_rename_file(message):
    chat_id  = message.chat.id
    new_name = message.text.strip()
    file_id  = user_data.get(chat_id, {}).get('rename_file_id')
    old_name = user_data.get(chat_id, {}).get('old_name')

    if not file_id:
        bot.send_message(chat_id, "⚠️ حدث خطأ، يرجى المحاولة من جديد.")
        send_main_menu(chat_id)
        return

    ext = os.path.splitext(old_name)[1]
    if not new_name.lower().endswith(ext.lower()):
        new_name += ext

    status_msg = bot.send_message(chat_id, "⚙️ جاري تحديث اسم الملف...")
    try:
        file_info       = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(new_name, 'wb') as f:
            f.write(downloaded_file)
        bot.delete_message(chat_id, status_msg.message_id)
        with open(new_name, 'rb') as final_file:
            bot.send_document(
                chat_id, final_file,
                caption=f"✅ تمت إعادة التسمية بنجاح.\nالاسم الجديد: <b>{new_name}</b>",
                reply_markup=file_action_markup()
            )
        os.remove(new_name)
    except Exception as e:
        print(f"[rename_error] {e}")
        bot.edit_message_text("⚠️ حدث خطأ أثناء تغيير الاسم.", chat_id, status_msg.message_id)
    finally:
        user_data.pop(chat_id, None)

# ================= وظائف المعالجة المركزية =================
def extract_pdf_text(chat_id, file_path, start_page, end_page):
    bot.send_message(chat_id, "⚙️ جاري استخراج النصوص (قد يستغرق بعض الوقت)...")
    try:
        reader      = PdfReader(file_path)
        total_pages = len(reader.pages)
        end_page    = min(end_page, total_pages)
        extracted   = ""
        for i, page_num in enumerate(range(start_page - 1, end_page)):
            text = reader.pages[page_num].extract_text()
            if text:
                extracted += f"\n--- صفحة {page_num + 1} ---\n{text}\n"
            if (i + 1) % 5 == 0 and page_num != end_page - 1:
                time.sleep(3)
        final_name = user_data.get(chat_id, {}).get('final_name') or f"extracted_{chat_id}.txt"
        out_file = final_name if final_name.endswith('.txt') else final_name + '.txt'
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(extracted)
        with open(out_file, "rb") as final_file:
            bot.send_document(chat_id, final_file, caption="✅ تم استخراج النصوص بنجاح.", reply_markup=file_result_markup())
        os.remove(out_file)
    except Exception as e:
        print(f"[extract_error] {e}")
        bot.send_message(chat_id, "⚠️ حدث خطأ أثناء معالجة الملف.")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        user_data.pop(chat_id, None)
        

def crop_pdf_pages(chat_id, file_path, start_page, end_page):
    bot.send_message(chat_id, "⚙️ جاري قص الصفحات...")
    try:
        reader      = PdfReader(file_path)
        writer      = PdfWriter()
        total_pages = len(reader.pages)
        end_page    = min(end_page, total_pages)
        for page_num in range(start_page - 1, end_page):
            writer.add_page(reader.pages[page_num])
        final_name = user_data.get(chat_id, {}).get('final_name') or f"cropped_{chat_id}.pdf"
        out_file = final_name if final_name.endswith('.pdf') else final_name + '.pdf'
        with open(out_file, "wb") as f:
            writer.write(f)
        with open(out_file, "rb") as final_pdf:
            bot.send_document(
                chat_id, final_pdf,
                caption=f"✅ تم قص الصفحات من {start_page} إلى {end_page} بنجاح.",
                reply_markup=file_result_markup()
            )
        os.remove(out_file)
    except Exception as e:
        print(f"[crop_error] {e}")
        bot.send_message(chat_id, "⚠️ حدث خطأ أثناء قص الملف.")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        user_data.pop(chat_id, None)


def convert_office_to_pdf(chat_id, file_path, msg_id):
    file_hash = get_file_hash(file_path)
    conn = sqlite3.connect('bot_cache.db')
    c    = conn.cursor()
    try:
        c.execute("SELECT pdf_file_id FROM converted_files WHERE file_hash = ?", (file_hash,))
        result = c.fetchone()
        if result:
            pdf_file_id = result[0]
            bot.edit_message_text("🚀 تم العثور على الملف مسبقاً! جاري إرساله...\n[■■■■■■■■■■] 100%", chat_id, msg_id)
            try:
                bot.send_document(chat_id, pdf_file_id, caption="✅ تم الإرسال بلمح البصر (نسخة محفوظة).", reply_markup=file_action_markup())
                c.execute("UPDATE converted_files SET last_used = ? WHERE file_hash = ?", (datetime.now(), file_hash))
                conn.commit()
                return
            except Exception:
                c.execute("DELETE FROM converted_files WHERE file_hash = ?", (file_hash,))
                conn.commit()

        bot.edit_message_text("⚙️ جاري تحويل الصيغة...\n[■■■■■■□□□□] 60%", chat_id, msg_id)
        output_dir = os.path.dirname(os.path.abspath(file_path)) or "."
        subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'pdf', file_path, '--outdir', output_dir],
            check=True, timeout=120
        )
        pdf_filename = os.path.splitext(file_path)[0] + ".pdf"

        if not os.path.exists(pdf_filename):
            bot.send_message(chat_id, "⚠️ فشل التحويل. تأكد من أن الملف سليم.")
            return

        bot.edit_message_text("✅ اكتمل التحويل! جاري رفع الملف...\n[■■■■■■■■■■] 100%", chat_id, msg_id)

        # استخدام الاسم المخصص إن وُجد
        final_name = user_data.get(chat_id, {}).get('final_name')

        # استخدام الاسم المخصص إن وُجد
        final_name = user_data.get(chat_id, {}).get('final_name')

        with open(pdf_filename, "rb") as pdf_file:
            group_msg     = bot.send_document(GROUP_USERNAME, pdf_file, caption=f"نسخة محفوظة | بصمة: {file_hash}")
            saved_file_id = group_msg.document.file_id

        c.execute(
            "INSERT OR REPLACE INTO converted_files (file_hash, pdf_file_id, last_used) VALUES (?, ?, ?)",
            (file_hash, saved_file_id, datetime.now())
        )
        conn.commit()

        caption = f"📄 تم تحويل الملف بنجاح."
        if final_name:
            caption += f"\nالاسم: <b>{final_name}</b>"

        bot.send_document(chat_id, saved_file_id, caption=caption, reply_markup=file_action_markup())
        os.remove(pdf_filename)

    except subprocess.TimeoutExpired:
        bot.send_message(chat_id, "⚠️ انتهت مهلة التحويل. يرجى المحاولة بملف أصغر.")
    except Exception as e:
        print(f"[convert_error] {e}")
        bot.send_message(chat_id, "⚠️ حدث خطأ أثناء التحويل. يرجى المحاولة لاحقاً.")
    finally:
        conn.close()
        if os.path.exists(file_path):
            os.remove(file_path)
        user_data.pop(chat_id, None)

def process_images_to_pdf(chat_id, format_type="format_original"):
    images_paths = user_data.get(chat_id, {}).get('images', [])
    if not images_paths:
        return

    try:
        image_list = []
        for path in images_paths:
            img = Image.open(path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
                
            # الجوهر: تغيير الأبعاد بالإجبار (مط الصورة)
            if format_type == "format_a4":
                img = img.resize((1240, 1754), Image.Resampling.LANCZOS)
            elif format_type == "format_16_9":
                img = img.resize((1920, 1080), Image.Resampling.LANCZOS)
            # إذا كان الخيار format_original، تبقى الصورة كما هي وتُضاف للقائمة

            image_list.append(img)

        if image_list:
            pdf_filename = f"Images_to_PDF_{chat_id}_{int(time.time())}.pdf"
            
            image_list[0].save(pdf_filename, save_all=True, append_images=image_list[1:])

            with open(pdf_filename, 'rb') as final_pdf:
                bot.send_document(
                    chat_id,
                    final_pdf,
                    caption="✅ تم تجميع الصور وتنسيقها في ملف PDF بنجاح.",
                    reply_markup=file_result_markup()
                )
            os.remove(pdf_filename)

    except Exception as e:
        print(f"[images_to_pdf_error] {e}")
        bot.send_message(chat_id, "⚠️ حدث خطأ أثناء تكوين ملف الـ PDF.")
    finally:
        for path in images_paths:
            if os.path.exists(path):
                os.remove(path)
        user_data.pop(chat_id, None)

# ================= تشغيل البوت =================
if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()