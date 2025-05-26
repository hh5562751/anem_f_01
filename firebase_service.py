# firebase_service.py (User App - Updated to align with Admin Panel Logic - AppData Paths)
import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
import logging
import datetime # لاستخدامه مع الطوابع الزمنية في Firestore
import socket # لاسم الجهاز و IP المحلي
import platform # لنظام التشغيل
import getpass # لاسم المستخدم
import uuid # لإنشاء معرف فريد للجهاز إذا لم يكن موجودًا
import requests # لمحاولة الحصول على IP العام
import threading # For snapshot listener management
import time

# استيراد الثوابت من ملف config.py
from config import (
    FIREBASE_SERVICE_ACCOUNT_KEY_FILE, 
    # --- استخدام الثوابت المحدثة للمسارات ---
    ACTIVATION_STATUS_FILE, 
    DEVICE_ID_FILE, # تم استيراد هذا حديثًا
    FIRESTORE_ACTIVATION_CODES_COLLECTION
)
from utils import resource_path


logger = logging.getLogger(__name__)

class FirebaseService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(FirebaseService, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized_by_instance') and self._initialized_by_instance:
            return

        with self._lock:
            self.db = None
            self.app_initialized = False
            self._code_listeners = {}  # To store active listeners {code_id: listener_watch_object}
            self._listener_stop_events = {} # {code_id: threading.Event()}

            try:
                key_file_path = resource_path(FIREBASE_SERVICE_ACCOUNT_KEY_FILE)
                logger.info(f"FirebaseService (User): Attempting to initialize Firebase using key file: {key_file_path}")

                if not firebase_admin._apps:
                    if os.path.exists(key_file_path):
                        logger.info(f"FirebaseService (User): Key file '{FIREBASE_SERVICE_ACCOUNT_KEY_FILE}' exists at the resolved path: {key_file_path}.")
                        cred = credentials.Certificate(key_file_path)
                        firebase_admin.initialize_app(cred)
                        self.db = firestore.client()
                        self.app_initialized = True
                        logger.info("FirebaseService (User): Firebase Admin SDK initialized successfully.")
                    else:
                        logger.error(f"FirebaseService (User): Firebase service account key file '{FIREBASE_SERVICE_ACCOUNT_KEY_FILE}' (resolved path: {key_file_path}) not found. Firebase cannot be initialized.")
                else:
                    self.db = firestore.client()
                    self.app_initialized = True
                    logger.info("FirebaseService (User): Using pre-initialized Firebase Admin SDK app.")

                self._initialized_by_instance = True

            except Exception as e:
                logger.exception(f"FirebaseService (User): An error occurred during Firebase Admin SDK initialization: {e}")
                self._initialized_by_instance = False

    def is_initialized(self):
        return self.app_initialized and self.db is not None

    def _normalize_timestamp(self, timestamp_data):
        if isinstance(timestamp_data, datetime.datetime):
            if timestamp_data.tzinfo is None:
                return timestamp_data.replace(tzinfo=datetime.timezone.utc)
            return timestamp_data.astimezone(datetime.timezone.utc)
        elif hasattr(timestamp_data, 'to_datetime'): # Firestore Timestamp object
            dt_obj = timestamp_data.to_datetime()
            if dt_obj.tzinfo is None:
                return dt_obj.replace(tzinfo=datetime.timezone.utc)
            return dt_obj.astimezone(datetime.timezone.utc)
        return None

    def get_device_info(self):
        device_info = {}
        # --- استخدام DEVICE_ID_FILE من config.py ---
        local_device_id_file = DEVICE_ID_FILE 
        generated_id = None
        try:
            if os.path.exists(local_device_id_file):
                with open(local_device_id_file, 'r') as f:
                    generated_id = f.read().strip()
            if not generated_id or len(generated_id) < 10: # التحقق من أن المعرف ليس فارغًا أو قصيرًا جدًا
                generated_id = str(uuid.uuid4())
                # التأكد من أن المجلد موجود قبل الكتابة (يجب أن يكون موجودًا بواسطة config.py)
                os.makedirs(os.path.dirname(local_device_id_file), exist_ok=True)
                with open(local_device_id_file, 'w') as f:
                    f.write(generated_id)
                logger.info(f"FirebaseService (User): Generated and stored new device UUID: {generated_id} to {local_device_id_file}")
            else:
                logger.debug(f"FirebaseService (User): Loaded device UUID: {generated_id} from {local_device_id_file}")
            device_info["generated_device_id"] = generated_id
        except Exception as e:
            logger.error(f"FirebaseService (User): Error getting or creating device UUID at {local_device_id_file}: {e}")
            # كحل بديل، قم بإنشاء معرف مؤقت في الذاكرة فقط إذا فشلت الكتابة/القراءة
            device_info["generated_device_id"] = str(uuid.uuid4()) + "-inmemory"


        try: device_info["system_username"] = getpass.getuser()
        except Exception: device_info["system_username"] = "N/A"
        try: device_info["hostname"] = socket.gethostname()
        except Exception: device_info["hostname"] = "N/A"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5) # تقليل المهلة
            s.connect(("8.8.8.8", 80)) # استخدام DNS جوجل للتحقق من الاتصال
            device_info["local_ip"] = s.getsockname()[0]
            s.close()
        except Exception: device_info["local_ip"] = "N/A" # قد لا يكون متاحًا دائمًا
        try:
            device_info["os_platform"] = platform.system()
            device_info["os_version"] = platform.version()
            device_info["os_release"] = platform.release()
            device_info["architecture"] = platform.machine()
        except Exception: device_info["os_platform"] = "N/A"

        public_ip = "N/A"
        ip_services = ["https://api.ipify.org", "https://icanhazip.com", "https://ipinfo.io/ip"]
        for service_url in ip_services:
            try:
                response = requests.get(service_url, timeout=2) # مهلة قصيرة
                response.raise_for_status()
                public_ip = response.text.strip()
                if public_ip and not public_ip.startswith("Error_"): break # الخروج عند أول نجاح
            except requests.exceptions.RequestException:
                public_ip = f"Error_{service_url.split('//')[1].split('/')[0]}" # تسجيل الخدمة التي فشلت
        device_info["public_ip"] = public_ip

        logger.debug(f"FirebaseService (User): Collected device info: {device_info}")
        return device_info

    def check_local_activation(self):
        """
        Checks for local activation status.
        Returns: (is_activated_locally, code_id, device_id_used_for_activation, local_data)
        """
        # --- استخدام ACTIVATION_STATUS_FILE من config.py ---
        if os.path.exists(ACTIVATION_STATUS_FILE):
            try:
                with open(ACTIVATION_STATUS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("is_activated") and data.get("activation_code") and data.get("activated_by_device_id"):
                        actual_expires_at_iso = data.get("actualExpiresAt_iso")
                        if actual_expires_at_iso:
                            try:
                                actual_expires_at_dt = datetime.datetime.fromisoformat(actual_expires_at_iso)
                                if actual_expires_at_dt.tzinfo is None:
                                     actual_expires_at_dt = actual_expires_at_dt.replace(tzinfo=datetime.timezone.utc)
                                if actual_expires_at_dt < datetime.datetime.now(datetime.timezone.utc):
                                    logger.warning(f"FirebaseService (User): Local activation for code '{data.get('activation_code')}' has expired based on local data at {ACTIVATION_STATUS_FILE}.")
                                    return False, data.get("activation_code"), data.get("activated_by_device_id"), data
                            except ValueError:
                                logger.error(f"FirebaseService (User): Could not parse local actualExpiresAt_iso: {actual_expires_at_iso} from {ACTIVATION_STATUS_FILE}")

                        logger.info(f"FirebaseService (User): Found valid local activation status for code: {data.get('activation_code')} on device: {data.get('activated_by_device_id')} from {ACTIVATION_STATUS_FILE}")
                        return True, data.get("activation_code"), data.get("activated_by_device_id"), data
            except Exception as e:
                logger.exception(f"FirebaseService (User): Unexpected error reading local activation status file {ACTIVATION_STATUS_FILE}: {e}")
        logger.info(f"FirebaseService (User): No valid local activation status found at {ACTIVATION_STATUS_FILE}.")
        return False, None, None, None

    def save_local_activation(self, activation_code, device_id_for_activation, code_data_from_firebase):
        """Saves activation status locally, including actualExpiresAt."""
        data_to_save = {
            "is_activated": True,
            "activation_code": activation_code,
            "activated_by_device_id": device_id_for_activation,
            "activated_at_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "device_info_at_activation": self.get_device_info(),
            "actualExpiresAt_iso": None,
            "validityDuration_from_server": code_data_from_firebase.get("validityDuration"),
            "deviceLimit_from_server": code_data_from_firebase.get("deviceLimit")
        }
        actual_expires_at = code_data_from_firebase.get("actualExpiresAt")
        if actual_expires_at and isinstance(actual_expires_at, datetime.datetime):
            data_to_save["actualExpiresAt_iso"] = actual_expires_at.isoformat()

        try:
            # --- استخدام ACTIVATION_STATUS_FILE من config.py ---
            # التأكد من أن المجلد موجود قبل الكتابة
            os.makedirs(os.path.dirname(ACTIVATION_STATUS_FILE), exist_ok=True)
            with open(ACTIVATION_STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            logger.info(f"FirebaseService (User): Local activation status saved for code: {activation_code} to {ACTIVATION_STATUS_FILE}")
        except Exception as e:
            logger.exception(f"FirebaseService (User): Error saving local activation status file {ACTIVATION_STATUS_FILE}: {e}")

    def _calculate_actual_expires_at(self, activation_time_utc, validity_duration_dict):
        """Calculates the actual expiry time based on activation time and duration."""
        if not activation_time_utc or not validity_duration_dict:
            return None
        if not isinstance(activation_time_utc, datetime.datetime):
            logger.error(f"FirebaseService (User): _calculate_actual_expires_at - activation_time_utc is not datetime: {activation_time_utc}")
            return None
        if activation_time_utc.tzinfo is None:
            activation_time_utc = activation_time_utc.replace(tzinfo=datetime.timezone.utc)

        unit = validity_duration_dict.get("unit")
        value = validity_duration_dict.get("value")

        if unit == "none" or value is None:
            return None

        delta = None
        if unit == "days":
            delta = datetime.timedelta(days=int(value))
            if "value_hours" in validity_duration_dict: delta += datetime.timedelta(hours=int(validity_duration_dict["value_hours"]))
            if "value_minutes" in validity_duration_dict: delta += datetime.timedelta(minutes=int(validity_duration_dict["value_minutes"]))
        elif unit == "hours":
            delta = datetime.timedelta(hours=int(value))
            if "value_minutes" in validity_duration_dict: delta += datetime.timedelta(minutes=int(validity_duration_dict["value_minutes"]))
        elif unit == "minutes":
            delta = datetime.timedelta(minutes=int(value))
        else:
            logger.warning(f"FirebaseService (User): Unknown validity duration unit: {unit}")
            return None

        return activation_time_utc + delta

    def get_activation_code_details(self, code_id):
        """Fetches and normalizes activation code details from Firestore."""
        if not self.is_initialized():
            return None, "خدمة Firebase غير مهيأة."
        if not code_id or not code_id.strip():
            return None, "كود التفعيل فارغ."

        try:
            logger.debug(f"FirebaseService (User): Fetching details for code '{code_id}'")
            code_ref = self.db.collection(FIRESTORE_ACTIVATION_CODES_COLLECTION).document(code_id.strip())
            code_doc = code_ref.get()

            if code_doc.exists:
                code_data = code_doc.to_dict()
                code_data['id'] = code_doc.id
                for ts_field in ['createdAt', 'activatedAt', 'actualExpiresAt', 'lastUsedAt', 'revokedAt']:
                    if ts_field in code_data and code_data[ts_field] is not None:
                        code_data[ts_field] = self._normalize_timestamp(code_data[ts_field])

                code_data.setdefault('deviceLimit', 1)
                code_data.setdefault('activatedDevices', [])
                code_data.setdefault('validityDuration', {"unit": "none", "value": None})

                logger.info(f"FirebaseService (User): Details fetched for code '{code_id}'.")
                return code_data, None
            else:
                logger.warning(f"FirebaseService (User): Code '{code_id}' not found.")
                return None, "كود التفعيل غير موجود."
        except Exception as e:
            logger.exception(f"FirebaseService (User): Error fetching code '{code_id}': {e}")
            return None, f"خطأ في الاتصال بالخادم: {e}"

    def activate_code_on_current_device(self, code_to_activate):
        """
        Attempts to activate the given code on the current device.
        Handles 'UNUSED' and 'ACTIVE' (for multi-device) states.
        Returns: (success, message, updated_code_data_from_server)
        """
        if not self.is_initialized():
            return False, "خدمة Firebase غير مهيأة. لا يمكن تفعيل الكود.", None
        if not code_to_activate or not code_to_activate.strip():
            return False, "كود التفعيل فارغ أو غير صالح.", None

        current_device_full_info = self.get_device_info()
        current_device_id = current_device_full_info.get("generated_device_id")
        if not current_device_id or "-inmemory" in current_device_id: # التحقق إذا كان المعرف مؤقتًا
            logger.error("FirebaseService (User): Failed to get persistent current device ID for activation.")
            return False, "فشل في تحديد هوية الجهاز الحالي بشكل دائم. لا يمكن التفعيل.", None

        try:
            code_ref = self.db.collection(FIRESTORE_ACTIVATION_CODES_COLLECTION).document(code_to_activate.strip())
            code_doc = code_ref.get()

            if not code_doc.exists:
                logger.warning(f"FirebaseService (User): Activation attempt for non-existent code '{code_to_activate}'.")
                return False, "كود التفعيل غير صحيح أو غير موجود.", None

            code_data = code_doc.to_dict()
            code_data['id'] = code_doc.id
            for ts_field in ['createdAt', 'activatedAt', 'actualExpiresAt', 'lastUsedAt', 'revokedAt']:
                if ts_field in code_data and code_data[ts_field] is not None:
                    code_data[ts_field] = self._normalize_timestamp(code_data[ts_field])

            code_data.setdefault('deviceLimit', 1)
            code_data.setdefault('activatedDevices', [])
            code_data.setdefault('validityDuration', {"unit": "none", "value": None})

            status = code_data.get("status", "UNKNOWN").upper()
            device_limit = code_data.get("deviceLimit", 1)
            activated_devices_list = code_data.get("activatedDevices", [])

            if status == "REVOKED":
                logger.warning(f"FirebaseService (User): Code '{code_to_activate}' is REVOKED.")
                return False, "هذا الكود تم إلغاؤه من قبل المسؤول.", code_data

            if status == "EXPIRED":
                logger.warning(f"FirebaseService (User): Code '{code_to_activate}' is EXPIRED.")
                return False, "صلاحية هذا الكود قد انتهت.", code_data

            for device_entry in activated_devices_list:
                if isinstance(device_entry, dict) and device_entry.get("generated_device_id") == current_device_id:
                    logger.info(f"FirebaseService (User): Device '{current_device_id}' is already activated with code '{code_to_activate}'.")
                    self.save_local_activation(code_to_activate, current_device_id, code_data)
                    return True, "تم تفعيل هذا الجهاز بهذا الكود مسبقًا.", code_data

            update_payload = {}
            now_utc = datetime.datetime.now(datetime.timezone.utc)

            if status == "UNUSED":
                if len(activated_devices_list) >= device_limit:
                    logger.warning(f"FirebaseService (User): Code '{code_to_activate}' is UNUSED but device limit ({device_limit}) reached. This state should ideally not happen if admin panel manages limits correctly.")
                    return False, "تم الوصول للحد الأقصى للأجهزة لهذا الكود (حالة غير متوقعة).", code_data

                update_payload["status"] = "ACTIVE"
                update_payload["activatedAt"] = now_utc

                calculated_expiry = self._calculate_actual_expires_at(now_utc, code_data.get("validityDuration"))
                if calculated_expiry:
                    update_payload["actualExpiresAt"] = calculated_expiry
                else:
                    update_payload["actualExpiresAt"] = None # Explicitly set to None if no duration

                new_device_entry = {
                    "generated_device_id": current_device_id,
                    "activationTimestamp": now_utc,
                    **current_device_full_info
                }
                update_payload["activatedDevices"] = firestore.ArrayUnion([new_device_entry])
                update_payload["lastUsedAt"] = now_utc

            elif status == "ACTIVE":
                if len(activated_devices_list) >= device_limit:
                    logger.warning(f"FirebaseService (User): Code '{code_to_activate}' is ACTIVE but device limit ({device_limit}) already reached for new device '{current_device_id}'.")
                    return False, "تم الوصول للحد الأقصى لعدد الأجهزة المسموح بها لهذا الكود.", code_data

                new_device_entry = {
                    "generated_device_id": current_device_id,
                    "activationTimestamp": now_utc,
                     **current_device_full_info
                }
                update_payload["activatedDevices"] = firestore.ArrayUnion([new_device_entry])
                update_payload["lastUsedAt"] = now_utc # تحديث آخر استخدام أيضًا عند إضافة جهاز جديد لكود نشط

            else:
                logger.warning(f"FirebaseService (User): Code '{code_to_activate}' has an unhandled status: {status}.")
                return False, f"حالة الكود غير صالحة للتفعيل: {status}.", code_data

            if not update_payload:
                 logger.info(f"FirebaseService (User): No update payload generated for code '{code_to_activate}' with status '{status}'. This might be an issue.")
                 return False, "لم يتمكن البرنامج من تحديد إجراء التفعيل. يرجى المحاولة مرة أخرى.", code_data

            code_ref.update(update_payload)
            logger.info(f"FirebaseService (User): Successfully updated code '{code_to_activate}' in Firestore. Payload: {update_payload}")

            updated_doc = code_ref.get() # إعادة جلب البيانات المحدثة
            if updated_doc.exists:
                final_code_data = updated_doc.to_dict()
                final_code_data['id'] = updated_doc.id
                for ts_field_upd in ['createdAt', 'activatedAt', 'actualExpiresAt', 'lastUsedAt', 'revokedAt']:
                    if ts_field_upd in final_code_data and final_code_data[ts_field_upd] is not None:
                        final_code_data[ts_field_upd] = self._normalize_timestamp(final_code_data[ts_field_upd])

                if 'activatedDevices' not in final_code_data or not isinstance(final_code_data['activatedDevices'], list):
                    final_code_data['activatedDevices'] = [] # ضمان وجود القائمة

                self.save_local_activation(code_to_activate, current_device_id, final_code_data)
                return True, "تم تفعيل البرنامج بنجاح!", final_code_data
            else:
                logger.error(f"FirebaseService (User): Code '{code_to_activate}' disappeared after update attempt.")
                return False, "خطأ غير متوقع بعد محاولة التفعيل. الكود لم يعد موجودًا.", None

        except firebase_admin.exceptions.FirebaseError as fe:
            logger.exception(f"FirebaseService (User): Firebase error during activation of '{code_to_activate}': {fe}")
            return False, f"خطأ في قاعدة بيانات Firebase أثناء التفعيل: {fe}", None
        except Exception as e:
            logger.exception(f"FirebaseService (User): General error during activation of '{code_to_activate}': {e}")
            return False, f"خطأ عام أثناء محاولة التفعيل: {e}", None

    def verify_online_status_and_device(self, local_code_id, local_device_id):
        """
        Verifies the locally activated code against Firestore.
        Checks status, expiry, and if the current device is still authorized.
        Returns: (is_still_valid, message, code_data_from_server_or_local_if_offline)
        """
        if not self.is_initialized():
            logger.warning("FirebaseService (User): Firebase not initialized. Cannot verify online status. Relying on local data if any.")
            is_local, _, _, local_data = self.check_local_activation()
            if is_local and local_data and local_data.get("activation_code") == local_code_id and local_data.get("activated_by_device_id") == local_device_id:
                actual_expires_at_iso = local_data.get("actualExpiresAt_iso")
                if actual_expires_at_iso:
                    try:
                        actual_expires_at_dt = datetime.datetime.fromisoformat(actual_expires_at_iso)
                        if actual_expires_at_dt.tzinfo is None: actual_expires_at_dt = actual_expires_at_dt.replace(tzinfo=datetime.timezone.utc)
                        if actual_expires_at_dt < datetime.datetime.now(datetime.timezone.utc):
                            return False, "الاشتراك منتهي الصلاحية (وفقًا للبيانات المحلية).", local_data
                    except ValueError: pass # تجاهل إذا كان التنسيق خاطئًا
                return True, "تم التحقق محليًا (لا يوجد اتصال بالخادم).", local_data
            return False, "لا يوجد اتصال بالخادم ولا توجد بيانات تفعيل محلية صالحة.", None

        code_data, error_msg = self.get_activation_code_details(local_code_id)

        if error_msg or not code_data:
            logger.error(f"FirebaseService (User): Error fetching code '{local_code_id}' for online verification: {error_msg}")
            return False, f"فشل التحقق من حالة الاشتراك عبر الإنترنت: {error_msg}", None

        status = code_data.get("status", "UNKNOWN").upper()
        actual_expires_at = code_data.get("actualExpiresAt") # هذا سيكون datetime.datetime object or None

        if status == "REVOKED":
            return False, "تم إلغاء هذا الاشتراك من قبل المسؤول.", code_data
        if status == "EXPIRED":
            return False, "هذا الاشتراك قد انتهت صلاحيته.", code_data
        if status != "ACTIVE":
            return False, f"حالة الاشتراك لم تعد نشطة ({status}).", code_data

        if actual_expires_at and actual_expires_at < datetime.datetime.now(datetime.timezone.utc):
            logger.warning(f"FirebaseService (User): Code '{local_code_id}' has expired online at {actual_expires_at}.")
            # قد تحتاج لتحديث الحالة في Firestore إلى EXPIRED هنا إذا لم يتم ذلك تلقائيًا
            return False, "الاشتراك منتهي الصلاحية (وفقًا للخادم).", code_data

        activated_devices_list = code_data.get("activatedDevices", [])
        device_found_in_list = False
        for device_entry in activated_devices_list:
            if isinstance(device_entry, dict) and device_entry.get("generated_device_id") == local_device_id:
                device_found_in_list = True
                break

        if not device_found_in_list:
            logger.warning(f"FirebaseService (User): Device '{local_device_id}' no longer in activated list for code '{local_code_id}'.")
            return False, "لم يعد هذا الجهاز مصرحًا له باستخدام هذا الكود.", code_data

        logger.info(f"FirebaseService (User): Online verification successful for code '{local_code_id}' on device '{local_device_id}'.")
        self.save_local_activation(local_code_id, local_device_id, code_data) # تحديث البيانات المحلية بأحدث بيانات من الخادم
        return True, "الاشتراك صالح ونشط.", code_data

    def _on_code_snapshot(self, doc_snapshot_list, changes, read_time, code_id, user_callback, stop_event):
        if stop_event.is_set():
            logger.info(f"FirebaseService (User): Stop event set for listener on code '{code_id}'. Not processing snapshot.")
            if code_id in self._code_listeners and self._code_listeners[code_id]:
                try:
                    self._code_listeners[code_id].unsubscribe() # إيقاف المستمع
                    del self._code_listeners[code_id]
                except Exception: pass # تجاهل الأخطاء عند إلغاء الاشتراك
            return

        logger.debug(f"FirebaseService (User): Snapshot received for code '{code_id}'. Changes: {len(changes)}")

        if doc_snapshot_list and len(doc_snapshot_list) > 0:
            doc_snapshot = doc_snapshot_list[0] # عادة ما يكون هناك مستند واحد فقط عند الاستماع إلى مستند محدد
            if doc_snapshot.exists:
                code_data = doc_snapshot.to_dict()
                code_data['id'] = doc_snapshot.id # إضافة معرف المستند
                # تطبيع الطوابع الزمنية
                for ts_field in ['createdAt', 'activatedAt', 'actualExpiresAt', 'lastUsedAt', 'revokedAt']:
                    if ts_field in code_data and code_data[ts_field] is not None:
                        code_data[ts_field] = self._normalize_timestamp(code_data[ts_field])
                # ضمان وجود الحقول الافتراضية
                code_data.setdefault('deviceLimit', 1)
                code_data.setdefault('activatedDevices', [])
                code_data.setdefault('validityDuration', {"unit": "none", "value": None})

                if user_callback:
                    try: user_callback(code_data, None)
                    except Exception as e: logger.exception(f"FirebaseService (User): Error in user_callback for '{code_id}': {e}")
            else:
                logger.warning(f"FirebaseService (User): Code '{code_id}' document no longer exists (deleted).")
                if user_callback: user_callback(None, "DocumentDeleted") # إرسال إشعار بأن المستند حُذف
        else:
            # هذا السيناريو غير متوقع عند الاستماع إلى مستند واحد
            logger.warning(f"FirebaseService (User): Unexpected empty snapshot list for code '{code_id}'.")
            if user_callback: user_callback(None, "SnapshotError_EmptyList")


    def listen_to_activation_code_changes(self, code_id, callback_on_update):
        if not self.is_initialized():
            logger.error("FirebaseService (User): Firebase not initialized. Cannot start listener.")
            if callback_on_update: callback_on_update(None, "Firebase service not initialized.")
            return False

        if not code_id or not code_id.strip():
            logger.error("FirebaseService (User): Cannot listen to changes: code_id is empty.")
            if callback_on_update: callback_on_update(None, "Code ID is empty.")
            return False

        if code_id in self._code_listeners and self._code_listeners[code_id] is not None:
            logger.info(f"FirebaseService (User): Listener for code '{code_id}' already active. Stopping existing one.")
            self.stop_listening_to_code_changes(code_id) # إيقاف المستمع القديم أولاً

        try:
            doc_ref = self.db.collection(FIRESTORE_ACTIVATION_CODES_COLLECTION).document(code_id.strip())
            stop_event = threading.Event() # إنشاء حدث إيقاف جديد لكل مستمع
            self._listener_stop_events[code_id] = stop_event
            # استخدام lambda لتمرير stop_event إلى _on_code_snapshot
            internal_cb = lambda doc_sn_list, chgs, rt: self._on_code_snapshot(doc_sn_list, chgs, rt, code_id, callback_on_update, stop_event)
            watch_object = doc_ref.on_snapshot(internal_cb)
            self._code_listeners[code_id] = watch_object # تخزين كائن المراقبة
            logger.info(f"FirebaseService (User): Successfully started listening for updates on code '{code_id}'.")
            return True
        except Exception as e:
            logger.exception(f"FirebaseService (User): Error starting listener for code '{code_id}': {e}")
            if callback_on_update: callback_on_update(None, f"Error starting listener: {e}")
            return False

    def stop_listening_to_code_changes(self, code_id):
        if not code_id or not code_id.strip():
            logger.warning("FirebaseService (User): Cannot stop listener: code_id is empty.")
            return

        logger.info(f"FirebaseService (User): Attempting to stop listener for code '{code_id}'.")
        if code_id in self._listener_stop_events:
            self._listener_stop_events[code_id].set() # تعيين حدث الإيقاف

        watch_object = self._code_listeners.pop(code_id, None) # إزالة وإرجاع كائن المراقبة
        if watch_object:
            try:
                watch_object.unsubscribe() # إلغاء الاشتراك من التحديثات
                logger.info(f"FirebaseService (User): Successfully stopped listener for code '{code_id}'.")
            except Exception as e:
                logger.exception(f"FirebaseService (User): Error stopping listener for code '{code_id}': {e}")
        else:
            logger.info(f"FirebaseService (User): No active listener watch object found for code '{code_id}'.")
        
        self._listener_stop_events.pop(code_id, None) # إزالة حدث الإيقاف


if __name__ == '__main__':
    # هذا الجزء مخصص للاختبار فقط ولن يعمل بشكل صحيح بدون تهيئة PyQt Application
    # إذا كنت ترغب في اختبار هذا الملف بشكل منفصل، ستحتاج إلى محاكاة بيئة PyQt أو تشغيله ضمن تطبيق PyQt.
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - [%(threadName)s] - %(filename)s:%(lineno)d - %(message)s")
    
    # --- محاكاة مسارات config ---
    # في سياق الاختبار المستقل، قد تحتاج إلى تحديد هذه المسارات يدويًا
    # أو التأكد من أن config.py يمكنه تحديدها بشكل صحيح بدون بيئة PyQt كاملة.
    # DEVICE_ID_FILE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "AnemAppUserData", "device_id.dat")
    # ACTIVATION_STATUS_FILE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "AnemAppUserData", "activation_status.json")
    # os.makedirs(os.path.dirname(DEVICE_ID_FILE), exist_ok=True)


    fb_service = FirebaseService()

    if fb_service.is_initialized():
        print("FirebaseService (User): Firebase is initialized.")
        
        # --- Test get_device_info ---
        print("\n--- Testing get_device_info ---")
        dev_info = fb_service.get_device_info()
        print(f"Device Info: {dev_info}")
        if dev_info.get("generated_device_id"):
            print(f"  Device ID: {dev_info['generated_device_id']}")
        else:
            print("  Device ID could not be determined persistently.")


        # --- Test activate_code_on_current_device ---
        test_code_to_activate = "YOUR_UNUSED_CODE_HERE_FOR_TESTING" # استبدل هذا بكود حقيقي للاختبار

        if "YOUR_UNUSED_CODE_HERE" in test_code_to_activate: # تحقق إذا كان لا يزال placeholder
            print(f"\nSkipping activate_code_on_current_device test as placeholder code '{test_code_to_activate}' is used.")
        elif not dev_info.get("generated_device_id") or "-inmemory" in dev_info.get("generated_device_id"):
            print(f"\nSkipping activate_code_on_current_device test as persistent device ID could not be obtained.")
        else:
            print(f"\n--- Testing activate_code_on_current_device for code: {test_code_to_activate} ---")
            success, msg, data = fb_service.activate_code_on_current_device(test_code_to_activate)
            print(f"Activation attempt 1: Success={success}, Msg='{msg}'")
            if data:
                print(f"  Data: ID={data.get('id')}, Status={data.get('status')}, activatedAt={data.get('activatedAt')}, actualExpiresAt={data.get('actualExpiresAt')}")
                print(f"  Device Limit: {data.get('deviceLimit')}, Activated Devices: {len(data.get('activatedDevices', []))}")
                if data.get('activatedDevices'): print(f"  Device 1 ID: {data['activatedDevices'][0].get('generated_device_id')}")

            # يمكنك إضافة المزيد من سيناريوهات الاختبار هنا كما كان من قبل

        # --- Test listener ---
        listener_test_code_id = "YOUR_ACTIVE_CODE_FOR_LISTENER_TEST" # استبدل هذا بكود نشط للاختبار

        if "YOUR_ACTIVE_CODE_FOR_LISTENER" in listener_test_code_id:
            print("\nSkipping listener test as placeholder code is used.")
        else:
            print(f"\n--- Testing listener for code '{listener_test_code_id}' (will run for ~25 seconds) ---")

            def my_code_update_callback(cb_data, cb_error_msg):
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                if cb_error_msg:
                    print(f"LISTENER CB ({timestamp} - {listener_test_code_id}): Error: {cb_error_msg}")
                elif cb_data:
                    print(f"LISTENER CB ({timestamp} - {listener_test_code_id}): Data updated! Status: {cb_data.get('status')}, Expires: {cb_data.get('actualExpiresAt')}, Devices: {len(cb_data.get('activatedDevices',[]))}")
                else:
                    print(f"LISTENER CB ({timestamp} - {listener_test_code_id}): Received empty data but no error.")

            if fb_service.listen_to_activation_code_changes(listener_test_code_id, my_code_update_callback):
                print(f"Listener started for {listener_test_code_id}. Modify this code in Firebase Admin Panel to see updates.")
                try:
                    # ... (يمكنك إعادة إضافة منطق التعديل التلقائي من Firebase هنا إذا أردت) ...
                    time.sleep(25) # انتظر 25 ثانية
                except KeyboardInterrupt:
                    print("Interrupted by user.")
                finally:
                    print(f"\n--- Stopping listener for code '{listener_test_code_id}' ---")
                    fb_service.stop_listening_to_code_changes(listener_test_code_id)
                    print("Listener stopped.")
            else:
                print(f"Failed to start listener for {listener_test_code_id}")

        print("\n--- Test check_local_activation ---")
        is_local_act, local_c_id, local_d_id, local_act_data = fb_service.check_local_activation()
        print(f"Local activation check: IsLocal={is_local_act}, Code={local_c_id}, DeviceID={local_d_id}")
        if local_act_data:
            print(f"  Local Data: actualExpiresAt_iso={local_act_data.get('actualExpiresAt_iso')}")

        if is_local_act and local_c_id and local_d_id:
            print("\n--- Test verify_online_status_and_device (using local data if available) ---")
            is_still_ok, online_msg, online_data = fb_service.verify_online_status_and_device(local_c_id, local_d_id)
            print(f"Online verification: StillOK={is_still_ok}, Msg='{online_msg}'")
            if online_data:
                 print(f"  Online Data: Status={online_data.get('status')}, actualExpiresAt={online_data.get('actualExpiresAt')}, Devices: {len(online_data.get('activatedDevices',[]))}")

    else:
        print("FirebaseService (User): Firebase initialization failed. Check logs.")
