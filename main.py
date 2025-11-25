# ==============================
# 📦 استيراد المكتبات المطلوبة
# ==============================
import logging
import re
import phonenumbers
import json  
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext, CallbackQueryHandler
from telegram import ReplyKeyboardRemove
import random
import string
import os
import urllib.parse
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import secrets

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_database_config():
    """الحصول على إعدادات قاعدة البيانات من متغيرات البيئة"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Parse PostgreSQL URL
        parsed_url = urllib.parse.urlparse(database_url)
        
        return {
            'dbname': parsed_url.path[1:],
            'user': parsed_url.username,
            'password': parsed_url.password,
            'host': parsed_url.hostname,
            'port': parsed_url.port,
            'environment': 'render'
        }
    else:
        # للاستخدام المحلي (إذا لزم الأمر)
        return {
            'dbname': 'telegram_bot',
            'user': 'postgres',
            'password': 'password',
            'host': 'localhost',
            'port': 5432,
            'environment': 'local'
        }

def create_connection():
    """إنشاء اتصال بقاعدة البيانات - نسخة محسنة"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            config = get_database_config()
            conn = psycopg2.connect(
                dbname=config['dbname'],
                user=config['user'],
                password=config['password'],
                host=config['host'],
                port=config['port'],
                connect_timeout=10
            )
            logger.info(f"✅ تم الاتصال بقاعدة البيانات (محاولة {attempt + 1})")
            return conn
        except Exception as e:
            logger.error(f"❌ فشل الاتصال بقاعدة البيانات (محاولة {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2)
    
    logger.error("❌ فشل جميع محاولات الاتصال بقاعدة البيانات")
    return None

# ==============================
# 🤖 إعدادات البوت لـ Render
# ==============================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN غير معين في متغيرات البيئة")

OWNER_USER_ID = int(os.environ.get('OWNER_USER_ID', 0))
TELEGRAM_OWNER_ID = int(os.environ.get('TELEGRAM_OWNER_ID', 0))
ALLOWED_USER_IDS = [OWNER_USER_ID, TELEGRAM_OWNER_ID] if OWNER_USER_ID and TELEGRAM_OWNER_ID else []

# ==============================
# 🎯 تعريف مراحل المحادثة (States)
# ==============================

(
    REFERRAL_STAGE,       # 0: مرحلة كود الدعوة
    FULL_NAME,            # 1: مرحلة الاسم الكامل
    COUNTRY,              # 2: مرحلة اختيار البلد
    GENDER,               # 3: مرحلة اختيار الجنس
    BIRTH_YEAR,           # 4: مرحلة سنة الولادة
    PHONE,                # 5: مرحلة رقم الهاتف
    EMAIL,                # 6: مرحلة البريد الإلكتروني
    SOCIAL_MEDIA_MENU,    # 7: قائمة وسائل التواصل
    FACEBOOK_URL,         # 8: إدخال رابط الفيسبوك
    INSTAGRAM_URL,        # 9: إدخال رابط الانستغرام
    YOUTUBE_URL,          # 10: إدخال رابط يوتيوب
    OTHER_SOCIAL_MEDIA,   # 11: إدخال وسائل تواصل أخرى
    PAYMENT_METHOD,       # 12: اختيار طريقة الدفع
    WALLET_TYPE,          # 13: اختيار نوع المحفظة
    WALLET_ADDRESS,       # 14: إدخال عنوان المحفظة
    NEW_WALLET_TYPE,      # 15: إدخال نوع محفظة جديدة
    TRANSFER_DETAILS,     # 16: تفاصيل الحوالة المالية
    TRANSFER_PHONE,       # 17: هاتف مستلم الحوالة
    TRANSFER_LOCATION,    # 18: موقع استلام الحوالة
    TRANSFER_COMPANY,     # 19: شركة الحوالة
    CONFIRMATION,         # 20: تأكيد البيانات
    EDIT_CHOICE,          # 21: اختيار التعديل
    EDIT_FULL_NAME,       # 22: تعديل الاسم
    EDIT_COUNTRY,         # 23: تعديل البلد
    EDIT_GENDER,          # 24: تعديل الجنس
    EDIT_BIRTH_YEAR,      # 25: تعديل سنة الولادة
    EDIT_PHONE,           # 26: تعديل الهاتف
    EDIT_EMAIL,           # 27: تعديل البريد الإلكتروني
    EDIT_SOCIAL_MEDIA,    # 28: تعديل وسائل التواصل
    EDIT_PAYMENT_METHOD   # 29: تعديل طريقة الدفع
) = range(30)

# ==============================
# 🌍 قائمة البلدان ورموز الهاتف
# ==============================
COUNTRIES = {
    "السعودية": "+966", "مصر": "+20", "سوريا": "+963", "الأردن": "+962",
    "الإمارات": "+971", "الكويت": "+965", "قطر": "+974", "عمان": "+968",
    "البحرين": "+973", "لبنان": "+961", "العراق": "+964", "الجزائر": "+213",
    "المغرب": "+212", "تونس": "+216", "السودان": "+249", "اليمن": "+967"
}

# ==============================
# 💼 أنواع المحافظ الإلكترونية
# ==============================
ELECTRONIC_WALLETS = [
    "PayPal", "Payeer", "Perfect Money", "Skrill", "Neteller", "WebMoney",
    "فودافون كاش", "أورانج موني", "اتصالات كاش", "زين كاش"
]
# قائمة منفصلة للخيار الإضافي
WALLET_CHOICES = ELECTRONIC_WALLETS + ["محفظة أخرى"]

# ==============================
# 🏢 شركات الحوالات المالية
# ==============================
TRANSFER_COMPANIES = [
    "Western Union", "MoneyGram", "البنك الأهلي", "البنك السعودي الفرنسي",
    "بنك الرياض", "البنك العربي", "الهرم", "الفؤاد", "شركة أخرى"
]

# ==============================
# 🗃️ دوال قاعدة البيانات
# ==============================

def setup_database():
    """إنشاء الجداول المطلوبة في قاعدة البيانات"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        # جدول المستخدمين الرئيسي
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id BIGINT PRIMARY KEY,
                telegram_username VARCHAR(100),
                email VARCHAR(255),
                referral_code VARCHAR(20) UNIQUE,
                invited_by VARCHAR(20),
                full_name VARCHAR(200),
                country VARCHAR(100),
                gender VARCHAR(10),
                birth_year INTEGER,
                phone_number VARCHAR(20),
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_referrals INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'active',
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول التقدم في التسجيل
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registration_progress (
                user_id BIGINT PRIMARY KEY,
                current_stage VARCHAR(50),
                user_data TEXT,
                telegram_username VARCHAR(100),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # جدول الروابط
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_links (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                platform VARCHAR(50),
                url VARCHAR(500),
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
            )
        ''')
        
        # جدول الدفع
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                payment_method VARCHAR(50),
                wallet_type VARCHAR(100),
                wallet_address VARCHAR(500),
                transfer_full_name VARCHAR(200),
                transfer_phone VARCHAR(20),
                transfer_location VARCHAR(200),
                transfer_company VARCHAR(100),
                setup_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE
            )
        ''')
        
        # جداول نظام التعليقات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS comment_verification_tasks (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                post_url VARCHAR(500),
                platform VARCHAR(50),
                unique_code VARCHAR(20) UNIQUE,
                required_comment_text VARCHAR(200),
                status VARCHAR(20) DEFAULT 'pending',
                user_comment_text TEXT,
                reward_amount DECIMAL(10,2) DEFAULT 0.00,
                verified_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_rewards (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                task_id INTEGER,
                reward_amount DECIMAL(10,2),
                reward_type VARCHAR(50),
                status VARCHAR(20) DEFAULT 'pending',
                paid_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES comment_verification_tasks(id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_comment_tasks (
                id SERIAL PRIMARY KEY,
                platform VARCHAR(50),
                post_url VARCHAR(500),
                description VARCHAR(300),
                required_comment_template VARCHAR(200),
                reward_amount DECIMAL(10,2),
                max_participants INTEGER,
                current_participants INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'active',
                created_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("✅ تم إعداد قاعدة البيانات والجداول بنجاح!")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في إعداد قاعدة البيانات: {e}")
        return False

def save_registration_progress(user_id: int, current_stage: str, user_data: dict):
    """حفظ تقدم التسجيل للاستئناف لاحقاً"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        user_data_json = json.dumps(user_data)
        
        cursor.execute('''
            INSERT INTO registration_progress 
            (user_id, current_stage, user_data, telegram_username)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) 
            DO UPDATE SET 
                current_stage = EXCLUDED.current_stage,
                user_data = EXCLUDED.user_data,
                last_updated = CURRENT_TIMESTAMP
        ''', (user_id, current_stage, user_data_json, user_data.get('telegram_username', '')))
        
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"✅ تم حفظ تقدم التسجيل للمستخدم {user_id} في مرحلة {current_stage}")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حفظ تقدم التسجيل: {e}")
        return False

def get_registration_progress(user_id: int):
    """استرجاع تقدم التسجيل المحفوظ"""
    try:
        conn = create_connection()
        if not conn:
            return None
            
        cursor = conn.cursor()
        
        cursor.execute('SELECT current_stage, user_data FROM registration_progress WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        
        if result:
            user_data = json.loads(result[1]) if result[1] else {}
            logger.info(f"✅ تم استرجاع تقدم التسجيل للمستخدم {user_id}")
            return {'current_stage': result[0], 'user_data': user_data}
        return None
        
    except Exception as e:
        logger.error(f"❌ خطأ في استرجاع تقدم التسجيل: {e}")
        return None
    finally:
        if conn:
            conn.close()

def delete_registration_progress(user_id: int):
    """حذف تقدم التسجيل بعد إكمال العملية"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM registration_progress WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"✅ تم حذف تقدم التسجيل للمستخدم {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حذف تقدم التسجيل: {e}")
        return False

async def check_user_registration(user_id: int) -> bool:
    """التحقق من تسجيل المستخدم مسبقاً في النظام"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE user_id = %s", (user_id,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        return count > 0
        
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من تسجيل المستخدم: {e}")
        return False

def generate_referral_code():
    """إنشاء كود إحالة فريد مكون من 8 أحرف"""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if check_referral_code_unique(code):
            return code

def check_referral_code_unique(code):
    """التحقق من أن كود الإحالة فريد وغير مستخدم"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE referral_code = %s", (code,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count == 0
        
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من كود الإحالة: {e}")
        return False

def update_referral_count(referral_code):
    """زيادة عداد الإحالات للمستخدم الذي قام بدعوة آخر"""
    try:
        conn = create_connection()
        if not conn:
            return False
            
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE user_profiles SET total_referrals = total_referrals + 1 WHERE referral_code = %s",
            (referral_code,)
        )
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"✅ تم تحديث عداد الإحالات للكود {referral_code}")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث عداد الإحالات: {e}")
        return False

# ==============================
# 🔍 دوال التحقق من الصحة
# ==============================

def validate_phone_with_country(phone_number, country_code):
    """التحقق من رقم الهاتف مع رمز الدولة"""
    try:
        phone_number = re.sub(r'[\s\-\(\)]', '', phone_number)
        
        if not phone_number.startswith('+'):
            phone_number = country_code + phone_number
        
        parsed_number = phonenumbers.parse(phone_number, None)
        
        if phonenumbers.is_valid_number(parsed_number):
            formatted_number = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            return True, formatted_number, "✅ رقم الهاتف صحيح"
        else:
            return False, phone_number, "❌ رقم الهاتف غير صحيح"
            
    except Exception as e:
        return False, phone_number, f"❌ رقم الهاتف غير صحيح: {str(e)}"

def validate_email(email: str) -> bool:
    """التحقق من صحة البريد الإلكتروني"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_facebook_url(url):
    """تحقق من روابط الفيسبوك"""
    url = url.strip().lower()
    return 'facebook.com' in url or 'fb.com' in url

def validate_instagram_url(url):
    """التحقق من رابط الانستغرام"""
    url = url.strip().lower()
    return 'instagram.com' in url or 'instagr.am' in url

def validate_youtube_url(url: str) -> bool:
    """التحقق من رابط يوتيوب (لقنوات فقط)"""
    url = url.strip().lower()
    
    # رفض روابط الفيديوهات الفردية
    if 'youtube.com/watch' in url or 'youtu.be/' in url:
        return False
        
    # قبول روابط القنوات فقط
    return 'youtube.com' in url

def validate_social_media_url(url):
    """التحقق من رابط وسائل التواصل الاجتماعي العامة"""
    social_domains = [
        'twitter.com', 'linkedin.com', 'tiktok.com', 
        'snapchat.com', 'youtube.com', 'telegram.me'
    ]
    return any(domain in url for domain in social_domains)

def validate_birth_year(year):
    """التحقق من سنة الولادة"""
    try:
        year_int = int(year)
        current_year = datetime.now().year
        if 1920 <= year_int <= current_year - 13:
            return True, year_int
        return False, year_int
    except:
        return False, None

def is_duplicate_social_media(context: CallbackContext, platform: str, new_url: str) -> bool:
    """التحقق من أن الرابط غير مكرر في نفس المنصة"""
    social_media = context.user_data.get('social_media', {})
    
    if platform in social_media:
        cleaned_new_url = clean_social_media_url(new_url)
        
        for existing_url in social_media[platform]:
            cleaned_existing_url = clean_social_media_url(existing_url)
            if cleaned_new_url == cleaned_existing_url:
                return True
    
    return False

def clean_social_media_url(url: str) -> str:
    """تنظيف الرابط للمقارنة"""
    url = url.strip().lower()
    url = re.sub(r'^https?://(www\.)?', '', url)
    url = url.rstrip('/')
    
    if 'facebook.com' in url or 'fb.com' in url:
        url = url.split('?')[0]
    
    if 'instagram.com' in url:
        url = url.split('?')[0]
    
    return url

def extract_username(url: str) -> str:
    """استخراج اسم المستخدم من الرابط"""
    cleaned = re.sub(r'^https?://(www\.)?', '', url)
    cleaned = cleaned.split('?')[0]
    
    if 'youtube.com' in url or 'youtu.be' in url:
        return extract_youtube_username(url)
    
    if '/' in cleaned:
        username = cleaned.split('/')[-1]
        if username:
            return f"@{username}"
    
    return url

def extract_youtube_username(url: str) -> str:
    """استخراج اسم قناة يوتيوب من الرابط"""
    try:
        url = url.strip().lower()
        
        if '?' in url:
            url = url.split('?')[0]
        
        if '/channel/' in url:
            username = url.split('/channel/')[-1].split('/')[0]
            return f"قناة: {username}"
        
        elif '/c/' in url:
            username = url.split('/c/')[-1].split('/')[0]
            return f"@{username}"
        
        elif '/user/' in url:
            username = url.split('/user/')[-1].split('/')[0]
            return f"@{username}"
        
        elif '/@' in url:
            username = url.split('/@')[-1].split('/')[0]
            return f"@{username}"
        
        else:
            return url[:30] + "..." if len(url) > 30 else url
            
    except Exception as e:
        logger.error(f"❌ خطأ في استخراج اسم يوتيوب: {e}")
        return url

# ==============================
# 💬 نظام التحقق من التعليقات
# ==============================

class CommentVerificationSystem:
    def __init__(self):
        self.setup_database()
    
    def setup_database(self):
        """إعداد جداول التحقق من التعليقات في قاعدة البيانات"""
        conn = None
        try:
            conn = create_connection()
            if not conn:
                logger.error("❌ فشل الاتصال بقاعدة البيانات في setup_database")
                return
                
            cursor = conn.cursor()
            
            # جدول مهام التحقق
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comment_verification_tasks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    post_url VARCHAR(500),
                    platform VARCHAR(50),
                    unique_code VARCHAR(20) UNIQUE,
                    required_comment_text VARCHAR(200),
                    status VARCHAR(20) DEFAULT 'pending',
                    user_comment_text TEXT,
                    reward_amount DECIMAL(10,2) DEFAULT 0.00,
                    verified_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # جدول المكافآت
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_rewards (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    task_id INTEGER,
                    reward_amount DECIMAL(10,2),
                    reward_type VARCHAR(50),
                    status VARCHAR(20) DEFAULT 'pending',
                    paid_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES comment_verification_tasks(id) ON DELETE CASCADE
                )
            ''')
            
            # جدول المهام النشطة
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS active_comment_tasks (
                    id SERIAL PRIMARY KEY,
                    platform VARCHAR(50),
                    post_url VARCHAR(500),
                    description VARCHAR(300),
                    required_comment_template VARCHAR(200),
                    reward_amount DECIMAL(10,2),
                    max_participants INTEGER,
                    current_participants INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'active',
                    created_by BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            logger.info("✅ تم إعداد جداول نظام التحقق من التعليقات بنجاح!")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إعداد جداول التحقق: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                cursor.close()
                conn.close()
    
    def generate_unique_code(self, user_id: int) -> str:
        """إنشاء كود تحقق فريد للمستخدم"""
        base_string = f"{user_id}_{datetime.now().timestamp()}_{secrets.token_hex(4)}"
        unique_code = hashlib.md5(base_string.encode()).hexdigest()[:8].upper()
        return f"CMT{unique_code}"
    
    def create_verification_task(self, user_id: int, task_data: dict) -> dict:
        """إنشاء مهمة تحقق جديدة للمستخدم"""
        conn = None
        try:
            conn = create_connection()
            if not conn:
                return {'success': False, 'message': 'فشل الاتصال بقاعدة البيانات'}
                
            cursor = conn.cursor()
            
            unique_code = self.generate_unique_code(user_id)
            
            cursor.execute('''
                INSERT INTO comment_verification_tasks 
                (user_id, post_url, platform, unique_code, required_comment_text, reward_amount)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                user_id,
                task_data['post_url'],
                task_data['platform'],
                unique_code,
                task_data.get('required_comment_template', 'شارك برأيك في هذا المنتج'),
                task_data['reward_amount']
            ))
            
            # تحديث عدد المشاركين في المهمة النشطة
            if 'task_id' in task_data:
                cursor.execute('''
                    UPDATE active_comment_tasks 
                    SET current_participants = current_participants + 1 
                    WHERE id = %s
                ''', (task_data['task_id'],))
            
            conn.commit()
            
            return {
                'success': True,
                'unique_code': unique_code,
                'message': 'تم إنشاء المهمة بنجاح'
            }
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء مهمة التحقق: {e}")
            if conn:
                conn.rollback()
            return {'success': False, 'message': 'حدث خطأ في إنشاء المهمة'}
        finally:
            if conn:
                cursor.close()
                conn.close()
    
    def verify_comment_submission(self, user_id: int, unique_code: str, user_comment: str) -> dict:
        """التحقق من تقديم التعليق"""
        conn = None
        try:
            conn = create_connection()
            if not conn:
                return {'success': False, 'message': 'فشل الاتصال بقاعدة البيانات'}
                
            cursor = conn.cursor()
            
            # البحث عن المهمة
            cursor.execute('''
                SELECT id, post_url, platform, required_comment_text, reward_amount, status
                FROM comment_verification_tasks 
                WHERE user_id = %s AND unique_code = %s
            ''', (user_id, unique_code))
            
            task = cursor.fetchone()
            
            if not task:
                return {'success': False, 'message': '❌ لم يتم العثور على المهمة'}
            
            task_id, post_url, platform, required_text, reward_amount, status = task
            
            if status != 'pending':
                return {'success': False, 'message': '❌ تم التحقق من هذه المهمة مسبقاً'}
            
            # التحقق من وجود الكود الفريد في التعليق
            if unique_code not in user_comment:
                return {'success': False, 'message': '❌ لم يتم العثور على كود التحقق في التعليق'}
            
            # تحديث حالة المهمة
            cursor.execute('''
                UPDATE comment_verification_tasks 
                SET status = 'verified', user_comment_text = %s, verified_at = CURRENT_TIMESTAMP
                WHERE id = %s
            ''', (user_comment, task_id))
            
            # تسجيل المكافأة
            cursor.execute('''
                INSERT INTO user_rewards (user_id, task_id, reward_amount, reward_type, status)
                VALUES (%s, %s, %s, 'comment_verification', 'approved')
            ''', (user_id, task_id, reward_amount))
            
            conn.commit()
            
            return {
                'success': True, 
                'message': f'✅ تم التحقق من تعليقك بنجاح! مكافأة: {reward_amount} ريال',
                'reward_amount': reward_amount
            }
            
        except Exception as e:
            logger.error(f"❌ خطأ في التحقق من التعليق: {e}")
            if conn:
                conn.rollback()
            return {'success': False, 'message': 'حدث خطأ في التحقق'}
        finally:
            if conn:
                cursor.close()
                conn.close()

    def get_active_tasks(self) -> list:
        """الحصول على المهام النشطة"""
        conn = None
        try:
            conn = create_connection()
            if not conn:
                logger.error("❌ فشل الاتصال بقاعدة البيانات في get_active_tasks")
                return []
                
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, platform, post_url, description, required_comment_template, reward_amount, 
                       max_participants, current_participants
                FROM active_comment_tasks 
                WHERE status = 'active' AND (current_participants < max_participants OR max_participants = 0)
                ORDER BY created_at DESC
            ''')
            
            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    'id': row[0],
                    'platform': row[1],
                    'post_url': row[2],
                    'description': row[3],
                    'required_comment_template': row[4],
                    'reward_amount': float(row[5]),
                    'max_participants': row[6],
                    'current_participants': row[7],
                    'available_slots': row[6] - row[7] if row[6] > 0 else 999
                })
            
            return tasks
            
        except Exception as e:
            logger.error(f"❌ خطأ في جلب المهام النشطة: {e}")
            return []
        finally:
            if conn:
                cursor.close()
                conn.close()

    def get_user_progress(self, user_id: int) -> dict:
        """الحصول على تقدم المستخدم"""
        conn = None
        try:
            conn = create_connection()
            if not conn:
                logger.error("❌ فشل الاتصال بقاعدة البيانات في get_user_progress")
                return {'success': False}
                
            cursor = conn.cursor()
            
            # عدد المهام المكتملة
            cursor.execute('''
                SELECT COUNT(*) FROM comment_verification_tasks 
                WHERE user_id = %s AND status = 'verified'
            ''', (user_id,))
            completed_tasks = cursor.fetchone()[0]
            
            # إجمالي المكافآت
            cursor.execute('''
                SELECT SUM(reward_amount) FROM user_rewards 
                WHERE user_id = %s AND status = 'approved'
            ''', (user_id,))
            total_rewards_result = cursor.fetchone()
            total_rewards = float(total_rewards_result[0]) if total_rewards_result[0] else 0.0
            
            # المهام قيد الانتظار
            cursor.execute('''
                SELECT COUNT(*) FROM comment_verification_tasks 
                WHERE user_id = %s AND status = 'pending'
            ''', (user_id,))
            pending_tasks = cursor.fetchone()[0]
            
            return {
                'completed_tasks': completed_tasks,
                'pending_tasks': pending_tasks,
                'total_rewards': total_rewards,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"❌ خطأ في جلب تقدم المستخدم: {e}")
            return {'success': False}
        finally:
            if conn:
                cursor.close()
                conn.close()

# إنشاء كائن النظام العالمي
comment_system = CommentVerificationSystem()

# ==============================
# 🚀 دوال المحادثة الرئيسية
# ==============================

async def start(update: Update, context: CallbackContext) -> int:
    """بدء عملية التسجيل - البوت خاص ويعمل فقط بالدعوات"""
    user = update.message.from_user
    
    logger.info(f"محاولة دخول من: {user.id} - {user.first_name} - @{user.username}")
    
    # التحقق إذا كان المستخدم مسموحاً له بدون دعوة
    if user.id in ALLOWED_USER_IDS:
        logger.info(f"المستخدم المسموح {user.id} دخل البوت")
        return await handle_allowed_user_start(update, context, user.id == OWNER_USER_ID)
    
    # التحقق من وجود معلمة في الرابط (كود دعوة)
    if context.args and len(context.args) > 0:
        referral_code = context.args[0]
        logger.info(f"مستخدم دخل برابط دعوة: {user.id} - كود الدعوة: {referral_code}")
        return await handle_invited_user(update, context, referral_code)
    else:
        # إذا جاء بدون رابط دعوة
        logger.warning(f"مستخدم غير مصرح حاول الدخول بدون دعوة: {user.id}")
        await update.message.reply_text(
            "🚫 **البوت خاص**\n\n"
            "🔐 هذا البوت لا يعمل إلا عبر روابط الدعوة الحصرية.\n\n"
            "📨 **للتسجيل، يجب أن تحصل على رابط دعوة من:**\n"
            "• أحد الأعضاء المسجلين في النظام\n"
            "• المسؤول عن البوت\n\n"
            "🔗 **طريقة الاستخدام الصحيحة:**\n"
            "1. اطلب رابط دعوة من شخص مسجل\n"
            "2. انقر على الرابط الذي سيصلك\n"
            "3. ابدأ عملية التسجيل\n\n"
            "❌ **لا يمكنك استخدام البوت مباشرة**\n\n"
            "📞 للاستفسارات: /support"
        )
        return ConversationHandler.END

async def handle_allowed_user_start(update: Update, context: CallbackContext, is_owner: bool):
    """معالجة بدء المستخدم المسموح له"""
    user = update.message.from_user
    
    user_type = "المالك" if is_owner else "المسؤول"
    
    # التحقق من التسجيل المسبق
    is_registered = await check_user_registration(user.id)
    if is_registered:
        await update.message.reply_text(
            f"🎉 **مرحباً بعودتك {user.first_name}!** ({user_type})\n\n"
            "🔧 **الأوامر المتاحة:**\n"
            "/profile - عرض ملفك الشخصي\n"
            "/invite - عرض كود الدعوة وإنشاء روابط\n"
            "/stats - إحصائيات البوت (للمالك)\n"
            "/support - الدعم الفني"
        )
        return ConversationHandler.END
    
    # بدء تسجيل المستخدم المسموح
    context.user_data.clear()
    context.user_data['telegram_username'] = user.username
    context.user_data['user_id'] = user.id
    context.user_data['social_media'] = {'facebook': [], 'instagram': [], 'youtube': [], 'other': []}
    context.user_data['is_allowed_user'] = True
    context.user_data['is_owner'] = is_owner
    
    save_registration_progress(user.id, 'REFERRAL_STAGE', context.user_data)
    
    await update.message.reply_text(
        f"👑 **مرحباً {user.first_name}!** ({user_type})\n\n"
        "🏢 **أهلاً بك في نظام التسجيل لمؤسسة الترويج الإعلامي**\n\n"
        f"💼 **بصفتك {user_type.lower()}، يمكنك التسجيل بدون دعوة**\n\n"
        "📋 **هل تمت دعوتك من قبل أحد الأعضاء؟**\n"
        "إذا كان لديك كود دعوة، الرجاء إدخاله الآن.\n"
        "إذا لم يكن لديك، اكتب 'لا' للمتابعة."
    )
    return REFERRAL_STAGE

async def handle_invited_user(update: Update, context: CallbackContext, referral_code: str):
    """معالجة المستخدم المدعو"""
    user = update.message.from_user
    
    # التحقق من صحة كود الدعوة
    if not await validate_referral_code(referral_code):
        logger.warning(f"كود دعوة غير صالح: {referral_code} من المستخدم: {user.id}")
        await update.message.reply_text(
            "❌ **رابط الدعوة غير صالح!**\n\n"
            "🔍 الرابط الذي استخدمته غير صحيح أو منتهي الصلاحية.\n\n"
            "💡 **الرجاء:**\n"
            "• طلب رابط جديد من الشخص الذي دعاك\n"
            "• التأكد من نسخ الرابط كاملاً\n"
            "• التواصل مع الدعم إذا استمرت المشكلة\n\n"
            "📞 /support - للتواصل مع الدعم الفني"
        )
        return ConversationHandler.END
    
    # التحقق من التسجيل المسبق
    is_registered = await check_user_registration(user.id)
    if is_registered:
        await update.message.reply_text(
            f"🎉 **مرحباً بعودتك {user.first_name}!**\n\n"
            "✅ **أنت مسجل مسبقاً في النظام**\n\n"
            "🔧 **الأوامر المتاحة:**\n"
            "/profile - عرض ملفك الشخصي\n"
            "/invite - عرض كود الدعوة\n"
            "/support - الدعم الفني"
        )
        return ConversationHandler.END
    
    # الحصول على اسم الشخص الذي دعاه
    inviter_name = await get_inviter_name(referral_code)
    
    # التحقق من وجود تسجيل غير مكتمل
    progress = get_registration_progress(user.id)
    
    if progress:
        # استئناف التسجيل من حيث توقف
        context.user_data.clear()
        context.user_data.update(progress['user_data'])
        context.user_data['invited_by'] = referral_code
        
        # التأكد من وجود يوتيوب في البيانات المسترجعة
        if 'social_media' not in context.user_data:
            context.user_data['social_media'] = {'facebook': [], 'instagram': [], 'youtube': [], 'other': []}
        elif 'youtube' not in context.user_data['social_media']:
            context.user_data['social_media']['youtube'] = []
        
        stage_mapping = {
            'REFERRAL_STAGE': REFERRAL_STAGE,
            'FULL_NAME': FULL_NAME,
            'COUNTRY': COUNTRY,
            'GENDER': GENDER,
            'BIRTH_YEAR': BIRTH_YEAR,
            'PHONE': PHONE,
            'EMAIL': EMAIL,
            'SOCIAL_MEDIA_MENU': SOCIAL_MEDIA_MENU,
            'FACEBOOK_URL': FACEBOOK_URL,
            'INSTAGRAM_URL': INSTAGRAM_URL,
            'YOUTUBE_URL': YOUTUBE_URL,
            'OTHER_SOCIAL_MEDIA': OTHER_SOCIAL_MEDIA,
            'PAYMENT_METHOD': PAYMENT_METHOD,
            'WALLET_TYPE': WALLET_TYPE,
            'NEW_WALLET_TYPE': NEW_WALLET_TYPE,
            'WALLET_ADDRESS': WALLET_ADDRESS,
            'TRANSFER_DETAILS': TRANSFER_DETAILS
        }
        
        current_stage = stage_mapping.get(progress['current_stage'], REFERRAL_STAGE)
        
        await update.message.reply_text(
            f"🔄 **عودة إلى التسجيل غير المكتمل {user.first_name}!**\n\n"
            f"📨 **تمت دعوتك بواسطة: {inviter_name}**\n\n"
            "📋 لقد وجدنا أن لديك تسجيلاً غير مكتمل.\n"
            "سنستأنف من حيث توقفت.\n\n"
            "⏩ **متابعة من المرحلة الحالية...**"
        )
        
        if current_stage == SOCIAL_MEDIA_MENU:
            return await show_social_media_menu(update, context)
        elif current_stage in [FACEBOOK_URL, INSTAGRAM_URL, YOUTUBE_URL, OTHER_SOCIAL_MEDIA]:
            return await show_social_media_menu(update, context)
        else:
            return current_stage
    else:
        # بدء تسجيل جديد للمستخدم المدعو
        context.user_data.clear()
        context.user_data['telegram_username'] = user.username
        context.user_data['user_id'] = user.id
        context.user_data['social_media'] = {'facebook': [], 'instagram': [], 'youtube': [], 'other': []}
        context.user_data['invited_by'] = referral_code
        
        save_registration_progress(user.id, 'REFERRAL_STAGE', context.user_data)
        
        await update.message.reply_text(
            f"🆕 **مرحباً {user.first_name}!** 👋\n"
            f"📨 **تمت دعوتك بواسطة: {inviter_name}**\n\n"
            "🏢 **أهلاً بك في نظام التسجيل لمؤسسة الترويج الإعلامي**\n\n"
            "✅ **لقد تمت دعوتك بنجاح!**\n\n"
            "📋 **هل تريد استخدام كود الدعوة هذا؟**\n"
            "• اكتب 'نعم' لاستخدام كود الدعوة الحالي\n"
            "• اكتب 'لا' إذا كنت تمتلك كود دعوة آخر\n"
            "• أو أدخل كود الدعوة مباشرة"
        )
        return REFERRAL_STAGE

async def get_inviter_name(referral_code: str) -> str:
    """الحصول على اسم الشخص الذي قام بالدعوة"""
    try:
        conn = create_connection()
        if not conn:
            logger.error("❌ فشل الاتصال بقاعدة البيانات في get_inviter_name")
            return "عضو مجهول"
        cursor = conn.cursor()
        
        cursor.execute("SELECT full_name FROM user_profiles WHERE referral_code = %s", (referral_code,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return result[0]
        else:
            return "عضو مجهول"
            
    except Exception as e:
        logger.error(f"خطأ في الحصول على اسم المُدعي: {e}")
        return "عضو مجهول"

async def validate_referral_code(code: str) -> bool:
    """التحقق من صحة كود الإحالة"""
    try:
        code = code.strip().upper()
        
        if len(code) < 3:
            return False
            
        conn = create_connection()
        if not conn:
            logger.error("❌ فشل الاتصال بقاعدة البيانات في validate_referral_code")
            return False
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE referral_code = %s", (code,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        return count > 0
        
    except Exception as e:
        logger.error(f"❌ خطأ في التحقق من كود الإحالة: {e}")
        return False

async def get_referral(update: Update, context: CallbackContext) -> int:
    """معالجة كود الإحالة المدخل من المستخدم - النسخة المحسنة"""
    try:
        referral_input = update.message.text.strip().lower()
        
        # الحصول على كود الدعوة المخزن مسبقاً
        stored_referral = context.user_data.get('invited_by')
        
        # معالجة الردود النصية
        if referral_input in ['نعم', 'yes', 'y', 'ye', 'yep', 'ايوه']:
            if stored_referral:
                # استخدام كود الدعوة المخزن
                context.user_data['invited_by'] = stored_referral
                
                await update.message.reply_text(
                    f"✅ **تم تأكيد كود الدعوة:** {stored_referral}\n\n"
                    "🆔 **الآن، ما هو اسمك الثلاثي الكامل؟**\n"
                    "(مثال: أحمد محمد علي)"
                )
                
                save_registration_progress(update.effective_user.id, 'FULL_NAME', context.user_data)
                return FULL_NAME
            else:
                await update.message.reply_text(
                    "❌ **لم يتم العثور على كود دعوة!**\n\n"
                    "🔍 **السبب:** لم يتم حفظ كود الدعوة من الرابط\n\n"
                    "💡 **الحلول:**\n"
                    "• أدخل كود الدعوة يدوياً\n"
                    "• أو اكتب 'لا' للمتابعة بدون كود دعوة\n\n"
                    "📝 **أدخل كود الدعوة أو اكتب 'لا':**"
                )
                return REFERRAL_STAGE
                
        elif referral_input in ['لا', 'no', 'skip', 'لأ', 'لاء']:
            context.user_data['invited_by'] = None
            
            await update.message.reply_text(
                "⏭️ **تم تخطي كود الدعوة**\n\n"
                "🆔 **الآن، ما هو اسمك الثلاثي الكامل؟**\n"
                "(مثال: أحمد محمد علي)"
            )
            
            save_registration_progress(update.effective_user.id, 'FULL_NAME', context.user_data)
            return FULL_NAME
            
        else:
            # معالجة إدخال كود دعوة يدوي
            if await validate_referral_code(referral_input.upper()):
                context.user_data['invited_by'] = referral_input.upper()
                
                await update.message.reply_text(
                    f"✅ **تم التحقق من كود الدعوة:** {referral_input.upper()}\n\n"
                    "🆔 **الآن، ما هو اسمك الثلاثي الكامل؟**\n"
                    "(مثال: أحمد محمد علي)"
                )
                
                save_registration_progress(update.effective_user.id, 'FULL_NAME', context.user_data)
                return FULL_NAME
                
            else:
                await update.message.reply_text(
                    "❌ **كود الدعوة غير صحيح!**\n\n"
                    "🔍 **الأسباب المحتملة:**\n"
                    "• الكود غير موجود في النظام\n"
                    "• الكود منتهي الصلاحية\n"
                    "• خطأ في كتابة الكود\n\n"
                    "💡 **الحلول:**\n"
                    "• تحقق من الكود وأعد إدخاله\n"
                    "• اطلب كود جديد من الشخص الذي دعاك\n"
                    "• اكتب 'لا' للمتابعة بدون كود دعوة\n\n"
                    "📝 **أدخل كود الدعوة أو اكتب 'لا':**"
                )
                return REFERRAL_STAGE
                
    except Exception as e:
        logger.error(f"❌ خطأ في get_referral: {e}")
        
        # استمرار العملية في حالة الخطأ
        await update.message.reply_text(
            "⚠️ **حدث خطأ تقني. جاري المتابعة...**\n\n"
            "🆔 **ما هو اسمك الثلاثي الكامل؟**\n"
            "(مثال: أحمد محمد علي)"
        )
        
        context.user_data['invited_by'] = None
        save_registration_progress(update.effective_user.id, 'FULL_NAME', context.user_data)
        return FULL_NAME

async def get_full_name(update: Update, context: CallbackContext) -> int:
    """استقبال الاسم الثلاثي الكامل من المستخدم"""
    full_name = update.message.text.strip()

    name_parts = full_name.split()
    if len(name_parts) < 3:
        await update.message.reply_text(
            "❌ الرجاء إدخال الاسم الثلاثي الكامل (الاسم الأول + الأب + الكنية)\n"
            "(مثال: أحمد محمد علي)"
        )
        return FULL_NAME

    if len(full_name) > 50:
        await update.message.reply_text(
            "❌ الاسم طويل جداً! الحد الأقصى هو 50 حرف\n\n"
            f"📏 عدد أحرف الاسم الذي أدخلته: {len(full_name)}\n"
            "✂️ الرجاء اختصار الاسم وإعادة إدخاله"
        )
        return FULL_NAME
    
    context.user_data['full_name'] = full_name
    save_registration_progress(update.effective_user.id, 'COUNTRY', context.user_data)
    
    country_buttons = [list(COUNTRIES.keys())[i:i+2] for i in range(0, len(COUNTRIES), 2)]
    reply_markup = ReplyKeyboardMarkup(country_buttons, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"✅ تم حفظ الاسم: {full_name}\n\n"
        "🌍 **الآن، اختر بلدك من القائمة:**",
        reply_markup=reply_markup
    )
    return COUNTRY

async def get_country(update: Update, context: CallbackContext) -> int:
    """استقبال البلد المختار من المستخدم"""
    country = update.message.text

    if country not in COUNTRIES:
        await update.message.reply_text("❌ الرجاء اختيار بلد من القائمة المحددة.")
        return COUNTRY
    
    context.user_data['country'] = country
    context.user_data['country_code'] = COUNTRIES[country]
    save_registration_progress(update.effective_user.id, 'GENDER', context.user_data)
    
    gender_keyboard = [['ذكر', 'أنثى']]
    reply_markup = ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"🌍 تم اختيار البلد: {country}\n\n"
        "🚻 **الآن، اختر جنسك:**",
        reply_markup=reply_markup
    )
    return GENDER

async def get_gender(update: Update, context: CallbackContext) -> int:
    """استقبال الجنس المختار من المستخدم - النسخة المصححة"""
    try:
        gender = update.message.text
        if gender not in ['ذكر', 'أنثى']:
            await update.message.reply_text(
                "❌ الرجاء اختيار 'ذكر' أو 'أنثى' من القائمة.",
                reply_markup=ReplyKeyboardMarkup([['ذكر', 'أنثى']], one_time_keyboard=True)
            )
            return GENDER
        
        context.user_data['gender'] = gender
        save_registration_progress(update.effective_user.id, 'BIRTH_YEAR', context.user_data)
        
        await update.message.reply_text(
            f"🚻 تم التسجيل كـ: {gender}\n\n"
            "🎂 **الآن، ما هو عام ولادتك؟**\n"
            "(أدخل السنة بأربعة أرقام، مثال: 1990)",
            reply_markup=ReplyKeyboardRemove()
        )
        return BIRTH_YEAR
        
    except Exception as e:
        logger.error(f"❌ خطأ في get_gender: {e}")
        await update.message.reply_text(
            "❌ حدث خطأ. الرجاء اختيار الجنس مرة أخرى:",
            reply_markup=ReplyKeyboardMarkup([['ذكر', 'أنثى']], one_time_keyboard=True)
        )
        return GENDER

async def get_birth_year(update: Update, context: CallbackContext) -> int:
    """استقبال عام الولادة من المستخدم"""
    year = update.message.text
    is_valid, year_int = validate_birth_year(year)
    
    if not is_valid:
        await update.message.reply_text(
            "❌ سنة الولادة غير صحيحة!\n"
            "الرجاء إدخال سنة صحيحة (مثال: 1990)"
        )
        return BIRTH_YEAR
    
    context.user_data['birth_year'] = year_int
    save_registration_progress(update.effective_user.id, 'PHONE', context.user_data)
    
    country_code = context.user_data.get('country_code', '+966')
    await update.message.reply_text(
        f"🎂 تم حفظ سنة الولادة: {year_int}\n\n"
        f"📞 **الآن، ما هو رقم هاتفك؟**\n"
        f"سيتم إضافة رمز الدولة {country_code} تلقائياً\n"
        f"(أدخل الرقم فقط، مثال: 512345678)"
    )
    return PHONE

async def get_phone(update: Update, context: CallbackContext) -> int:
    """استقبال رقم الهاتف من المستخدم"""
    phone_input = update.message.text
    country_code = context.user_data.get('country_code', '+966')
    
    is_valid, formatted_phone, message = validate_phone_with_country(phone_input, country_code)
    
    if not is_valid:
        await update.message.reply_text(
            f"{message}\n\n"
            f"📞 الرجاء إدخال رقم هاتف صحيح لبلدك:\n"
            f"(أدخل الرقم فقط، مثال: 512345678)"
        )
        return PHONE
    
    context.user_data['phone_number'] = formatted_phone
    save_registration_progress(update.effective_user.id, 'EMAIL', context.user_data)
    
    await update.message.reply_text(
        f"{message}\n\n"
        "📧 **الآن، أدخل بريدك الإلكتروني:**\n"
        "(مثال: yourname@example.com)"
    )
    return EMAIL

async def get_email(update: Update, context: CallbackContext) -> int:
    """استقبال البريد الإلكتروني من المستخدم"""
    email = update.message.text.strip()
    
    if not validate_email(email):
        await update.message.reply_text(
            "❌ البريد الإلكتروني غير صحيح!\n"
            "الرجاء إدخال بريد إلكتروني صالح (مثال: user@example.com)\n\n"
            "📧 أدخل بريدك الإلكتروني:"
        )
        return EMAIL
    
    context.user_data['email'] = email
    save_registration_progress(update.effective_user.id, 'SOCIAL_MEDIA_MENU', context.user_data)
    
    keyboard = [
        [InlineKeyboardButton("📘 إضافة حساب فيسبوك", callback_data="add_facebook")],
        [InlineKeyboardButton("📸 إضافة حساب انستغرام", callback_data="add_instagram")],
        [InlineKeyboardButton("📺 إضافة قناة يوتيوب", callback_data="add_youtube")],
        [InlineKeyboardButton("🔗 إضافة وسائل تواصل أخرى", callback_data="add_other")],
        [InlineKeyboardButton("⏩ تخطي وإكمال التسجيل", callback_data="skip_social")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ تم حفظ البريد الإلكتروني: {email}\n\n"
        "📱 **الآن سنبدأ بتسجيل روابط التواصل الاجتماعي**\n\n"
        "💡 **يمكنك إضافة عدة حسابات لنفس المنصة**\n\n"
        "🔗 **اختر نوع الحساب الذي تريد إضافته:**",
        reply_markup=reply_markup
    )
    return SOCIAL_MEDIA_MENU

async def handle_social_media_menu(update: Update, context: CallbackContext) -> int:
    """معالجة قائمة وسائل التواصل"""
    try:
        query = update.callback_query
        await query.answer()
        
        choice = query.data
        
        if choice == "add_facebook":
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "📘 **إضافة حساب الفيسبوك**\n\n"
                    "أدخل رابط حساب الفيسبوك:\n"
                    "(مثال: https://facebook.com/username)\n\n"
                    "أو اكتب 'تخطي' للتخطي"
                )
            )
            return FACEBOOK_URL
            
        elif choice == "add_instagram":
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "📸 **إضافة حساب الانستغرام**\n\n"
                    "أدخل رابط حساب الانستغرام:\n"
                    "(مثال: https://instagram.com/username)\n\n"
                    "أو اكتب 'تخطي' للتخطي"
                )
            )
            return INSTAGRAM_URL
            
        elif choice == "add_youtube":
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "📺 **إضافة قناة يوتيوب**\n\n"
                    "أدخل رابط قناة يوتيوب (وليس فيديو):\n"
                    "(مثال: https://youtube.com/@username)\n\n"
                    "أو اكتب 'تخطي' للتخطي"
                )
            )
            return YOUTUBE_URL
            
        elif choice == "add_other":
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=(
                    "🔗 **إضافة وسائل تواصل أخرى**\n\n"
                    "أدخل رابط أي وسيلة تواصل:\n"
                    "(تويتر، لينكد إن، تيك توك، إلخ...)\n\n"
                    "أو اكتب 'انتهيت' للتخطي"
                )
            )
            return OTHER_SOCIAL_MEDIA
            
        else:  # skip_social
            # ⭐ التعديل: استخدام await للاستدعاء
            return await proceed_to_payment(update, context)
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_social_media_menu: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ تم الانتقال إلى المرحلة التالية..."
        )
        return await proceed_to_payment(update, context)

async def get_facebook_url(update: Update, context: CallbackContext) -> int:
    """استقبال رابط الفيسبوك من المستخدم"""
    try:
        user_input = update.message.text.strip()
        
        if user_input.lower() in ['/skip', 'skip', 'تخطي']:
            return await show_social_media_menu(update, context)
        
        url = user_input
        if '?' in url:
            url = url.split('?')[0]
        if not url.startswith('http'):
            url = 'https://' + url
        url = url.replace('m.facebook.com', 'www.facebook.com')
        
        if not validate_facebook_url(url):
            await update.message.reply_text(
                "❌ رابط الفيسبوك غير صحيح!\n\n"
                "📋 **أمثلة صحيحة:**\n"
                "• https://facebook.com/username\n"
                "• https://www.facebook.com/profile.php?id=123\n\n"
                "أعد إدخال الرابط أو اكتب 'تخطي' للتخطي:"
            )
            return FACEBOOK_URL
        
        if 'social_media' not in context.user_data:
            context.user_data['social_media'] = {'facebook': [], 'instagram': [], 'youtube': [], 'other': []}
        
        if is_duplicate_social_media(context, 'facebook', url):
            await update.message.reply_text(
                "❌ هذا الحساب مضاف مسبقاً!\n\n"
                "الرجاء إدخال حساب فيسبوك مختلف أو اكتب 'تخطي' للتخطي:"
            )
            return FACEBOOK_URL
        
        context.user_data['social_media']['facebook'].append(url)
        save_registration_progress(update.effective_user.id, 'SOCIAL_MEDIA_MENU', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم إضافة حساب الفيسبوك بنجاح!\n"
            f"📊 العدد الإجمالي: {len(context.user_data['social_media']['facebook'])}"
        )
        
        # ⭐ التعديل: العودة إلى القائمة الرئيسية بعد الإضافة
        return await show_social_media_menu(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في get_facebook_url: {e}")
        await update.message.reply_text("❌ حدث خطأ. جاري العودة إلى القائمة...")
        return await show_social_media_menu(update, context)

async def get_instagram_url(update: Update, context: CallbackContext) -> int:
    """استقبال رابط الانستغرام من المستخدم"""
    try:
        user_input = update.message.text.strip()
        
        if user_input.lower() in ['/skip', 'skip', 'تخطي']:
            return await show_social_media_menu(update, context)
        
        url = user_input
        if '?' in url:
            url = url.split('?')[0]
        if not url.startswith('http'):
            url = 'https://' + url
        
        if not validate_instagram_url(url):
            await update.message.reply_text(
                "❌ رابط الانستغرام غير صحيح!\n\n"
                "📋 **أمثلة صحيحة:**\n"
                "• https://instagram.com/username\n"
                "• https://www.instagram.com/username\n\n"
                "أعد إدخال الرابط أو اكتب 'تخطي' للتخطي:"
            )
            return INSTAGRAM_URL
        
        if 'social_media' not in context.user_data:
            context.user_data['social_media'] = {'facebook': [], 'instagram': [], 'youtube': [], 'other': []}
        
        if is_duplicate_social_media(context, 'instagram', url):
            await update.message.reply_text(
                "❌ هذا الحساب مضاف مسبقاً!\n\n"
                "الرجاء إدخال حساب انستغرام مختلف أو اكتب 'تخطي' للتخطي:"
            )
            return INSTAGRAM_URL
        
        context.user_data['social_media']['instagram'].append(url)
        save_registration_progress(update.effective_user.id, 'SOCIAL_MEDIA_MENU', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم إضافة حساب الانستغرام بنجاح!\n"
            f"📊 العدد الإجمالي: {len(context.user_data['social_media']['instagram'])}"
        )
        
        # ⭐ التعديل: العودة إلى القائمة الرئيسية بعد الإضافة
        return await show_social_media_menu(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في get_instagram_url: {e}")
        await update.message.reply_text("❌ حدث خطأ. جاري العودة للقائمة...")
        return await show_social_media_menu(update, context)

async def get_youtube_url(update: Update, context: CallbackContext) -> int:
    """استقبال رابط يوتيوب من المستخدم"""
    try:
        user_input = update.message.text.strip()
        
        if user_input.lower() in ['/skip', 'skip', 'تخطي']:
            return await show_social_media_menu(update, context)
        
        url = user_input
        if '?' in url:
            url = url.split('?')[0]
        if not url.startswith('http'):
            url = 'https://' + url
        
        if not validate_youtube_url(url):
            await update.message.reply_text(
                "❌ رابط يوتيوب غير صحيح!\n\n"
                "📋 **للقنوات فقط (وليس الفيديوهات):**\n"
                "• https://youtube.com/@username\n"
                "• https://youtube.com/c/channelname\n"
                "• https://youtube.com/channel/UCXXXX\n\n"
                "أعد إدخال الرابط أو اكتب 'تخطي' للتخطي:"
            )
            return YOUTUBE_URL
        
        if 'social_media' not in context.user_data:
            context.user_data['social_media'] = {'facebook': [], 'instagram': [], 'youtube': [], 'other': []}
        
        if is_duplicate_social_media(context, 'youtube', url):
            await update.message.reply_text(
                "❌ هذه القناة مضافه مسبقاً!\n\n"
                "الرجاء إدخال قناة يوتيوب مختلفة أو اكتب 'تخطي' للتخطي:"
            )
            return YOUTUBE_URL
        
        context.user_data['social_media']['youtube'].append(url)
        save_registration_progress(update.effective_user.id, 'SOCIAL_MEDIA_MENU', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم إضافة قناة يوتيوب بنجاح!\n"
            f"📊 العدد الإجمالي: {len(context.user_data['social_media']['youtube'])}"
        )
        
        # ⭐ التعديل: العودة إلى القائمة الرئيسية بعد الإضافة
        return await show_social_media_menu(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في get_youtube_url: {e}")
        await update.message.reply_text("❌ حدث خطأ. جاري العودة للقائمة...")
        return await show_social_media_menu(update, context)

async def get_other_social_media(update: Update, context: CallbackContext) -> int:
    """استقبال روابط أخرى من المستخدم"""
    try:
        user_input = update.message.text.strip()
        
        if user_input.lower() in ['انتهيت', 'لا', 'كفاية', 'تم', '/skip']:
            return await show_social_media_menu(update, context)
        
        if not validate_social_media_url(user_input):
            await update.message.reply_text(
                "❌ الرابط غير مدعوم!\n\n"
                "📋 **الوسائل المدعومة:**\n"
                "تويتر، لينكد إن، تيك توك، سناب شات، يوتيوب، تلغرام\n\n"
                "أعد إدخال الرابط أو اكتب 'انتهيت' للتخطي:"
            )
            return OTHER_SOCIAL_MEDIA
        
        url = user_input
        if '?' in url:
            url = url.split('?')[0]
        if not url.startswith('http'):
            url = 'https://' + url
        
        if 'social_media' not in context.user_data:
            context.user_data['social_media'] = {'facebook': [], 'instagram': [], 'youtube': [], 'other': []}
        
        if is_duplicate_social_media(context, 'other', url):
            await update.message.reply_text(
                "❌ هذا الرابط مضاف مسبقاً!\n\n"
                "الرجاء إدخال رابط مختلف أو اكتب 'انتهيت' للتخطي:"
            )
            return OTHER_SOCIAL_MEDIA
        
        context.user_data['social_media']['other'].append(url)
        save_registration_progress(update.effective_user.id, 'SOCIAL_MEDIA_MENU', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم إضافة الرابط بنجاح!\n"
            f"📊 العدد الإجمالي: {len(context.user_data['social_media']['other'])}"
        )
        
        # ⭐ التعديل: العودة إلى القائمة الرئيسية بعد الإضافة
        return await show_social_media_menu(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في get_other_social_media: {e}")
        await update.message.reply_text("❌ حدث خطأ. جاري العودة للقائمة...")
        return await show_social_media_menu(update, context)

async def show_social_media_menu(update: Update, context: CallbackContext) -> int:
    """عرض قائمة وسائل التواصل مع الحسابات المضافة"""
    try:
        social_data = context.user_data.get('social_media', {'facebook': [], 'instagram': [], 'youtube': [], 'other': []})
        
        summary_lines = []
        summary_lines.append("📱 **الحسابات المضافة:**")
        
        if social_data['facebook']:
            summary_lines.append(f"📘 فيسبوك: {len(social_data['facebook'])} حساب")
            for i, url in enumerate(social_data['facebook'], 1):
                summary_lines.append(f"   {i}. {extract_username(url)}")
        else:
            summary_lines.append("📘 فيسبوك: لا توجد حسابات")
        
        if social_data['instagram']:
            summary_lines.append(f"\n📸 انستغرام: {len(social_data['instagram'])} حساب")
            for i, url in enumerate(social_data['instagram'], 1):
                summary_lines.append(f"   {i}. {extract_username(url)}")
        else:
            summary_lines.append("\n📸 انستغرام: لا توجد حسابات")
        
        if social_data['youtube']:
            summary_lines.append(f"\n📺 يوتيوب: {len(social_data['youtube'])} قناة")
            for i, url in enumerate(social_data['youtube'], 1):
                summary_lines.append(f"   {i}. {extract_youtube_username(url)}")
        else:
            summary_lines.append("\n📺 يوتيوب: لا توجد قنوات")
        
        if social_data['other']:
            summary_lines.append(f"\n🔗 أخرى: {len(social_data['other'])} رابط")
            for i, url in enumerate(social_data['other'], 1):
                summary_lines.append(f"   {i}. {extract_username(url)}")
        else:
            summary_lines.append("\n🔗 أخرى: لا توجد روابط")
        
        summary = "\n".join(summary_lines)
        
        keyboard = [
            [InlineKeyboardButton("📘 إضافة حساب فيسبوك", callback_data="add_facebook")],
            [InlineKeyboardButton("📸 إضافة حساب انستغرام", callback_data="add_instagram")],
            [InlineKeyboardButton("📺 إضافة قناة يوتيوب", callback_data="add_youtube")],
            [InlineKeyboardButton("🔗 إضافة وسائل تواصل أخرى", callback_data="add_other")],
            [InlineKeyboardButton("✅ إنهاء وإكمال التسجيل", callback_data="skip_social")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{summary}\n\n🔗 **اختر الإجراء الذي تريد تنفيذه:**",
            reply_markup=reply_markup
        )
        
        save_registration_progress(update.effective_user.id, 'SOCIAL_MEDIA_MENU', context.user_data)
        return SOCIAL_MEDIA_MENU
        
    except Exception as e:
        logger.error(f"❌ خطأ في show_social_media_menu: {e}")
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📱 **قائمة وسائل التواصل**\n\nحدث خطأ تقني. الرجاء اختيار أحد الخيارات:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📘 فيسبوك", callback_data="add_facebook")],
                [InlineKeyboardButton("📸 انستغرام", callback_data="add_instagram")],
                [InlineKeyboardButton("📺 يوتيوب", callback_data="add_youtube")],
                [InlineKeyboardButton("🔗 أخرى", callback_data="add_other")],
                [InlineKeyboardButton("✅ إنهاء", callback_data="skip_social")]
            ])
        )
        return SOCIAL_MEDIA_MENU

async def proceed_to_payment(update: Update, context: CallbackContext) -> int:
    """الانتقال إلى مرحلة اختيار طريقة الدفع"""
    try:
        # ⭐ التحقق إذا كنا في وضع التعديل لوسائل التواصل
        if context.user_data.get('editing_social'):
            # مسح العلامة أولاً
            del context.user_data['editing_social']
            
            # حفظ التقدم أولاً
            save_registration_progress(update.effective_user.id, 'EDIT_CHOICE', context.user_data)
            
            # إرسال رسالة تأكيد
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(
                    "✅ **تم تحديث وسائل التواصل بنجاح!**\n\n"
                    "🔁 **جاري العودة إلى قائمة التعديل...**"
                )
            else:
                await update.message.reply_text(
                    "✅ **تم تحديث وسائل التواصل بنجاح!**\n\n"
                    "🔁 **جاري العودة إلى قائمة التعديل...**"
                )
            
            # ⭐ التعديل الحاسم: استخدام context.bot.send_message بدلاً من العودة المباشرة
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="📋 **قائمة التعديل**\n\nاختر البيانات التي تريد تعديلها:"
            )
            return await show_edit_options(update, context)
        
        # إذا لم نكن في وضع التعديل، نستمر إلى طريقة الدفع كالمعتاد
        payment_keyboard = [['محفظة الكترونية', 'حوالة مالية']]
        reply_markup = ReplyKeyboardMarkup(payment_keyboard, one_time_keyboard=True)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.answer()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="✅ **تم حفظ جميع بيانات وسائل التواصل!**\n\n"
                     "💰 **الآن، اختر طريقة استلام المكافآت:**",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "✅ **تم حفظ جميع بيانات وسائل التواصل!**\n\n"
                "💰 **الآن، اختر طريقة استلام المكافآت:**",
                reply_markup=reply_markup
            )
        
        save_registration_progress(update.effective_user.id, 'PAYMENT_METHOD', context.user_data)
        return PAYMENT_METHOD
        
    except Exception as e:
        logger.error(f"❌ خطأ في proceed_to_payment: {e}")
        # استمرار العملية في حالة الخطأ
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ حدث خطأ تقني. جاري المتابعة..."
        )
        return PAYMENT_METHOD

async def get_payment_method(update: Update, context: CallbackContext) -> int:
    """استقبال طريقة الدفع المختارة من المستخدم"""
    payment_method = update.message.text
    context.user_data['payment_method'] = payment_method
    
    if payment_method == 'محفظة الكترونية':
        wallet_buttons = [ELECTRONIC_WALLETS[i:i+2] for i in range(0, len(ELECTRONIC_WALLETS), 2)]
        reply_markup = ReplyKeyboardMarkup(wallet_buttons, one_time_keyboard=True)
        
        await update.message.reply_text(
            "💳 **تم اختيار المحفظة الإلكترونية**\n\n"
            "👛 **اختر نوع المحفظة من القائمة:**",
            reply_markup=reply_markup
        )
        save_registration_progress(update.effective_user.id, 'WALLET_TYPE', context.user_data)
        return WALLET_TYPE
    elif payment_method == 'حوالة مالية':
        await update.message.reply_text(
            "💰 **تم اختيار الحوالة المالية**\n\n"
            "👤 **الرجاء إدخال الاسم الثلاثي الكامل المستخدم في الحوالة:**\n"
            "(يجب أن يتطابق مع الاسم في الوثائق الرسمية)"
        )
        save_registration_progress(update.effective_user.id, 'TRANSFER_DETAILS', context.user_data)
        return TRANSFER_DETAILS
    else:
        await update.message.reply_text(
            "❌ الرجاء اختيار طريقة دفع صحيحة:\n"
            "• محفظة الكترونية\n"
            "• حوالة مالية"
        )
        return PAYMENT_METHOD

async def get_wallet_type(update: Update, context: CallbackContext) -> int:
    """استقبال نوع المحفظة الإلكترونية من المستخدم - النسخة المحسنة"""
    try:
        wallet_type = update.message.text
        
        wallet_buttons = [WALLET_CHOICES[i:i+2] for i in range(0, len(WALLET_CHOICES), 2)]
        
        if wallet_type not in WALLET_CHOICES:
            await update.message.reply_text(
                "❌ الرجاء اختيار نوع محفظة من القائمة المحددة.",
                reply_markup=ReplyKeyboardMarkup(wallet_buttons, one_time_keyboard=True)
            )
            return WALLET_TYPE
        
        if wallet_type == "محفظة أخرى":
            await update.message.reply_text(
                "🆕 **إضافة محفظة جديدة**\n\n"
                "📝 **أدخل اسم المحفظة الجديدة:**\n"
                "(الحد الأقصى 20 حرف فقط)\n\n"
                "مثال: Binance, Trust Wallet, إلخ...",
                reply_markup=ReplyKeyboardRemove()
            )
            save_registration_progress(update.effective_user.id, 'NEW_WALLET_TYPE', context.user_data)
            return NEW_WALLET_TYPE
        else:
            context.user_data['wallet_type'] = wallet_type
            await update.message.reply_text(
                f"✅ تم اختيار نوع المحفظة: {wallet_type}\n\n"
                "🔗 **الآن، أدخل عنوان المحفظة الإلكترونية:**\n"
                "(انسخ العنوان كما هو من تطبيق المحفظة)\n\n"
                "مثال: 0x742d35Cc6634C0532925a3b8D...",
                reply_markup=ReplyKeyboardRemove()
            )
            save_registration_progress(update.effective_user.id, 'WALLET_ADDRESS', context.user_data)
            return WALLET_ADDRESS
            
    except Exception as e:
        logger.error(f"❌ خطأ في get_wallet_type: {e}")
        wallet_buttons = [WALLET_CHOICES[i:i+2] for i in range(0, len(WALLET_CHOICES), 2)]
        await update.message.reply_text(
            "❌ حدث خطأ. الرجاء اختيار نوع المحفظة مرة أخرى:",
            reply_markup=ReplyKeyboardMarkup(wallet_buttons, one_time_keyboard=True)
        )
        return WALLET_TYPE

async def get_new_wallet_type(update: Update, context: CallbackContext) -> int:
    """استقبال اسم المحفظة الجديدة يدوياً من المستخدم"""
    try:
        wallet_name = update.message.text.strip()
        
        if len(wallet_name) > 20:
            await update.message.reply_text(
                f"❌ اسم المحفظة طويل جداً!\n\n"
                f"📏 عدد الأحرف المدخلة: {len(wallet_name)}\n"
                f"📋 الحد الأقصى المسموح: 20 حرف\n\n"
                "📝 **أعد إدخال اسم المحفظة:**\n"
                "(اسم قصير لا يتجاوز 20 حرف)"
            )
            return NEW_WALLET_TYPE
        
        if len(wallet_name) < 2:
            await update.message.reply_text(
                "❌ اسم المحفظة قصير جداً!\n\n"
                "📝 **أعد إدخال اسم المحفظة:**\n"
                "(اسم معنوي لا يقل عن حرفين)"
            )
            return NEW_WALLET_TYPE
        
        context.user_data['wallet_type'] = wallet_name
        
        await update.message.reply_text(
            f"✅ **تم إضافة المحفظة الجديدة:** {wallet_name}\n\n"
            "🔗 **الآن، أدخل عنوان المحفظة الإلكترونية:**\n"
            "(انسخ العنوان كما هو من تطبيق المحفظة)\n\n"
            "مثال: 0x742d35Cc6634C0532925a3b8D... أو TBiPajvQcR..."
        )
        save_registration_progress(update.effective_user.id, 'WALLET_ADDRESS', context.user_data)
        return WALLET_ADDRESS
        
    except Exception as e:
        logger.error(f"❌ خطأ في get_new_wallet_type: {e}")
        await update.message.reply_text("❌ حدث خطأ في حفظ اسم المحفظة. الرجاء إعادة الإدخال:")
        return NEW_WALLET_TYPE

async def get_wallet_address(update: Update, context: CallbackContext) -> int:
    """استقبال عنوان المحفظة الإلكترونية من المستخدم - مع دعم التعديل"""
    wallet_address = update.message.text.strip()
    
    if len(wallet_address) < 5:
        await update.message.reply_text(
            "❌ عنوان المحفظة قصير جداً!\n"
            "الرجاء إدخال عنوان محفظة صحيح"
        )
        return WALLET_ADDRESS
    
    context.user_data['wallet_address'] = wallet_address
    save_registration_progress(update.effective_user.id, 'CONFIRMATION', context.user_data)
    
    # ⭐ التحقق إذا كنا في وضع التعديل
    if context.user_data.get('editing_payment'):
        # مسح العلامة والعودة للقائمة
        del context.user_data['editing_payment']
        await update.message.reply_text(
            "✅ **تم تحديث بيانات المحفظة بنجاح!**\n\n"
            "🔁 **جاري العودة إلى قائمة التعديل...**"
        )
        return await show_edit_options(update, context)
    
    return await show_confirmation(update, context)

async def get_transfer_details(update: Update, context: CallbackContext) -> int:
    """استقبال تفاصيل الحوالة المالية من المستخدم"""
    user_data = context.user_data
    
    if 'transfer_full_name' not in user_data:
        full_name = update.message.text.strip()
        name_parts = full_name.split()
        if len(name_parts) < 3:
            await update.message.reply_text(
                "❌ الرجاء إدخال الاسم الثلاثي الكامل (الاسم الأول + الأب + الجد)\n"
                "أعد إدخال الاسم:"
            )
            return TRANSFER_DETAILS

        if len(full_name) > 50:
            await update.message.reply_text(
                "❌ الاسم طويل جداً! الحد الأقصى هو 50 حرف\n\n"
                f"📏 عدد أحرف الاسم الذي أدخلته: {len(full_name)}\n"
                "✂️ الرجاء اختصار الاسم وإعادة إدخاله"
            )
            return TRANSFER_DETAILS
        
        user_data['transfer_full_name'] = full_name
        save_registration_progress(update.effective_user.id, 'TRANSFER_PHONE', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم حفظ اسم المستلم: {full_name}\n\n"
            "📞 **الآن، أدخل رقم هاتف المستلم:**\n"
            "(يجب أن يكون رقم هاتف نشط)"
        )
        return TRANSFER_PHONE
    
    elif 'transfer_phone' not in user_data:
        phone_input = update.message.text
        country_code = user_data.get('country_code', '+966')
        
        is_valid, formatted_phone, message = validate_phone_with_country(phone_input, country_code)
        
        if not is_valid:
            await update.message.reply_text(
                f"{message}\n\n"
                f"📞 الرجاء إدخال رقم هاتف صحيح:\n"
                f"(أدخل الرقم فقط، مثال: 512345678)"
            )
            return TRANSFER_PHONE
        
        user_data['transfer_phone'] = formatted_phone
        save_registration_progress(update.effective_user.id, 'TRANSFER_LOCATION', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم حفظ هاتف المستلم: {formatted_phone}\n\n"
            "📍 **الآن، أدخل موقع استلام الحوالة:**\n"
            "(المدينة والمنطقة، مثال: الرياض - الملك فهد)"
        )
        return TRANSFER_LOCATION
    
    elif 'transfer_location' not in user_data:
        location = update.message.text.strip()
        
        if len(location) < 5:
            await update.message.reply_text(
                "❌ الموقع قصير جداً!\n"
                "الرجاء إدخال موقع مفصل"
            )
            return TRANSFER_LOCATION
        
        user_data['transfer_location'] = location
        save_registration_progress(update.effective_user.id, 'TRANSFER_COMPANY', context.user_data)
        
        company_buttons = [TRANSFER_COMPANIES[i:i+2] for i in range(0, len(TRANSFER_COMPANIES), 2)]
        reply_markup = ReplyKeyboardMarkup(company_buttons, one_time_keyboard=True)
        
        await update.message.reply_text(
            f"✅ تم حفظ الموقع: {location}\n\n"
            "🏢 **الآن، اختر شركة الحوالة من القائمة:**",
            reply_markup=reply_markup
        )
        return TRANSFER_COMPANY
    
    else:
        company = update.message.text
        if company not in TRANSFER_COMPANIES:
            await update.message.reply_text("❌ الرجاء اختيار شركة من القائمة المحددة.")
            return TRANSFER_COMPANY
        
        user_data['transfer_company'] = company
        save_registration_progress(update.effective_user.id, 'CONFIRMATION', context.user_data)
        
        # ⭐ التحقق إذا كنا في وضع التعديل
        if context.user_data.get('editing_payment'):
            # مسح العلامة والعودة للقائمة
            del context.user_data['editing_payment']
            await update.message.reply_text(
                "✅ **تم تحديث بيانات الحوالة بنجاح!**\n\n"
                "🔁 **جاري العودة إلى قائمة التعديل...**"
            )
            return await show_edit_options(update, context)
        
        return await show_confirmation(update, context)

async def show_confirmation(update: Update, context: CallbackContext) -> int:
    """عرض ملخص البيانات النهائي للمستخدم للتأكيد"""
    user_data = context.user_data
    social_data = user_data.get('social_media', {'facebook': [], 'instagram': [], 'youtube': [], 'other': []})
    
    confirmation_text = f"""
📋 **الرجاء مراجعة بياناتك قبل التأكيد:**

👤 **البيانات الشخصية:**
• الاسم: {user_data.get('full_name')}
• البلد: {user_data.get('country')}
• الجنس: {user_data.get('gender')}
• سنة الولادة: {user_data.get('birth_year')}
• الهاتف: {user_data.get('phone_number')}
• البريد الإلكتروني: {user_data.get('email')}

🔗 **وسائل التواصل:**
• فيسبوك: {len(social_data['facebook'])} حساب
• انستغرام: {len(social_data['instagram'])} حساب
• يوتيوب: {len(social_data['youtube'])} قناة
• روابط أخرى: {len(social_data['other'])} رابط
"""
    
    confirmation_text += f"\n💰 **طريقة الدفع: {user_data.get('payment_method')}**\n"
    
    if user_data.get('payment_method') == 'محفظة الكترونية':
        confirmation_text += f"• نوع المحفظة: {user_data.get('wallet_type')}\n"
        confirmation_text += f"• العنوان: {user_data.get('wallet_address')}\n"
    else:
        confirmation_text += f"• اسم المستلم: {user_data.get('transfer_full_name')}\n"
        confirmation_text += f"• هاتف المستلم: {user_data.get('transfer_phone')}\n"
        confirmation_text += f"• الموقع: {user_data.get('transfer_location')}\n"
        confirmation_text += f"• الشركة: {user_data.get('transfer_company')}\n"
    
    confirmation_text += "\n✅ **هل جميع البيانات صحيحة؟**"
    
    keyboard = [
        [InlineKeyboardButton("✅ نعم، حفظ البيانات", callback_data="confirm_yes")],
        [InlineKeyboardButton("✏️ تعديل البيانات", callback_data="confirm_edit")],
        [InlineKeyboardButton("❌ إلغاء التسجيل", callback_data="confirm_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(confirmation_text, reply_markup=reply_markup)
    elif hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text(confirmation_text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=confirmation_text,
            reply_markup=reply_markup
        )
    
    return CONFIRMATION

async def handle_confirmation(update: Update, context: CallbackContext) -> int:
    """معالجة رد المستخدم على تأكيد البيانات"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_yes":
        success = await save_all_data(update, context)
        if success:
            return await show_final_summary(update, context)
        else:
            await query.edit_message_text("❌ فشل في حفظ البيانات. الرجاء المحاولة مرة أخرى.")
            return ConversationHandler.END
    elif query.data == "confirm_edit":
        return await show_edit_options(update, context)
    else:
        await query.edit_message_text(
            "❌ **تم إلغاء التسجيل**\n\n"
            "يمكنك البدء من جديد باستخدام الأمر /start\n\n"
            "💡 للاستفسارات، استخدم /support"
        )
        return ConversationHandler.END

async def save_all_data(update: Update, context: CallbackContext) -> bool:
    """حفظ جميع البيانات في قاعدة البيانات - الإصدار المصحح"""
    conn = None
    try:
        conn = create_connection()
        if not conn:
            logger.error("❌ فشل الاتصال بقاعدة البيانات في save_all_data")
            return False
            
        cursor = conn.cursor()
        user_data = context.user_data
        user_id = update.effective_user.id

        # إنشاء كود إحالة فريد
        referral_code = generate_referral_code()
        
        # 1. حفظ البيانات الشخصية
        cursor.execute('''
            INSERT INTO user_profiles 
            (user_id, telegram_username, email, referral_code, invited_by, full_name, country, gender, birth_year, phone_number)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            user_id,
            user_data.get('telegram_username'),
            user_data.get('email'),
            referral_code,
            user_data.get('invited_by'),
            user_data.get('full_name'),
            user_data.get('country'),
            user_data.get('gender'),
            user_data.get('birth_year'),
            user_data.get('phone_number')
        ))

        # 2. حفظ روابط التواصل الاجتماعي
        social_data = user_data.get('social_media', {'facebook': [], 'instagram': [], 'youtube': [], 'other': []})
        
        for url in social_data.get('facebook', []):
            cursor.execute(
                "INSERT INTO user_links (user_id, platform, url) VALUES (%s, %s, %s)",
                (user_id, 'Facebook', url)
            )
        
        for url in social_data.get('instagram', []):
            cursor.execute(
                "INSERT INTO user_links (user_id, platform, url) VALUES (%s, %s, %s)",
                (user_id, 'Instagram', url)
            )
        
        for url in social_data.get('youtube', []):
            cursor.execute(
                "INSERT INTO user_links (user_id, platform, url) VALUES (%s, %s, %s)",
                (user_id, 'YouTube', url)
            )
        
        for url in social_data.get('other', []):
            platform = "Other"
            if 'twitter.com' in url:
                platform = "Twitter"
            elif 'linkedin.com' in url:
                platform = "LinkedIn"
            elif 'tiktok.com' in url:
                platform = "TikTok"
            elif 'snapchat.com' in url:
                platform = "Snapchat"
            elif 'youtube.com' in url:
                platform = "YouTube"
            elif 'telegram.me' in url:
                platform = "Telegram"
            
            cursor.execute(
                "INSERT INTO user_links (user_id, platform, url) VALUES (%s, %s, %s)",
                (user_id, platform, url)
            )

        # 3. حفظ بيانات الدفع
        if user_data.get('payment_method') == 'محفظة الكترونية':
            cursor.execute('''
                INSERT INTO user_payments 
                (user_id, payment_method, wallet_type, wallet_address)
                VALUES (%s, %s, %s, %s)
            ''', (
                user_id,
                user_data.get('payment_method'),
                user_data.get('wallet_type'),
                user_data.get('wallet_address')
            ))
        else:
            cursor.execute('''
                INSERT INTO user_payments 
                (user_id, payment_method, transfer_full_name, transfer_phone, transfer_location, transfer_company)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (
                user_id,
                user_data.get('payment_method'),
                user_data.get('transfer_full_name'),
                user_data.get('transfer_phone'),
                user_data.get('transfer_location'),
                user_data.get('transfer_company')
            ))

        conn.commit()
        logger.info(f"✅ تم حفظ بيانات المستخدم {user_id} بنجاح")

        # تحديث عداد الإحالات
        if user_data.get('invited_by'):
            update_referral_count(user_data.get('invited_by'))

        # حذف تقدم التسجيل
        delete_registration_progress(user_id)
        
        context.user_data['referral_code'] = referral_code
        return True

    except Exception as e:
        logger.error(f"❌ خطأ في حفظ البيانات: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            cursor.close()
            conn.close()

async def show_final_summary(update: Update, context: CallbackContext) -> int:
    """عرض الملخص النهائي بعد اكتمال التسجيل"""
    user_data = context.user_data
    social_data = user_data.get('social_media', {'facebook': [], 'instagram': [], 'youtube': [], 'other': []})
    referral_code = context.user_data.get('referral_code', 'غير متوفر')
    
    summary = f"""
🎉 **تم تسجيل بياناتك بنجاح!** ✅

🏢 **مرحباً بك في مؤسسة الترويج الإعلامي**

📋 **البيانات المسجلة:**
👤 الاسم: {user_data.get('full_name')}
🚻 الجنس: {user_data.get('gender')}
🌍 البلد: {user_data.get('country')}
🎂 سنة الولادة: {user_data.get('birth_year')}
📞 الهاتف: {user_data.get('phone_number')}
📧 البريد الإلكتروني: {user_data.get('email')}

🔗 **وسائل التواصل المسجلة:**
📘 فيسبوك: {len(social_data['facebook'])} حساب
📸 انستغرام: {len(social_data['instagram'])} حساب
📺 يوتيوب: {len(social_data['youtube'])} قناة
🔗 روابط أخرى: {len(social_data['other'])} رابط
"""
    
    summary += f"\n💰 **طريقة استلام المكافآت: {user_data.get('payment_method')}**"
    
    if user_data.get('payment_method') == 'محفظة الكترونية':
        summary += f"\n👛 نوع المحفظة: {user_data.get('wallet_type')}"
        summary += f"\n🔗 عنوان المحفظة: {user_data.get('wallet_address')}"
    else:
        summary += f"""
👤 اسم المستلم: {user_data.get('transfer_full_name')}
📞 هاتف المستلم: {user_data.get('transfer_phone')}
📍 الموقع: {user_data.get('transfer_location')}
🏢 الشركة: {user_data.get('transfer_company')}"""

    summary += f"""

📢 **كود دعوتك الشخصي:** `{referral_code}`
👥 شارك هذا الكود مع أصدقائك لتحصل على مكافآت إضافية!

💡 **التعليمات القادمة:**
• ستتلقى تعليمات التفاعل مع المنشورات قريباً
• تأكد من متابعة قناتنا للحصول على التحديثات
• سيتم التواصل معك عبر هذا البوت

🔧 **الأوامر المتاحة:**
/start - بدء تسجيل جديد
/profile - عرض ملفك الشخصي  
/invite - عرض كود الدعوة والإحصائيات
/support - التواصل مع الدعم الفني
"""

    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.message.reply_text(summary, parse_mode='Markdown')
    else:
        await update.message.reply_text(summary, parse_mode='Markdown')
    
    return ConversationHandler.END

# ==============================
# 🔧 الأوامر الإضافية
# ==============================

async def show_profile(update: Update, context: CallbackContext):
    """عرض الملف الشخصي للمستخدم"""
    try:
        user_id = update.effective_user.id
        if not await check_user_registration(user_id):
            await update.message.reply_text("❌ لم يتم العثور على ملفك الشخصي")
            return
        
        conn = create_connection()
        if not conn:
            await update.message.reply_text("❌ فشل الاتصال بقاعدة البيانات")
            return
            
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT up.referral_code, up.invited_by, up.full_name, up.country, 
                   up.gender, up.birth_year, up.phone_number, up.email, up.total_referrals,
                   up.registration_date, up.status
            FROM user_profiles up
            WHERE up.user_id = %s
        ''', (user_id,))
        
        profile = cursor.fetchone()
        
        if not profile:
            await update.message.reply_text("❌ لم يتم العثور على ملفك الشخصي!")
            return
        
        cursor.execute('SELECT platform, url FROM user_links WHERE user_id = %s ORDER BY platform', (user_id,))
        links = cursor.fetchall()
        
        cursor.execute('''
            SELECT payment_method, wallet_type, wallet_address, transfer_full_name, 
                   transfer_phone, transfer_location, transfer_company
            FROM user_payments WHERE user_id = %s
        ''', (user_id,))
        
        payment = cursor.fetchone()
        cursor.close()
        conn.close()
        
        message = f"""
📋 **ملفك الشخصي - مؤسسة الترويج الإعلامي**

👤 **المعلومات الشخصية:**
🆔 كود الدعوة: `{profile[0]}`
👥 مدعو بواسطة: {profile[1] or 'لا أحد'}
📛 الاسم: {profile[2]}
🌍 البلد: {profile[3]}
🚻 الجنس: {profile[4]}
🎂 سنة الولادة: {profile[5]}
📞 الهاتف: {profile[6]}
📧 البريد الإلكتروني: {profile[7]}
👥 عدد المُحالين: {profile[8]}
📅 تاريخ التسجيل: {profile[9].strftime('%Y-%m-%d')}
✅ الحالة: {profile[10]}

🔗 **روابط التواصل:**
"""
        
        for link in links:
            message += f"• {link[0]}: {link[1]}\n"
        
        if not links:
            message += "❌ لا توجد روابط مسجلة\n"
        
        message += f"\n💰 **طريقة استلام المكافآت: {payment[0] if payment else 'غير محدد'}**\n"
        
        if payment and payment[0] == 'محفظة الكترونية':
            message += f"👛 نوع المحفظة: {payment[1]}\n"
            message += f"🔗 عنوان المحفظة: {payment[2]}\n"
        elif payment and payment[0] == 'حوالة مالية':
            message += f"""
👤 اسم المستلم: {payment[3]}
📞 هاتف المستلم: {payment[4]}
📍 الموقع: {payment[5]}
🏢 الشركة: {payment[6]}"""
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text("❌ حدث خطأ في عرض الملف الشخصي")
        logger.error(f"Error: {e}")

async def show_invite(update: Update, context: CallbackContext):
    """عرض كود الدعوة والإحصائيات"""
    try:
        user_id = update.effective_user.id
        
        conn = create_connection()
        if not conn:
            await update.message.reply_text("❌ فشل الاتصال بقاعدة البيانات")
            return
        cursor = conn.cursor()
        
        cursor.execute('SELECT referral_code, total_referrals FROM user_profiles WHERE user_id = %s', (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not result:
            await update.message.reply_text("❌ لم يتم العثور على بياناتك!")
            return
        
        referral_code, total_referrals = result
        
        message = f"""
📢 **نظام الدعوة والإحالة**

🆔 **كود دعوتك الشخصي:** `{referral_code}`

👥 **عدد الأشخاص الذين دعوتهم:** {total_referrals}

🔗 **كيفية استخدام كود الدعوة:**
1. شارك هذا الكود مع أصدقائك: `{referral_code}`
2. عندما يسجل صديق باستخدام كودك، تحصل على نقطة
3. كلما زاد عدد المدعوين، زادت مكافآتك!

💡 **طريقة التسجيل:**
أرسل هذا الرابط لأصدقائك:
https://t.me/{(await context.bot.get_me()).username}?start={referral_code}

🎁 **المكافآت:**
• 5 مدعوين: مكافأة خاصة
• 10 مدعوين: مكافأة أكبر  
• 20 مدعوين: مكافأة مميزة
• 50 مدعوين: مكافأة استثنائية
"""
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text("❌ حدث خطأ في عرض معلومات الدعوة")
        logger.error(f"Error: {e}")

async def support_command(update: Update, context: CallbackContext):
    """عرض معلومات الدعم الفني"""
    support_text = """
🆘 **الدعم الفني**

📞 للاستفسارات والمشاكل التقنية:

💬 **طرق التواصل:**
• عبر البوت: اكتب رسالتك وسيتم الرد عليك
• البريد الإلكتروني: support@example.com
• الهاتف: +966500000000

⏰ **أوقات العمل:**
• الأحد - الخميس: 9:00 ص - 5:00 م
• الجمعة والسبت: إجازة

🔧 **نحن هنا لمساعدتك في:**
• مشاكل التسجيل
• استفسارات حول المكافآت
• أي استفسارات أخرى
"""
    
    await update.message.reply_text(support_text)

async def cancel(update: Update, context: CallbackContext) -> int:
    """إلغاء عملية التسجيل"""
    await update.message.reply_text(
        "❌ **تم إلغاء التسجيل**\n\n"
        "يمكنك البدء من جديد باستخدام /start\n\n"
        "💡 للاستفسارات، استخدم /support"
    )
    return ConversationHandler.END

# ==============================
# ✏️ نظام التعديل
# ==============================

async def show_edit_options(update: Update, context: CallbackContext) -> int:
    """عرض خيارات التعديل مع البيانات الحالية"""
    try:
        user_data = context.user_data
        
        current_data = f"""
📋 **البيانات الحالية:**

👤 الاسم: {user_data.get('full_name', '❌ غير محدد')}
🌍 البلد: {user_data.get('country', '❌ غير محدد')}
🚻 الجنس: {user_data.get('gender', '❌ غير محدد')}
🎂 سنة الولادة: {user_data.get('birth_year', '❌ غير محدد')}
📞 الهاتف: {user_data.get('phone_number', '❌ غير محدد')}
📧 البريد: {user_data.get('email', '❌ غير محدد')}
💰 طريقة الدفع: {user_data.get('payment_method', '❌ غير محدد')}

✏️ **اختر البيانات التي تريد تعديلها:**
"""
        
        keyboard = [
            [InlineKeyboardButton(f"👤 تعديل الاسم", callback_data="edit_name")],
            [InlineKeyboardButton(f"🌍 تعديل البلد", callback_data="edit_country")],
            [InlineKeyboardButton(f"🚻 تعديل الجنس", callback_data="edit_gender")],
            [InlineKeyboardButton(f"🎂 تعديل سنة الولادة", callback_data="edit_birthyear")],
            [InlineKeyboardButton(f"📞 تعديل الهاتف", callback_data="edit_phone")],
            [InlineKeyboardButton(f"📧 تعديل البريد", callback_data="edit_email")],
            [InlineKeyboardButton("📱 تعديل وسائل التواصل", callback_data="edit_social")],
            [InlineKeyboardButton(f"💰 تعديل طريقة الدفع", callback_data="edit_payment")],
            [InlineKeyboardButton("✅ إنهاء التعديل والعودة", callback_data="edit_done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(current_data, reply_markup=reply_markup)
        else:
            await update.message.reply_text(current_data, reply_markup=reply_markup)
        
        save_registration_progress(update.effective_user.id, 'EDIT_CHOICE', context.user_data)
        return EDIT_CHOICE
        
    except Exception as e:
        logger.error(f"❌ خطأ في show_edit_options: {e}")
        
        keyboard = [
            [InlineKeyboardButton("👤 الاسم", callback_data="edit_name")],
            [InlineKeyboardButton("🌍 البلد", callback_data="edit_country")],
            [InlineKeyboardButton("🚻 الجنس", callback_data="edit_gender")],
            [InlineKeyboardButton("🎂 سنة الولادة", callback_data="edit_birthyear")],
            [InlineKeyboardButton("📞 الهاتف", callback_data="edit_phone")],
            [InlineKeyboardButton("📧 البريد الإلكتروني", callback_data="edit_email")],
            [InlineKeyboardButton("📱 وسائل التواصل", callback_data="edit_social")],
            [InlineKeyboardButton("💰 طريقة الدفع", callback_data="edit_payment")],
            [InlineKeyboardButton("✅ إنهاء التعديل", callback_data="edit_done")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                "✏️ **اختر البيانات التي تريد تعديلها:**",
                reply_markup=reply_markup
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="✏️ **اختر البيانات التي تريد تعديلها:**",
                reply_markup=reply_markup
            )
        return EDIT_CHOICE

async def handle_edit_choice(update: Update, context: CallbackContext) -> int:
    """معالجة اختيار التعديل من القائمة"""
    try:
        query = update.callback_query
        await query.answer()
        
        choice = query.data
        
        if choice == "edit_name":
            await query.edit_message_text(
                "✏️ **تعديل الاسم**\n\n"
                "أدخل الاسم الثلاثي الكامل الجديد:\n"
                "(مثال: أحمد محمد علي)\n\n"
                f"📝 **الاسم الحالي:** {context.user_data.get('full_name', 'غير محدد')}"
            )
            return EDIT_FULL_NAME
            
        elif choice == "edit_country":
            country_buttons = [list(COUNTRIES.keys())[i:i+2] for i in range(0, len(COUNTRIES), 2)]
            reply_markup = ReplyKeyboardMarkup(country_buttons, one_time_keyboard=True)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✏️ **تعديل البلد**\n\nاختر بلدك الجديد من القائمة:\n\n🌍 **البلد الحالي:** {context.user_data.get('country', 'غير محدد')}",
                reply_markup=reply_markup
            )
            return EDIT_COUNTRY
            
        elif choice == "edit_gender":
            gender_keyboard = [['ذكر', 'أنثى']]
            reply_markup = ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✏️ **تعديل الجنس**\n\nاختر جنسك الجديد:\n\n🚻 **الجنس الحالي:** {context.user_data.get('gender', 'غير محدد')}",
                reply_markup=reply_markup
            )
            return EDIT_GENDER
            
        elif choice == "edit_birthyear":
            await query.edit_message_text(
                "✏️ **تعديل سنة الولادة**\n\n"
                "أدخل سنة الولادة الجديدة:\n"
                "(أدخل السنة بأربعة أرقام، مثال: 1990)\n\n"
                f"🎂 **سنة الولادة الحالية:** {context.user_data.get('birth_year', 'غير محدد')}"
            )
            return EDIT_BIRTH_YEAR
            
        elif choice == "edit_phone":
            country_code = context.user_data.get('country_code', '+966')
            await query.edit_message_text(
                f"✏️ **تعديل رقم الهاتف**\n\n"
                f"أدخل رقم الهاتف الجديد:\n"
                f"سيتم إضافة رمز الدولة {country_code} تلقائياً\n"
                f"(أدخل الرقم فقط، مثال: 512345678)\n\n"
                f"📞 **الهاتف الحالي:** {context.user_data.get('phone_number', 'غير محدد')}"
            )
            return EDIT_PHONE
            
        elif choice == "edit_email":
            await query.edit_message_text(
                "✏️ **تعديل البريد الإلكتروني**\n\n"
                "أدخل البريد الإلكتروني الجديد:\n"
                "(مثال: yourname@example.com)\n\n"
                f"📧 **البريد الحالي:** {context.user_data.get('email', 'غير محدد')}"
            )
            return EDIT_EMAIL
            
        elif choice == "edit_social":
            # ⭐ الإضافة: وضع علامة أننا في وضع التعديل لوسائل التواصل
            context.user_data['editing_social'] = True
            await query.edit_message_text(
                "📱 **تعديل وسائل التواصل**\n\n"
                "جاري الانتقال إلى قائمة إدارة الحسابات..."
            )
            return await show_social_media_menu(update, context)
            
        elif choice == "edit_payment":
            payment_keyboard = [['محفظة الكترونية', 'حوالة مالية']]
            reply_markup = ReplyKeyboardMarkup(payment_keyboard, one_time_keyboard=True)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✏️ **تعديل طريقة الدفع**\n\nاختر طريقة الدفع الجديدة:\n\n💰 **الطريقة الحالية:** {context.user_data.get('payment_method', 'غير محدد')}",
                reply_markup=reply_markup
            )
            return EDIT_PAYMENT_METHOD
            
        else:  # edit_done
            await query.edit_message_text(
                "✅ **تم إنهاء التعديل**\n\n"
                "جاري العودة لمراجعة البيانات النهائية..."
            )
            return await show_confirmation(update, context)
            
    except Exception as e:
        logger.error(f"❌ خطأ في handle_edit_choice: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ حدث خطأ في التعديل. جاري العودة للتأكيد..."
        )
        return await show_confirmation(update, context)

async def edit_full_name(update: Update, context: CallbackContext) -> int:
    """تعديل الاسم الكامل"""
    try:
        full_name = update.message.text.strip()
        
        name_parts = full_name.split()
        if len(name_parts) < 3:
            await update.message.reply_text(
                "❌ الرجاء إدخال الاسم الثلاثي الكامل (الاسم الأول + الأب + الكنية)\n"
                "(مثال: أحمد محمد علي)\n\n"
                "✏️ أعد إدخال الاسم:"
            )
            return EDIT_FULL_NAME

        if len(full_name) > 50:
            await update.message.reply_text(
                "❌ الاسم طويل جداً! الحد الأقصى هو 50 حرف\n\n"
                f"📏 عدد أحرف الاسم الذي أدخلته: {len(full_name)}\n"
                "✂️ الرجاء اختصار الاسم وإعادة إدخاله:"
            )
            return EDIT_FULL_NAME
        
        context.user_data['full_name'] = full_name
        save_registration_progress(update.effective_user.id, 'EDIT_CHOICE', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم تعديل الاسم إلى: {full_name}\n\n"
            "✏️ **اختر البيانات الأخرى التي تريد تعديلها:**"
        )
        return await show_edit_options(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في edit_full_name: {e}")
        await update.message.reply_text("❌ حدث خطأ في تعديل الاسم. جاري العودة للقائمة...")
        return await show_edit_options(update, context)

async def edit_country(update: Update, context: CallbackContext) -> int:
    """تعديل البلد"""
    try:
        country = update.message.text
        
        if country not in COUNTRIES:
            await update.message.reply_text("❌ الرجاء اختيار بلد من القائمة المحددة.")
            return EDIT_COUNTRY
        
        context.user_data['country'] = country
        context.user_data['country_code'] = COUNTRIES[country]
        save_registration_progress(update.effective_user.id, 'EDIT_CHOICE', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم تعديل البلد إلى: {country}\n\n"
            "✏️ **اختر البيانات الأخرى التي تريد تعديلها:**"
        )
        return await show_edit_options(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في edit_country: {e}")
        await update.message.reply_text("❌ حدث خطأ في تعديل البلد. جاري العودة للقائمة...")
        return await show_edit_options(update, context)

async def edit_gender(update: Update, context: CallbackContext) -> int:
    """تعديل الجنس"""
    try:
        gender = update.message.text
        
        if gender not in ['ذكر', 'أنثى']:
            await update.message.reply_text("❌ الرجاء اختيار 'ذكر' أو 'أنثى'.")
            return EDIT_GENDER
        
        context.user_data['gender'] = gender
        save_registration_progress(update.effective_user.id, 'EDIT_CHOICE', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم تعديل الجنس إلى: {gender}\n\n"
            "✏️ **اختر البيانات الأخرى التي تريد تعديلها:**"
        )
        return await show_edit_options(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في edit_gender: {e}")
        await update.message.reply_text("❌ حدث خطأ في تعديل الجنس. جاري العودة للقائمة...")
        return await show_edit_options(update, context)

async def edit_birth_year(update: Update, context: CallbackContext) -> int:
    """تعديل سنة الولادة"""
    try:
        year = update.message.text
        is_valid, year_int = validate_birth_year(year)
        
        if not is_valid:
            await update.message.reply_text(
                "❌ سنة الولادة غير صحيحة!\n"
                "الرجاء إدخال سنة صحيحة (مثال: 1990)\n\n"
                "✏️ أعد إدخال سنة الولادة:"
            )
            return EDIT_BIRTH_YEAR
        
        context.user_data['birth_year'] = year_int
        save_registration_progress(update.effective_user.id, 'EDIT_CHOICE', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم تعديل سنة الولادة إلى: {year_int}\n\n"
            "✏️ **اختر البيانات الأخرى التي تريد تعديلها:**"
        )
        return await show_edit_options(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في edit_birth_year: {e}")
        await update.message.reply_text("❌ حدث خطأ في تعديل سنة الولادة. جاري العودة للقائمة...")
        return await show_edit_options(update, context)

async def edit_phone(update: Update, context: CallbackContext) -> int:
    """تعديل رقم الهاتف"""
    try:
        phone_input = update.message.text
        country_code = context.user_data.get('country_code', '+966')
        
        is_valid, formatted_phone, message = validate_phone_with_country(phone_input, country_code)
        
        if not is_valid:
            await update.message.reply_text(
                f"{message}\n\n"
                f"📞 الرجاء إدخال رقم هاتف صحيح:\n"
                f"(أدخل الرقم فقط، مثال: 512345678)\n\n"
                "✏️ أعد إدخال رقم الهاتف:"
            )
            return EDIT_PHONE
        
        context.user_data['phone_number'] = formatted_phone
        save_registration_progress(update.effective_user.id, 'EDIT_CHOICE', context.user_data)
        
        await update.message.reply_text(
            f"✅ {message}\n\n"
            "✏️ **اختر البيانات الأخرى التي تريد تعديلها:**"
        )
        return await show_edit_options(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في edit_phone: {e}")
        await update.message.reply_text("❌ حدث خطأ في تعديل الهاتف. جاري العودة للقائمة...")
        return await show_edit_options(update, context)

async def edit_email(update: Update, context: CallbackContext) -> int:
    """تعديل البريد الإلكتروني"""
    try:
        email = update.message.text.strip()
        
        if not validate_email(email):
            await update.message.reply_text(
                "❌ البريد الإلكتروني غير صحيح!\n"
                "الرجاء إدخال بريد إلكتروني صالح (مثال: user@example.com)\n\n"
                "✏️ أعد إدخال البريد الإلكتروني:"
            )
            return EDIT_EMAIL
        
        context.user_data['email'] = email
        save_registration_progress(update.effective_user.id, 'EDIT_CHOICE', context.user_data)
        
        await update.message.reply_text(
            f"✅ تم تعديل البريد الإلكتروني إلى: {email}\n\n"
            "✏️ **اختر البيانات الأخرى التي تريد تعديلها:**"
        )
        return await show_edit_options(update, context)
        
    except Exception as e:
        logger.error(f"❌ خطأ في edit_email: {e}")
        await update.message.reply_text("❌ حدث خطأ في تعديل البريد الإلكتروني. جاري العودة للقائمة...")
        return await show_edit_options(update, context)

async def edit_payment_method(update: Update, context: CallbackContext) -> int:
    """تعديل طريقة الدفع - النسخة المصححة"""
    try:
        payment_method = update.message.text
        context.user_data['payment_method'] = payment_method
        
        payment_keys = ['wallet_type', 'wallet_address', 'transfer_full_name', 
                       'transfer_phone', 'transfer_location', 'transfer_company']
        for key in payment_keys:
            if key in context.user_data:
                del context.user_data[key]
        
        # ⭐ الإضافة: وضع علامة أننا في وضع التعديل
        context.user_data['editing_payment'] = True
        
        if payment_method == 'محفظة الكترونية':
            wallet_buttons = [ELECTRONIC_WALLETS[i:i+2] for i in range(0, len(ELECTRONIC_WALLETS), 2)]
            reply_markup = ReplyKeyboardMarkup(wallet_buttons, one_time_keyboard=True)
            
            await update.message.reply_text(
                "💳 **تم تعديل طريقة الدفع إلى: المحفظة الإلكترونية**\n\n"
                "👛 **الآن اختر نوع المحفظة من القائمة:**",
                reply_markup=reply_markup
            )
            save_registration_progress(update.effective_user.id, 'WALLET_TYPE', context.user_data)
            return WALLET_TYPE
            
        elif payment_method == 'حوالة مالية':
            await update.message.reply_text(
                "💰 **تم تعديل طريقة الدفع إلى: الحوالة المالية**\n\n"
                "👤 **الرجاء إدخال الاسم الثلاثي الكامل المستخدم في الحوالة:**\n"
                "(يجب أن يتطابق مع الاسم في الوثائق الرسمية)"
            )
            save_registration_progress(update.effective_user.id, 'TRANSFER_DETAILS', context.user_data)
            return TRANSFER_DETAILS
            
        else:
            await update.message.reply_text(
                "❌ الرجاء اختيار طريقة دفع صحيحة:\n"
                "• محفظة الكترونية\n"
                "• حوالة مالية"
            )
            return EDIT_PAYMENT_METHOD
            
    except Exception as e:
        logger.error(f"❌ خطأ في edit_payment_method: {e}")
        await update.message.reply_text("❌ حدث خطأ في تعديل طريقة الدفع. جاري العودة للقائمة...")
        return await show_edit_options(update, context)

async def new_start(update: Update, context: CallbackContext) -> int:
    """بدء تسجيل جديد مع حذف التقدم القديم"""
    user = update.message.from_user
    
    delete_registration_progress(user.id)
    context.user_data.clear()
    
    context.user_data['telegram_username'] = user.username
    context.user_data['user_id'] = user.id
    context.user_data['social_media'] = {'facebook': [], 'instagram': [], 'youtube': [], 'other': []}
    
    save_registration_progress(user.id, 'REFERRAL_STAGE', context.user_data)
    
    await update.message.reply_text(
        f"🆕 **بدء تسجيل جديد {user.first_name}!**\n\n"
        "📋 **هل تمت دعوتك من قبل أحد الأعضاء؟**\n"
        "إذا كان لديك كود دعوة، الرجاء إدخاله الآن.\n"
        "إذا لم يكن لديك، اكتب 'لا' للمتابعة."
    )
    
    return REFERRAL_STAGE

async def bot_stats(update: Update, context: CallbackContext):
    """عرض إحصائيات البوت (للمالك فقط)"""
    user = update.message.from_user
    
    if user.id != OWNER_USER_ID:
        await update.message.reply_text("🚫 هذا الأمر متاح للمالك فقط.")
        return
    
    try:
        conn = create_connection()
        if not conn:
            await update.message.reply_text("❌ فشل الاتصال بقاعدة البيانات")
            return
            
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM user_profiles")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE status = 'active'")
        active_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(total_referrals) FROM user_profiles")
        total_referrals = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM user_profiles WHERE DATE(registration_date) = CURRENT_DATE")
        today_registrations = cursor.fetchone()[0]
        
        cursor.execute('SELECT full_name, total_referrals FROM user_profiles WHERE total_referrals > 0 ORDER BY total_referrals DESC LIMIT 5')
        top_referrers = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        stats_text = f"""
📊 **إحصائيات البوت - المؤسسة**

👥 **المستخدمين:**
• إجمالي المسجلين: {total_users}
• المستخدمين النشطين: {active_users}
• إجمالي الإحالات: {total_referrals}
• تسجيلات اليوم: {today_registrations}

🏆 **أعلى 5 محيلين:**
"""
        
        for i, (name, referrals) in enumerate(top_referrers, 1):
            stats_text += f"{i}. {name} - {referrals} إحالة\n"
        
        if not top_referrers:
            stats_text += "لا توجد إحالات بعد\n"
        
        stats_text += f"\n🔐 **البوت خاص ويعمل بنظام الدعوات فقط**"
        
        await update.message.reply_text(stats_text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ في جلب الإحصائيات: {e}")

# ==============================
# 💬 دوال نظام التعليقات
# ==============================

async def comment_system_start(update: Update, context: CallbackContext):
    """بدء نظام التعليقات - نسخة محسنة"""
    user_id = update.effective_user.id
    
    # التحقق من تسجيل المستخدم
    if not await check_user_registration(user_id):
        await update.message.reply_text(
            "❌ **يجب أن تكون مسجلاً في النظام أولاً**\n\n"
            "استخدم /start لتسجيل حساب جديد"
        )
        return
    
    # عرض خيارات نظام التعليقات
    keyboard = [
        [InlineKeyboardButton("📋 المهام المتاحة", callback_data="available_tasks")],
        [InlineKeyboardButton("📊 تقدمي في التعليقات", callback_data="my_comment_progress")],
        [InlineKeyboardButton("🔙 الرجوع للقائمة الرئيسية", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "💬 **نظام مكافآت التعليقات**\n\n"
        "🎯 **كيفية العمل:**\n"
        "• اختر مهمة تعليق من المهام المتاحة\n"
        "• اكتب تعليقاً على المنشور المطلوب\n" 
        "• احصل على مكافأة فور التحقق\n\n"
        "💰 **المميزات:**\n"
        "• مكافآت فورية\n"
        "• مهام متنوعة\n"
        "• مرونة في المشاركة\n\n"
        "اختر الخيار المناسب:",
        reply_markup=reply_markup
    )

async def handle_comment_main_menu(update: Update, context: CallbackContext):
    """معالجة خيارات القائمة الرئيسية لنظام التعليقات"""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
    if choice == "available_tasks":
        await start_comment_system(update, context)
    elif choice == "my_comment_progress":
        await show_comment_progress(update, context)
    elif choice == "main_menu":
        await query.edit_message_text(
            "🔙 **العودة إلى القائمة الرئيسية**\n\n"
            "استخدم الأوامر التالية:\n"
            "/start - بدء التسجيل\n"
            "/profile - عرض الملف الشخصي\n" 
            "/invite - كود الدعوة\n"
            "/comments - نظام التعليقات\n"
            "/support - الدعم الفني"
        )

async def start_comment_system(update: Update, context: CallbackContext):
    """بدء نظام التعليقات - النسخة المعدلة"""
    user_id = update.effective_user.id
    
    # التحقق من تسجيل المستخدم
    if not await check_user_registration(user_id):
        await update.message.reply_text(
            "❌ **يجب أن تكون مسجلاً في النظام أولاً**\n\n"
            "استخدم /start لتسجيل حساب جديد"
        )
        return
    
    # الحصول على المهام النشطة
    active_tasks = comment_system.get_active_tasks()
    
    if not active_tasks:
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="comment_back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📭 **لا توجد مهام تعليقات نشطة حالياً**\n\n"
            "⏳ سيتم إضافة مهام جديدة قريباً\n"
            "🔔 سيتم إعلامك عند توفر مهام جديدة",
            reply_markup=reply_markup
        )
        return
    
    # عرض المهام المتاحة مع زر العودة
    keyboard = []
    for task in active_tasks:
        button_text = (
            f"{task['platform'].title()} - {task['reward_amount']} ريال - ({task['available_slots']} متبقي)"
        )
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"comment_task_{task['id']}")])
    
    keyboard.append([InlineKeyboardButton("📊 عرض تقدمي", callback_data="comment_progress")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="comment_back_to_main")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎯 **نظام مكافآت التعليقات**\n\n"
        "💡 **كيفية المشاركة:**\n"
        "1. اختر مهمة من القائمة\n"
        "2. ستتلقى كود تحقق فريد\n"
        "3. اكتب تعليقاً على المنشور وأضف الكود\n"
        "4. ارجع للبوت وأرسل نص التعليق للتحقق\n"
        "5. احصل على مكافأتك فوراً!\n\n"
        "🔗 **اختر المهمة التي تريد المشاركة فيها:**",
        reply_markup=reply_markup
    )

async def handle_comment_task_selection(update: Update, context: CallbackContext):
    """معالجة اختيار مهمة التعليق"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    task_id = int(query.data.replace("comment_task_", ""))
    
    # الحصول على معلومات المهمة
    active_tasks = comment_system.get_active_tasks()
    selected_task = next((task for task in active_tasks if task['id'] == task_id), None)
    
    if not selected_task:
        await query.edit_message_text("❌ هذه المهمة لم تعد متاحة")
        return
    
    # إنشاء مهمة تحقق للمستخدم
    result = comment_system.create_verification_task(user_id, {
        'task_id': task_id,
        'post_url': selected_task['post_url'],
        'platform': selected_task['platform'],
        'required_comment_template': selected_task['required_comment_template'],
        'reward_amount': selected_task['reward_amount']
    })
    
    if not result['success']:
        await query.edit_message_text(f"❌ {result['message']}")
        return
    
    unique_code = result['unique_code']
    
    # إعداد التعليمات حسب المنصة
    instructions = get_platform_instructions(selected_task['platform'], unique_code, selected_task['post_url'])
    
    message_text = (
        f"📝 **مهمة تعليق على {selected_task['platform'].title()}**\n\n"
        f"🎯 **الوصف:** {selected_task['description']}\n"
        f"💰 **المكافأة:** {selected_task['reward_amount']} ريال\n"
        f"👥 **المشاركون:** {selected_task['current_participants']+1}/{selected_task['max_participants'] or 'لا نهائي'}\n\n"
        f"🔑 **كود التحقق الفريد (مهم جداً):**\n"
        f"`{unique_code}`\n\n"
        f"{instructions}\n\n"
        f"⚠️ **تنبيه هام:**\n"
        f"• يجب نسخ الكود بدقة كما هو\n"
        f"• يجب أن يظهر الكود في تعليقك\n"
        f"• لا تحذف التعليق بعد التحقق\n\n"
        f"📨 **بعد الانتهاء من التعليق:**\n"
        f"ارجع هنا واضغط على '✅ تمت الكتابة' ثم أرسل نص التعليق"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ تمت الكتابة", callback_data=f"comment_done_{unique_code}")],
        [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="comment_back")]
    ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

def get_platform_instructions(platform: str, unique_code: str, post_url: str) -> str:
    """الحصول على تعليمات محددة لكل منصة"""
    base_instructions = f"**تعليمات {platform.title()}:**\n1. انتقل للمنشور: {post_url}\n2. اكتب تعليقاً يحتوي على: {unique_code}\n3. أضف رأيك الشخصي في المنتج\n4. احفظ التعليق"
    
    if platform == 'facebook':
        return f"📘 {base_instructions}"
    elif platform == 'instagram':
        return f"📸 {base_instructions}"
    elif platform == 'youtube':
        return f"📺 {base_instructions}"
    else:
        return f"🔗 {base_instructions}"

async def handle_comment_done(update: Update, context: CallbackContext):
    """معالجة الضغط على تمت الكتابة"""
    query = update.callback_query
    await query.answer()
    
    unique_code = query.data.replace("comment_done_", "")
    
    # حفظ حالة الانتظار
    context.user_data['awaiting_comment_text'] = True
    context.user_data['verification_code'] = unique_code
    
    await query.edit_message_text(
        "📨 **مرحلة التحقق**\n\n"
        "الآن قم بنسخ ولصص نص التعليق الذي كتبته **بالضبط**\n\n"
        "📝 **مثال:**\n"
        "\"هذا المنتج رائع! تجربتي كانت ممتازة CMT1A2B3C4\"\n\n"
        "🔍 **سيتم التحقق من:**\n"
        "• وجود كود التحقق في التعليق\n"
        "• مطابقة النص\n\n"
        "❌ **لا تقم بتغيير النص**\n"
        "⏳ **أرسل التعليق الآن:**"
    )

async def handle_comment_text_submission(update: Update, context: CallbackContext):
    """معالجة إرسال نص التعليق"""
    if not context.user_data.get('awaiting_comment_text'):
        return
    
    user_id = update.effective_user.id
    comment_text = update.message.text.strip()
    unique_code = context.user_data.get('verification_code')
    
    if not comment_text or not unique_code:
        await update.message.reply_text("❌ حدث خطأ، الرجاء المحاولة مرة أخرى")
        # مسح حالة الانتظار
        context.user_data['awaiting_comment_text'] = False
        context.user_data['verification_code'] = None
        return
    
    # التحقق من التعليق
    result = comment_system.verify_comment_submission(user_id, unique_code, comment_text)
    
    if result['success']:
        # نجاح التحقق
        reward_msg = f"💰 تم إضافة {result.get('reward_amount', 0)} ريال إلى رصيدك" if 'reward_amount' in result else ""
        
        success_message = (
            f"🎉 **تم التحقق بنجاح!**\n\n"
            f"✅ تم التحقق من تعليقك وتأكيد مشاركتك\n"
            f"{reward_msg}\n\n"
            f"📊 يمكنك متابعة تقدمك باستخدام /mycomments\n"
            f"💬 استخدم /comment للمشاركة في مهام أخرى\n\n"
            f"شكراً لمشاركتك وآرائك القيمة! 🌟"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 تقدمي", callback_data="comment_progress")],
            [InlineKeyboardButton("💬 مهام أخرى", callback_data="comment_back")]
        ]
        
        await update.message.reply_text(
            success_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    else:
        # فشل التحقق
        error_message = (
            f"❌ **{result['message']}**\n\n"
            f"🔍 **الأسباب المحتملة:**\n"
            f"• كود التحقق غير موجود في النص\n"
            f"• النص غير مطابق للتعليق\n"
            f"• انتهت صلاحية المهمة\n\n"
            f"💡 **الحلول:**\n"
            f"• تأكد من نسخ التعليق كاملاً\n"
            f"• تأكد من وجود الكود في التعليق\n"
            f"• جرب مرة أخرى\n\n"
            f"🔄 اضغط على الزر للمحاولة مرة أخرى:"
        )
        
        keyboard = [[InlineKeyboardButton("🔄 المحاولة مرة أخرى", callback_data=f"comment_done_{unique_code}")]]
        
        await update.message.reply_text(
            error_message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # مسح حالة الانتظار
    context.user_data['awaiting_comment_text'] = False
    context.user_data['verification_code'] = None

async def show_comment_progress(update: Update, context: CallbackContext):
    """عرض تقدم المستخدم في التعليقات - النسخة المعدلة"""
    user_id = update.effective_user.id
    
    progress = comment_system.get_user_progress(user_id)
    
    if not progress.get('success'):
        await update.message.reply_text("❌ حدث خطأ في جلب البيانات")
        return
    
    progress_message = (
        f"📊 **تقدمك في نظام التعليقات**\n\n"
        f"✅ **المهام المكتملة:** {progress['completed_tasks']}\n"
        f"⏳ **المهام قيد الانتظار:** {progress['pending_tasks']}\n"
        f"💰 **إجمالي المكافآت:** {progress['total_rewards']} ريال\n\n"
        f"🎯 **للمشاركة في مهام جديدة:**\n"
        f"استخدم /comments\n\n"
        f"💡 **نصائح:**\n"
        f"• شارك بآراء صادقة\n"
        f"• تأكد من إضافة كود التحقق\n"
        f"• لا تحذف التعليقات بعد التحقق"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="comment_back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(update, 'callback_query'):
        await update.callback_query.message.reply_text(progress_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(progress_message, reply_markup=reply_markup)

async def handle_comment_back(update: Update, context: CallbackContext):
    """العودة لقائمة المهام"""
    query = update.callback_query
    await query.answer()
    
    await start_comment_system(update, context)

async def handle_comment_back_to_main(update: Update, context: CallbackContext):
    """العودة للقائمة الرئيسية للتعليقات"""
    query = update.callback_query
    await query.answer()
    await comment_system_start(update, context)

# ==============================
# 🛠️ أوامر المسؤول لإدارة المهام
# ==============================

async def admin_add_comment_task(update: Update, context: CallbackContext):
    """إضافة مهمة تعليق جديدة"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_USER_ID:
        await update.message.reply_text("🚫 هذا الأمر للمسؤول فقط")
        return
    
    try:
        # تقسيم النص المدخل
        args = context.args
        
        if len(args) < 6:
            await update.message.reply_text(
                "📝 **استخدام الأمر:**\n\n"
                "/addcommenttask <المنصة> <الرابط> <الوصف> <المكافأة> <العدد_الأقصى> \"<نص التعليق المطلوب>\"\n\n"
                "📋 **مثال:**\n"
                '/addcommenttask facebook "https://facebook.com/post/123" "شارك برأيك في المنتج الجديد" 5.00 50 "برأيي هذا المنتج مميز بسبب جودته العالية"'
            )
            return
        
        platform = args[0]
        post_url = args[1]
        description = args[2]
        reward_amount = float(args[3])
        max_participants = int(args[4])
        required_comment = " ".join(args[5:])
        
        # حفظ المهمة في قاعدة البيانات
        conn = create_connection()
        if not conn:
            await update.message.reply_text("❌ فشل الاتصال بقاعدة البيانات")
            return
            
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO active_comment_tasks 
            (platform, post_url, description, required_comment_template, reward_amount, max_participants, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (platform, post_url, description, required_comment, reward_amount, max_participants, user_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        await update.message.reply_text(
            f"✅ **تم إضافة مهمة تعليق جديدة بنجاح!**\n\n"
            f"📱 **المنصة:** {platform}\n"
            f"📝 **الوصف:** {description}\n" 
            f"💰 **المكافأة:** {reward_amount} ريال\n"
            f"👥 **العدد الأقصى:** {max_participants}\n"
            f"🔗 **الرابط:** {post_url}\n"
            f"💬 **نص التعليق:** {required_comment}\n\n"
            f"🎯 يمكن للمستخدمين الآن المشاركة باستخدام /comment"
        )
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ **حدث خطأ في إضافة المهمة**\n\n"
            f"🔍 الخطأ: {str(e)}\n\n"
            f"💡 **تأكد من صيغة الأمر:**\n"
            '/addcommenttask facebook "الرابط" "الوصف" 5.00 100 "نص التعليق"'
        )

async def admin_comment_stats(update: Update, context: CallbackContext):
    """إحصائيات نظام التعليقات (للمسؤول)"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_USER_ID:
        await update.message.reply_text("🚫 هذا الأمر للمسؤول فقط")
        return
    
    try:
        conn = create_connection()
        if not conn:
            await update.message.reply_text("❌ فشل الاتصال بقاعدة البيانات")
            return
            
        cursor = conn.cursor()
        
        # إحصائيات عامة
        cursor.execute('''
            SELECT 
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status = 'verified' THEN 1 ELSE 0 END) as completed_tasks,
                COUNT(DISTINCT user_id) as unique_users,
                SUM(reward_amount) as total_rewards
            FROM comment_verification_tasks
        ''')
        
        stats = cursor.fetchone()
        
        # إحصائيات حسب المنصة
        cursor.execute('''
            SELECT platform, COUNT(*) as count 
            FROM comment_verification_tasks 
            WHERE status = 'verified' 
            GROUP BY platform
        ''')
        
        platform_stats = cursor.fetchall()
        
        # المهام النشطة
        cursor.execute('''
            SELECT COUNT(*) FROM active_comment_tasks WHERE status = 'active'
        ''')
        
        active_tasks = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        
        message = (
            "📊 **إحصائيات نظام التعليقات**\n\n"
            f"📈 إجمالي المهام: {stats[0]}\n"
            f"✅ المهام المكتملة: {stats[1]}\n"
            f"👥 المستخدمون الفريدون: {stats[2]}\n"
            f"💰 إجمالي المكافآت: {stats[3] or 0} ريال\n"
            f"🎯 المهام النشطة: {active_tasks}\n\n"
            "📱 **التوزيع حسب المنصة:**\n"
        )
        
        for platform, count in platform_stats:
            message += f"• {platform.title()}: {count} مهمة\n"
        
        await update.message.reply_text(message)
        
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")

def test_database_connection():
    """اختبار الاتصال بقاعدة البيانات"""
    print("🔍 اختبار الاتصال بقاعدة البيانات...")
    
    # التحقق من وجود متغير DATABASE_URL
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print("❌ لم يتم العثور على DATABASE_URL في متغيرات البيئة")
        return False
    
    print(f"✅ تم العثور على DATABASE_URL")
    print(f"📊 تفاصيل الاتصال: {db_url.split('@')[1] if '@' in db_url else 'مخفى'}")
    
    try:
        conn = create_connection()
        if conn:
            print("✅ الاتصال بقاعدة البيانات ناجح!")
            conn.close()
            return True
        else:
            print("❌ فشل الاتصال بقاعدة البيانات")
            return False
    except Exception as e:
        print(f"❌ خطأ في الاتصال: {e}")
        return False

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    
    print("🚀 بدء إعداد البوت المتكامل لمؤسسة الترويج الإعلامي...")

    # اختبر الاتصال أولاً
    if not test_database_connection():
        print("❌ لا يمكن تشغيل البوت بسبب مشكلة في قاعدة البيانات")
        return
        
    # التحقق من إعدادات قاعدة البيانات
    if not setup_database():
        print("❌ لا يمكن تشغيل البوت بسبب مشكلة في قاعدة البيانات")
        return

    # التحقق من توكن البوت
    if not BOT_TOKEN:
        print("❌ لم يتم تعيين BOT_TOKEN")
        return
    
    print("✅ تم التحقق من جميع الإعدادات بنجاح!")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إعداد نظام المحادثات الرئيسي
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REFERRAL_STAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_referral)],
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_country)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            BIRTH_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birth_year)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            SOCIAL_MEDIA_MENU: [CallbackQueryHandler(handle_social_media_menu)],
            FACEBOOK_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_facebook_url)],
            INSTAGRAM_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram_url)],
            YOUTUBE_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_youtube_url)],
            OTHER_SOCIAL_MEDIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_other_social_media)],
            PAYMENT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_payment_method)],
            WALLET_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_wallet_type)],
            NEW_WALLET_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_wallet_type)],
            WALLET_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_wallet_address)],
            TRANSFER_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_transfer_details)],
            TRANSFER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_transfer_details)],
            TRANSFER_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_transfer_details)],
            TRANSFER_COMPANY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_transfer_details)],
            
            # نظام التعديل
            CONFIRMATION: [CallbackQueryHandler(handle_confirmation)],
            EDIT_CHOICE: [CallbackQueryHandler(handle_edit_choice)],
            EDIT_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_full_name)],
            EDIT_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_country)],
            EDIT_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_gender)],
            EDIT_BIRTH_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_birth_year)],
            EDIT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_phone)],
            EDIT_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_email)],
            EDIT_PAYMENT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_payment_method)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('newstart', new_start)
        ]
    )
    
    application.add_handler(conv_handler)
    
    # إضافة الأوامر الإضافية
    application.add_handler(CommandHandler("profile", show_profile))
    application.add_handler(CommandHandler("invite", show_invite))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("newstart", new_start))
    application.add_handler(CommandHandler("stats", bot_stats))
    
    # ==============================
    # 💬 إضافة نظام التحقق من التعليقات
    # ==============================
    
    # إضافة معالجات نظام التعليقات
    application.add_handler(CommandHandler("comment", start_comment_system))
    application.add_handler(CommandHandler("mycomments", show_comment_progress))
    application.add_handler(CommandHandler("addcommenttask", admin_add_comment_task))
    application.add_handler(CommandHandler("commentstats", admin_comment_stats))

    application.add_handler(CallbackQueryHandler(handle_comment_task_selection, pattern="^comment_task_"))
    application.add_handler(CallbackQueryHandler(handle_comment_done, pattern="^comment_done_"))
    application.add_handler(CallbackQueryHandler(show_comment_progress, pattern="^comment_progress$"))
    application.add_handler(CallbackQueryHandler(handle_comment_back, pattern="^comment_back$"))

    # معالج النص الخاص بنظام التعليقات
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment_text_submission))

    application.add_handler(CommandHandler("comments", comment_system_start))
    application.add_handler(CallbackQueryHandler(handle_comment_main_menu, pattern="^(available_tasks|my_comment_progress|main_menu)$"))
    application.add_handler(CallbackQueryHandler(handle_comment_back_to_main, pattern="^comment_back_to_main$"))
   
    print("🤖 البوت المتكامل يعمل الآن...")
    print("🏢 مؤسسة الترويج الإعلامي")
    print("📍 يمكنك تجربته في تلغرام!")
    print("💡 الأوامر المتاحة:")
    print("   /start - بدء التسجيل المتكامل")
    print("   /newstart - بدء تسجيل جديد (حذف التقدم القديم)")
    print("   /profile - عرض الملف الشخصي")
    print("   /invite - عرض كود الدعوة والإحصائيات")
    print("   /stats - إحصائيات البوت (للمالك)")
    print("   /support - التواصل مع الدعم الفني")
    print("   /cancel - إلغاء التسجيل أثناء العملية")
    print("💬 **نظام التعليقات المضاف:**")
    print("   /comment - عرض المهام المتاحة")
    print("   /mycomments - عرض تقدمك في التعليقات")
    print("   /addcommenttask - إضافة مهمة جديدة (للمسؤول)")
    print("   /commentstats - إحصائيات النظام (للمسؤول)")
    print("📝 مميزات الأمان:")
    print("   • البوت يعمل فقط عبر روابط الدعوة")
    print("   • المالك والمسؤولين مسموح لهم مباشرة")
    print("   • جميع الأوامر مؤمنة")
    print("   • تسجيل كامل للنشاطات")
    print("🔧 المميزات المضافة:")
    print("   • دعم كامل ليوتيوب")
    print("   • نظام استئناف محسن بعد الانقطاع")
    print("   • معالجة أفضل للأخطاء")
    print("   • واجهة مستخدم محسنة")
     
    application.run_polling()

if __name__ == '__main__':
    main()
