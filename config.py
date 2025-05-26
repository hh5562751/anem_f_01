# config.py
import requests
import logging
import os # تمت الإضافة
from PyQt5.QtCore import QStandardPaths # تمت الإضافة

# --- Application Specific Name for AppData folder ---
APP_NAME_FOR_DATA_DIR = "AnemAppUserData" # يمكنك تغيير هذا إذا أردت

def get_app_data_dir():
    """
    Returns the application-specific data directory.
    Creates it if it doesn't exist.
    """
    try:
        # QStandardPaths.AppLocalDataLocation هو الأنسب للبيانات التي لا يجب أن يتجول بها المستخدم
        # أو QStandardPaths.AppDataLocation إذا كنت تفضل ذلك (أكثر شيوعًا للتجوال)
        path = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        if not path: # في حالة عدم تمكن PyQt من تحديد المسار (نادر جدًا)
            # fallback to a directory next to the executable, but inside a hidden folder
            path = os.path.join(os.path.abspath("."), "." + APP_NAME_FOR_DATA_DIR.lower() + "_data")
            
        app_data_path = os.path.join(path, APP_NAME_FOR_DATA_DIR)
        
        if not os.path.exists(app_data_path):
            os.makedirs(app_data_path, exist_ok=True)
        return app_data_path
    except Exception as e:
        # Fallback in case of any error with QStandardPaths or directory creation
        fallback_path = os.path.join(os.path.abspath("."), "." + APP_NAME_FOR_DATA_DIR.lower() + "_data_fallback")
        try:
            if not os.path.exists(fallback_path):
                 os.makedirs(fallback_path, exist_ok=True)
            return fallback_path
        except Exception as fe:
            # Ultimate fallback: current directory (not ideal, but better than crashing)
            # Log this critical failure
            critical_fallback_logger = logging.getLogger(__name__ + ".config_critical_fallback")
            critical_fallback_logger.error(f"CRITICAL: Could not create any app data directory. Error with QStandardPaths: {e}, Error with fallback: {fe}. Using current directory.")
            return os.path.abspath(".")


APP_DATA_DIR = get_app_data_dir() # الحصول على المسار مرة واحدة

# --- File Names and Paths (Updated to use APP_DATA_DIR) ---
LOG_FILE = os.path.join(APP_DATA_DIR, "anem_app.log")
DATA_FILE = os.path.join(APP_DATA_DIR, "members_data.json")
SETTINGS_FILE = os.path.join(APP_DATA_DIR, "app_settings.json")
ACTIVATION_STATUS_FILE = os.path.join(APP_DATA_DIR, "activation_status.json")
DEVICE_ID_FILE = os.path.join(APP_DATA_DIR, "device_id.dat") # ملف جديد لـ device_id

# --- Temporary and Backup File Names (Updated to use APP_DATA_DIR) ---
DATA_FILE_TMP = DATA_FILE + ".tmp"
DATA_FILE_BAK = DATA_FILE + ".bak"
SETTINGS_FILE_TMP = SETTINGS_FILE + ".tmp"
SETTINGS_FILE_BAK = SETTINGS_FILE + ".bak"

# --- Resource Files (These should remain relative to the app or be handled by resource_path) ---
STYLESHEET_FILE = "styles_dark.txt" # يبقى كما هو، يُفترض أنه مورد
FIREBASE_SERVICE_ACCOUNT_KEY_FILE = "firebase_service_account_key.json" # يبقى كما هو، يُفترض أنه مورد

# --- API Configuration ---
BASE_API_URL = "https://ac-controle.anem.dz/AllocationChomage/api"
MAIN_SITE_CHECK_URL = "https://ac-controle.anem.dz/"

# --- Session Object (shared across API clients if needed) ---
SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ar-DZ,ar;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'Origin': 'https://minha.anem.dz',
    'Referer': 'https://minha.anem.dz/',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
})

# --- Settings Keys (used for consistency in accessing settings dict) ---
SETTING_MIN_MEMBER_DELAY = "min_member_delay"
SETTING_MAX_MEMBER_DELAY = "max_member_delay"
SETTING_MONITORING_INTERVAL = "monitoring_interval"
SETTING_BACKOFF_429 = "backoff_429"
SETTING_BACKOFF_GENERAL = "backoff_general"
SETTING_REQUEST_TIMEOUT = "request_timeout"

# --- Default Settings (if settings file is missing or corrupted) ---
DEFAULT_SETTINGS = {
    SETTING_MIN_MEMBER_DELAY: 30,
    SETTING_MAX_MEMBER_DELAY: 60,
    SETTING_MONITORING_INTERVAL: 1,
    SETTING_BACKOFF_429: 60,
    SETTING_BACKOFF_GENERAL: 5,
    SETTING_REQUEST_TIMEOUT: 30
}

# --- Retry Mechanism Constants (used by AnemAPIClient) ---
MAX_RETRIES = 3
MAX_BACKOFF_DELAY = 120

# --- Other Application Constants ---
MAX_ERROR_DISPLAY_LENGTH = 70
APP_ID_FALLBACK = 'anem-booking-app-pyqt14-refactored-v2' # تم تغيير الـ fallback قليلاً للتمييز

# --- Firebase Activation Constants ---
FIRESTORE_ACTIVATION_CODES_COLLECTION = "activation_codes"

try:
    APP_ID = __app_id
except NameError:
    config_logger = logging.getLogger(__name__ + ".config_fallback")
    config_logger.info("Global variable __app_id not found, using fallback APP_ID.")
    APP_ID = APP_ID_FALLBACK

# تسجيل مسار بيانات التطبيق المستخدم
startup_logger = logging.getLogger(__name__ + ".startup_paths")
startup_logger.info(f"Application Data Directory set to: {APP_DATA_DIR}")
startup_logger.info(f"Log file path: {LOG_FILE}")
startup_logger.info(f"Data file path: {DATA_FILE}")
startup_logger.info(f"Settings file path: {SETTINGS_FILE}")
