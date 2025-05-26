# logger_setup.py
import logging
import sys
from config import LOG_FILE # LOG_FILE يتم استيراده من config.py ويحتوي الآن على المسار الكامل

def setup_logging():
    """Configures and returns a logger instance."""
    # Configure the root logger
    # This setup will apply to all loggers obtained via logging.getLogger()
    # unless they are specifically configured otherwise.
    
    # التأكد من أن logging.basicConfig يتم استدعاؤه مرة واحدة فقط
    # إذا كان هناك أي معالجات (handlers) مضافة مسبقًا إلى root logger، قم بإزالتها
    # هذا يمنع تكرار الرسائل في السجل إذا تم استدعاء setup_logging عدة مرات (على الرغم من أنه لا ينبغي أن يحدث)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
        
    logging.basicConfig(
        level=logging.INFO, # Set the desired logging level (e.g., INFO, DEBUG)
        format="%(asctime)s - %(levelname)s - %(threadName)s - %(filename)s:%(lineno)d - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'), # Log to a file, ensuring UTF-8 encoding
            logging.StreamHandler(sys.stdout) # Also log to console (standard output)
        ]
    )
    # Get a logger instance (optional if basicConfig is sufficient for all modules)
    # If other modules use logging.getLogger(__name__), they will inherit this config.
    logger = logging.getLogger(__name__) 
    logger.info(f"Logging initialized. Log file: {LOG_FILE}") # إضافة رسالة لتأكيد مسار ملف السجل
    return logger

# Example of how this might be used in another file (e.g., main_app.py at the beginning):
# from logger_setup import setup_logging
# logger = setup_logging() # Call this once at the start of your application
# logger.info("Logging is configured.")
