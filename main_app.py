# main_app.py (User App - Enhanced Activation & Error Handling - Data Safety V2 - Activation Thread & UI Fixes V2 - AppData Paths Confirmed - Auto Check & AttributeError Fix)
import sys
import json
import os
import logging
import random
import time
import datetime # noqa
import shutil

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QStatusBar, QFrame, QAction, QStyle,
    QMenu, QLineEdit, QComboBox, QAbstractItemView, QDesktopWidget, QDialog
)
from PyQt5.QtCore import QTimer, Qt, QDateTime, QLocale, QStandardPaths, QUrl, pyqtSignal, QThread, QSize
from PyQt5.QtGui import QIcon, QColor, QPalette, QDesktopServices, QFontDatabase

from firebase_service import FirebaseService
from gui_components import (
    ToastNotification, AddMemberDialog, EditMemberDialog,
    SettingsDialog, ViewMemberDialog, ActivationDialog, SubscriptionDetailsDialog
)

from api_client import AnemAPIClient
from member import Member
from threads import FetchInitialInfoThread, MonitoringThread, SingleMemberCheckThread, DownloadAllPdfsThread
from config import (
    # الملفات التي تم نقلها إلى APP_DATA_DIR
    DATA_FILE,
    SETTINGS_FILE,
    # الملفات المؤقتة والاحتياطية المرتبطة بها
    DATA_FILE_TMP, DATA_FILE_BAK,
    SETTINGS_FILE_TMP, SETTINGS_FILE_BAK,
    # الثوابت الأخرى
    STYLESHEET_FILE, # يبقى كما هو (مورد)
    DEFAULT_SETTINGS, SETTING_MIN_MEMBER_DELAY, SETTING_MAX_MEMBER_DELAY,
    SETTING_MONITORING_INTERVAL, SETTING_BACKOFF_429, SETTING_BACKOFF_GENERAL,
    SETTING_REQUEST_TIMEOUT, MAX_ERROR_DISPLAY_LENGTH,
    FIREBASE_SERVICE_ACCOUNT_KEY_FILE, # يبقى كما هو (مورد)
    FIRESTORE_ACTIVATION_CODES_COLLECTION,
    ACTIVATION_STATUS_FILE, # هذا الآن من APP_DATA_DIR عبر config.py
    DEVICE_ID_FILE # هذا الآن من APP_DATA_DIR عبر config.py
)
from logger_setup import setup_logging # logger_setup سيستخدم LOG_FILE من config.py
from utils import QColorConstants, get_icon_name_for_status, resource_path

logger = setup_logging()


def load_custom_fonts():
    font_dir = resource_path("fonts")
    if not os.path.isdir(font_dir):
        logger.warning(f"مجلد الخطوط '{font_dir}' غير موجود. لن يتم تحميل الخطوط المخصصة.")
        return

    font_files = [
        "Tajawal-Regular.ttf", "Tajawal-Medium.ttf", "Tajawal-Bold.ttf",
        "Tajawal-ExtraBold.ttf", "Tajawal-Light.ttf",
        "Tajawal-ExtraLight.ttf", "Tajawal-Black.ttf"
    ]
    loaded_fonts_count = 0
    for font_file in font_files:
        font_path = os.path.join(font_dir, font_file)
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                loaded_fonts_count +=1
            else: logger.warning(f"فشل تحميل الخط: {font_file} من المسار: {font_path}")
        else: logger.warning(f"ملف الخط غير موجود: {font_path}")
    if loaded_fonts_count > 0: logger.info(f"تم تحميل {loaded_fonts_count} خطوط مخصصة بنجاح.")
    else: logger.warning("لم يتم تحميل أي خطوط مخصصة.")

class ActivationProcessingThread(QThread):
    activation_finished = pyqtSignal(bool, str, object)

    def __init__(self, firebase_service_instance, code_to_activate, parent=None):
        super().__init__(parent)
        self.firebase_service = firebase_service_instance
        self.code = code_to_activate
        self.is_running = True

    def run(self):
        if not self.is_running:
            return
        try:
            logger.info(f"ActivationProcessingThread: بدء معالجة الكود {self.code}")
            success, message, server_data = self.firebase_service.activate_code_on_current_device(self.code)
            if self.is_running:
                self.activation_finished.emit(success, message, server_data)
            logger.info(f"ActivationProcessingThread: انتهاء معالجة الكود {self.code}. النجاح: {success}")
        except Exception as e:
            logger.exception(f"ActivationProcessingThread: خطأ غير متوقع أثناء معالجة الكود {self.code}: {e}")
            if self.is_running:
                self.activation_finished.emit(False, f"خطأ غير متوقع في الخيط: {e}", None)

    def stop(self):
        self.is_running = False


class AnemApp(QMainWindow):
    COL_ICON, COL_FULL_NAME_AR, COL_NIN, COL_WASSIT, COL_CCP, COL_PHONE_NUMBER, COL_STATUS, COL_RDV_DATE, COL_DETAILS = range(9)
    subscription_updated_signal = pyqtSignal(object, str)

    def __init__(self):
        super().__init__()
        self._should_initialize_ui = False
        # تهيئة activation_successful مبكرًا لتجنب AttributeError
        self.activation_successful = False
        self.firebase_service = FirebaseService() # هذا سيستخدم DEVICE_ID_FILE و ACTIVATION_STATUS_FILE من config
        self.activated_code_id = None
        self.current_subscription_data = None
        self.current_device_id = self.firebase_service.get_device_info().get("generated_device_id")
        self.activation_dialog_open = False
        self.toast_notifications = []
        self.settings = {}
        self.activation_thread = None

        self._initialize_and_check_activation()
        if not self.activation_successful: # سيعتمد على القيمة المحدثة من _initialize_and_check_activation
            logger.critical("AnemApp __init__: فشل تفعيل البرنامج. لن يتم إكمال تهيئة واجهة المستخدم.")
            # لا حاجة لـ QTimer.singleShot هنا، سيتم الخروج من البرنامج إذا لم تنجح التهيئة
            return
        self._should_initialize_ui = True # إذا وصلنا إلى هنا، فالتفعيل ناجح

        load_custom_fonts()
        QApplication.setLayoutDirection(Qt.RightToLeft)
        self.setWindowTitle("برنامج إدارة مواعيد منحة البطالة")

        desktop = QApplication.desktop()
        available_geometry = desktop.availableGeometry(self)
        self.setGeometry(available_geometry)
        self.setWindowState(Qt.WindowMaximized)
        logger.info(f"تم تعيين النافذة الرئيسية لملء الشاشة المتاحة: {available_geometry.width()}x{available_geometry.height()}")

        self.load_app_settings() # ستستخدم SETTINGS_FILE من config

        self.suppress_initial_messages = True
        self.members_list = []
        self.filtered_members_list = []
        self.is_filter_active = False

        self.api_client = AnemAPIClient(
            initial_backoff_general=self.settings.get(SETTING_BACKOFF_GENERAL, DEFAULT_SETTINGS[SETTING_BACKOFF_GENERAL]),
            initial_backoff_429=self.settings.get(SETTING_BACKOFF_429, DEFAULT_SETTINGS[SETTING_BACKOFF_429]),
            request_timeout=self.settings.get(SETTING_REQUEST_TIMEOUT, DEFAULT_SETTINGS[SETTING_REQUEST_TIMEOUT])
        )

        self.initial_fetch_threads = []
        self.single_check_thread = None
        self.active_download_all_pdfs_threads = {}
        self.active_spinner_row_in_view = -1
        self.spinner_char_idx = 0
        self.spinner_chars = ['◐', '◓', '◑', '◒']
        self.row_spinner_timer = QTimer(self)
        self.row_spinner_timer.timeout.connect(self.update_active_row_spinner_display)
        self.row_spinner_timer_interval = 150

        self.monitoring_thread = MonitoringThread(self.members_list, self.settings.copy())
        self.monitoring_thread.update_member_gui_signal.connect(self.update_member_gui_in_table)
        self.monitoring_thread.new_data_fetched_signal.connect(self.update_member_name_in_table)
        self.monitoring_thread.global_log_signal.connect(self.update_status_bar_message)
        self.monitoring_thread.member_being_processed_signal.connect(self.handle_member_processing_signal)
        self.monitoring_thread.countdown_update_signal.connect(self.update_countdown_timer_display)

        self.subscription_updated_signal.connect(self._handle_subscription_update_from_signal)

        self.init_ui()
        self.load_stylesheet() # ستستخدم STYLESHEET_FILE من config (يُفترض أنه مورد)
        self.load_members_data() # ستستخدم DATA_FILE من config
        QTimer.singleShot(0, self.apply_app_settings)
        logger.info("AnemApp __init__: اكتملت التهيئة.")

    def close_app_due_to_error(self, message=""):
        logger.info(f"AnemApp: Closing application due to critical error. Message: {message}")
        if self.activation_thread and self.activation_thread.isRunning():
            self.activation_thread.stop()
            self.activation_thread.wait(1000)

        if message and not self.activation_dialog_open :
             QMessageBox.critical(self, "خطأ حاسم", message, QMessageBox.Ok)
        self.close() # سيؤدي إلى استدعاء closeEvent

    def _initialize_and_check_activation(self):
        # self.activation_successful تم تهيئته بالفعل في __init__
        # سيتم تحديث قيمته بواسطة _perform_activation_check_logic
        self.activation_successful = self._perform_activation_check_logic()
        if not self.activation_successful:
            # إذا فشل التفعيل، لا تقم بإظهار الواجهة الرئيسية
            # سيتم التعامل مع الخروج في __init__
            logger.info("AnemApp: _initialize_and_check_activation determined activation failed.")
            # لا حاجة لـ QTimer.singleShot هنا، لأن __init__ سيتحقق من self.activation_successful

    def _perform_activation_check_logic(self):
        logger.info("AnemApp: بدء التحقق من تفعيل البرنامج...")
        if not self.firebase_service.is_initialized(): # firebase_service يستخدم FIREBASE_SERVICE_ACCOUNT_KEY_FILE
            logger.critical(f"AnemApp: خدمة Firebase غير مهيأة. تأكد من وجود ملف '{FIREBASE_SERVICE_ACCOUNT_KEY_FILE}'.")
            if not hasattr(self, 'toast_notifications'): self.toast_notifications = []
            QMessageBox.critical(self, "خطأ فادح في الاتصال",
                                 f"لا يمكن تهيئة خدمة المصادقة.\nالرجاء التأكد من وجود ملف '{FIREBASE_SERVICE_ACCOUNT_KEY_FILE}' وأنه صالح, ومن وجود اتصال بالإنترنت.\nسيتم إغلاق البرنامج.",
                                 QMessageBox.Ok)
            return False

        # firebase_service.check_local_activation() ستستخدم ACTIVATION_STATUS_FILE من config
        is_locally_activated, local_code, local_device_id, local_data = self.firebase_service.check_local_activation()

        if is_locally_activated and local_code and local_device_id:
            logger.info(f"AnemApp: البرنامج مفعل محليًا بالكود: {local_code} للجهاز: {local_device_id}. يتم التحقق من الصلاحية عبر الإنترنت...")

            # firebase_service.verify_online_status_and_device() ستستخدم ACTIVATION_STATUS_FILE
            is_still_valid_online, online_message, server_code_data = self.firebase_service.verify_online_status_and_device(local_code, local_device_id)

            if is_still_valid_online and server_code_data:
                logger.info(f"AnemApp: الكود المحلي '{local_code}' صالح وحالته '{server_code_data.get('status', 'UNKNOWN')}' في Firebase.")
                self.current_subscription_data = server_code_data
                self.activated_code_id = local_code
                self.firebase_service.listen_to_activation_code_changes(self.activated_code_id, self._pass_subscription_update_to_signal)
                return True # التفعيل ناجح
            else:
                user_facing_message = "فشل التحقق من التفعيل المحلي عبر الإنترنت. قد يكون الاشتراك قد انتهى أو تم إلغاؤه."
                if "لم يعد هذا الجهاز مصرحًا له" in online_message:
                    user_facing_message = "لم يعد هذا الجهاز مصرحًا له باستخدام هذا الكود."
                elif "تم إلغاء هذا الاشتراك" in online_message:
                     user_facing_message = "تم إلغاء هذا الاشتراك من قبل المسؤول."
                elif "الاشتراك منتهي الصلاحية" in online_message or "قد انتهت صلاحيته" in online_message:
                    user_facing_message = "صلاحية اشتراكك الحالي قد انتهت."

                logger.warning(f"AnemApp: الكود المحلي '{local_code}' لم يعد صالحًا عبر الإنترنت: {online_message}.")
                self._clear_local_activation_and_state(f"الكود المحلي ({local_code}) لم يعد صالحًا: {online_message}")
                return self._show_activation_dialog_loop(initial_message=user_facing_message, initial_is_error=True)

        logger.info("AnemApp: البرنامج غير مفعل محليًا أو التحقق المحلي فشل. يتطلب التفعيل عبر الإنترنت.")
        return self._show_activation_dialog_loop()

    def _clear_local_activation_and_state(self, reason=""):
        logger.info(f"AnemApp: مسح بيانات التفعيل المحلية. السبب: {reason}")
        # ACTIVATION_STATUS_FILE يتم استيراده من config ويشير للمسار الصحيح
        if os.path.exists(ACTIVATION_STATUS_FILE):
            try:
                os.remove(ACTIVATION_STATUS_FILE)
                logger.info(f"AnemApp: تم حذف ملف التفعيل المحلي: {ACTIVATION_STATUS_FILE}")
            except Exception as e_remove:
                logger.error(f"AnemApp: خطأ أثناء حذف ملف التفعيل المحلي {ACTIVATION_STATUS_FILE}: {e_remove}")
        self.current_subscription_data = None
        if self.activated_code_id and self.firebase_service.is_initialized():
            self.firebase_service.stop_listening_to_code_changes(self.activated_code_id)
        self.activated_code_id = None

    def _process_activation_result(self, success, message_from_service, server_code_data, dialog_instance):
        logger.info(f"AnemApp: Activation thread finished. Success: {success}, Msg: '{message_from_service}'")
        if not dialog_instance or not hasattr(dialog_instance, 'isVisible') or not dialog_instance.isVisible():
            logger.warning("AnemApp: _process_activation_result called but dialog_instance is None or not visible.")
            return False

        dialog_instance.show_status_message("", is_waiting=False)

        if success and server_code_data:
            self.current_subscription_data = server_code_data
            self.activated_code_id = server_code_data.get("id", dialog_instance.get_activation_code())

            dialog_instance.show_status_message(message_from_service or "تم تفعيل البرنامج بنجاح!", is_success=True)
            QMessageBox.information(dialog_instance, "نجاح التفعيل", message_from_service or "تم تفعيل البرنامج بنجاح!")

            self.firebase_service.listen_to_activation_code_changes(self.activated_code_id, self._pass_subscription_update_to_signal)
            dialog_instance.accept()
            return True # يشير إلى أن التفعيل كان ناجحًا
        else:
            if server_code_data: self.current_subscription_data = server_code_data
            user_friendly_error = "فشل تفعيل الكود. يرجى المحاولة مرة أخرى."
            if message_from_service:
                if "غير صحيح أو غير موجود" in message_from_service: user_friendly_error = "الكود الذي أدخلته غير صحيح أو غير موجود."
                elif "صلاحية هذا الكود قد انتهت" in message_from_service: user_friendly_error = "عذرًا، صلاحية الكود الذي أدخلته قد انتهت."
                elif "تم إلغاؤه من قبل المسؤول" in message_from_service: user_friendly_error = "تم إلغاء صلاحية هذا الكود."
                elif "تم الوصول للحد الأقصى لعدد الأجهزة" in message_from_service: user_friendly_error = "تم استخدام هذا الكود على الحد الأقصى من الأجهزة."
                elif "فشل الاتصال" in message_from_service or "خدمة Firebase غير مهيأة" in message_from_service or "خطأ غير متوقع في الخيط" in message_from_service:
                     user_friendly_error = "فشل الاتصال بالخادم أو حدث خطأ أثناء التحقق. يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى."
                else: user_friendly_error = message_from_service

            dialog_instance.show_status_message(user_friendly_error, is_error=True)
            return False # يشير إلى أن التفعيل فشل


    def _show_activation_dialog_loop(self, initial_message=None, initial_is_error=False):
        if self.activation_dialog_open:
            logger.warning("AnemApp: Activation dialog is already open. Skipping new instance.")
            return self.activation_successful # إرجاع الحالة الحالية إذا كان الحوار مفتوحًا بالفعل

        self.activation_dialog_open = True
        activation_dialog = ActivationDialog(self)

        activation_processing_started_locally = False

        def handle_activation_attempt(code_from_dialog):
            nonlocal activation_processing_started_locally
            if activation_processing_started_locally:
                logger.warning("Activation attempt while another is in progress. Ignoring.")
                return

            if not code_from_dialog:
                activation_dialog.show_status_message("الرجاء إدخال كود التفعيل.", is_error=True)
                return

            if not self.firebase_service.is_initialized():
                activation_dialog.show_status_message("فشل الاتصال بخادم التفعيل. يرجى التحقق من اتصالك بالإنترنت.", is_error=True)
                return

            activation_processing_started_locally = True
            activation_dialog.show_status_message("جاري التحقق وتفعيل الكود...", is_waiting=True)

            if self.activation_thread and self.activation_thread.isRunning():
                self.activation_thread.stop()
                self.activation_thread.wait(500)

            self.activation_thread = ActivationProcessingThread(self.firebase_service, code_from_dialog, self)

            # استخدام lambda لتمرير dialog_instance بشكل صحيح
            self.activation_thread.activation_finished.connect(
                lambda success, msg, data, ad=activation_dialog: (
                    self._process_activation_result(success, msg, data, ad)
                )
            )

            def on_thread_actually_finished():
                nonlocal activation_processing_started_locally
                activation_processing_started_locally = False
                if hasattr(activation_dialog, 'isVisible') and activation_dialog.isVisible():
                    if activation_dialog.result() != QDialog.Accepted: # فقط إذا لم يتم قبول الحوار بالفعل
                         current_status_text = activation_dialog.status_message_area.toPlainText()
                         if "⏳" not in current_status_text: # لا تقم بتحديث الرسالة إذا كانت لا تزال "جاري الانتظار"
                            activation_dialog.show_status_message(current_status_text, is_waiting=False)


            self.activation_thread.finished.connect(on_thread_actually_finished)
            self.activation_thread.start()

        activation_dialog.activation_attempted.connect(handle_activation_attempt)

        current_message_for_dialog = initial_message if initial_message else "الرجاء إدخال كود التفعيل للمتابعة."
        current_is_error_for_dialog = initial_is_error
        activation_dialog.show_status_message(current_message_for_dialog, is_error=current_is_error_for_dialog)

        parent_window_for_centering = self if self.isVisible() else QApplication.desktop()
        screen_geometry = QApplication.desktop().availableGeometry(parent_window_for_centering)

        activation_dialog.adjustSize()

        x_pos = screen_geometry.left() + (screen_geometry.width() - activation_dialog.width()) // 2
        y_pos = screen_geometry.top() + (screen_geometry.height() - activation_dialog.height()) // 2
        activation_dialog.move(x_pos, y_pos)
        logger.info(f"تم تعيين موقع حوار التفعيل إلى: ({x_pos}, {y_pos}) على الشاشة.")


        dialog_result_code = activation_dialog.exec_()

        if self.activation_thread and self.activation_thread.isRunning():
            logger.info("Activation dialog closed, stopping activation thread if running.")
            self.activation_thread.stop()
            self.activation_thread.wait(1000)

        self.activation_dialog_open = False

        if dialog_result_code == QDialog.Accepted:
            # self.activation_successful يتم تحديثه داخل _process_activation_result
            # إذا تم قبول الحوار، فهذا يعني أن _process_activation_result أعاد True
            return True
        else:
            logger.warning(f"AnemApp: عملية التفعيل ألغيت من قبل المستخدم أو أُغلقت (Result: {dialog_result_code}).")
            # إذا لم يتم التفعيل بنجاح (سواء بالإلغاء أو الفشل)، فإن self.activation_successful يجب أن تكون False
            # وهذا سيتم التعامل معه في _initialize_and_check_activation
            return False # يشير إلى أن حلقة الحوار انتهت بدون تفعيل ناجح

    def _show_subscription_details_dialog(self):
        if self.current_subscription_data:
            dialog = SubscriptionDetailsDialog(self.current_subscription_data, self)
            dialog.exec_()
        elif self.activated_code_id and self.firebase_service.is_initialized():
            self._show_toast("جاري جلب تفاصيل الاشتراك...", type="info")
            QApplication.processEvents()
            code_data, error_msg = self.firebase_service.get_activation_code_details(self.activated_code_id)
            if code_data:
                self.current_subscription_data = code_data
                dialog = SubscriptionDetailsDialog(self.current_subscription_data, self)
                dialog.exec_()
            else:
                QMessageBox.warning(self, "خطأ", f"لم يتم العثور على تفاصيل الاشتراك للكود {self.activated_code_id}: {error_msg}")
        else:
             QMessageBox.information(self, "لا توجد تفاصيل", "لم يتم تفعيل البرنامج أو لا يمكن الوصول لمعلومات الاشتراك حاليًا.")

    def _pass_subscription_update_to_signal(self, updated_data, error_message):
        self.subscription_updated_signal.emit(updated_data, error_message)

    def _handle_subscription_update_from_signal(self, updated_data, error_message):
        logger.info(f"AnemApp: Subscription update received via signal: Data={bool(updated_data)}, Error='{error_message}'")

        critical_error_occurred = False
        critical_message = ""

        if error_message:
            logger.error(f"AnemApp: خطأ في مستمع تحديثات الاشتراك: {error_message}")
            if error_message == "DocumentDeleted":
                critical_message = "تم حذف كود التفعيل الخاص بك من الخادم."
                critical_error_occurred = True
            else:
                self.update_status_bar_message(f"خطأ في تحديث الاشتراك: {error_message}", is_general_message=True)
                self._show_toast(f"خطأ في تحديث حالة الاشتراك: {error_message}", type="error")
                if not updated_data: # إذا كان هناك خطأ ولا توجد بيانات محدثة، فهذا أمر خطير
                    critical_message = f"حدث خطأ أثناء تحديث حالة الاشتراك ({error_message}). قد تحتاج لإعادة التفعيل."
                    critical_error_occurred = True


        if updated_data:
            old_status = self.current_subscription_data.get("status", "UNKNOWN") if self.current_subscription_data else "UNKNOWN"
            self.current_subscription_data = updated_data # تحديث البيانات الحالية دائمًا

            new_status_from_server = updated_data.get("status", "UNKNOWN").upper()
            actual_expires_at = updated_data.get("actualExpiresAt") # يفترض أن يكون datetime object
            activated_devices_list = updated_data.get("activatedDevices", [])

            effective_status = new_status_from_server # نبدأ بالحالة من الخادم

            # تحقق إذا كان الجهاز الحالي لا يزال في قائمة الأجهزة المفعلة
            current_device_still_active = False
            if self.current_device_id:
                for dev_entry in activated_devices_list:
                    if isinstance(dev_entry, dict) and dev_entry.get("generated_device_id") == self.current_device_id:
                        current_device_still_active = True
                        break

            if effective_status == "ACTIVE" and not current_device_still_active and self.activated_code_id: # إذا كان الكود نشطًا ولكن الجهاز الحالي ليس في القائمة
                if not critical_error_occurred: # لا تقم بالكتابة فوق رسالة خطأ أهم
                    critical_message = "لم يعد هذا الجهاز مصرحًا له باستخدام هذا الكود. قد يكون تم تفعيله على أجهزة أخرى أو تم إزالته من قبل المسؤول."
                critical_error_occurred = True
                effective_status = "DEVICE_REMOVED" # حالة داخلية للإشارة إلى هذه المشكلة

            # تحقق من انتهاء الصلاحية إذا كان الكود نشطًا
            if effective_status == "ACTIVE" and actual_expires_at and actual_expires_at <= datetime.datetime.now(datetime.timezone.utc):
                if not critical_error_occurred:
                    critical_message = "صلاحية اشتراكك قد انتهت."
                critical_error_occurred = True
                effective_status = "EXPIRED" # تحديث الحالة الفعالة
                logger.warning(f"AnemApp: Listener detected expiry for code {self.activated_code_id}. Server status was {new_status_from_server}.")


            # التعامل مع الحالات التي تعتبر خطأ فادحًا مباشرة من الخادم
            if new_status_from_server == "REVOKED":
                if not critical_error_occurred:
                    critical_message = "تم إلغاء اشتراكك من قبل المسؤول."
                critical_error_occurred = True
                effective_status = "REVOKED" # ضمان أن الحالة الفعالة هي REVOKED

            elif new_status_from_server == "EXPIRED": # إذا كان الخادم يقول صراحة أنه منتهي الصلاحية
                 if not critical_error_occurred:
                    critical_message = "صلاحية اشتراكك قد انتهت (وفقًا للخادم)."
                 critical_error_occurred = True
                 effective_status = "EXPIRED"


            # تحديث واجهة المستخدم بناءً على الحالة الفعالة
            expiry_text_display = "لا يوجد تاريخ انتهاء"
            remaining_time_str_display = ""
            if actual_expires_at and isinstance(actual_expires_at, datetime.datetime):
                q_dt_local_expiry = QDateTime.fromSecsSinceEpoch(int(actual_expires_at.timestamp()), Qt.UTC).toLocalTime()
                expiry_text_display = q_dt_local_expiry.toString("yyyy/MM/dd hh:mm AP")
                if effective_status == "ACTIVE" and actual_expires_at > datetime.datetime.now(datetime.timezone.utc): # فقط إذا كان نشطًا وغير منتهي الصلاحية
                    remaining_delta = actual_expires_at - datetime.datetime.now(datetime.timezone.utc)
                    days, hours, minutes = remaining_delta.days, remaining_delta.seconds // 3600, (remaining_delta.seconds // 60) % 60
                    if days > 0: remaining_time_str_display = f" (متبقي: {days}ي {hours}س)"
                    elif hours > 0: remaining_time_str_display = f" (متبقي: {hours}س {minutes}د)"
                    else: remaining_time_str_display = f" (متبقي: {minutes}د)"


            status_display_map = {"ACTIVE": "نشط", "EXPIRED": "منتهي الصلاحية",
                                  "REVOKED": "تم إلغاؤه", "UNUSED": "غير مستخدم",
                                  "DEVICE_REMOVED": "الجهاز غير مصرح له"}
            status_text_for_gui = status_display_map.get(effective_status, effective_status) # استخدام الحالة الفعالة
            self.update_status_bar_message(f"الاشتراك: {status_text_for_gui}, ينتهي في: {expiry_text_display}{remaining_time_str_display}", is_general_message=True)


            # إذا كانت الحالة الفعالة ليست نشطة، فهذا خطأ فادح
            if effective_status != "ACTIVE":
                if not critical_error_occurred: # إذا لم يتم تعيين رسالة خطأ فادح بالفعل
                    if effective_status == "EXPIRED": critical_message = "صلاحية اشتراكك قد انتهت."
                    elif effective_status == "DEVICE_REMOVED": critical_message = "لم يعد هذا الجهاز مصرحًا له باستخدام هذا الكود."
                    elif old_status == "ACTIVE": # إذا كانت الحالة السابقة نشطة والآن تغيرت لشيء آخر
                         critical_message = f"تغيرت حالة اشتراكك إلى '{status_text_for_gui}'. لا يمكن متابعة استخدام البرنامج."
                critical_error_occurred = True # التأكيد على وجود خطأ فادح
            elif old_status != "ACTIVE" and not critical_error_occurred: # إذا كانت الحالة السابقة ليست نشطة والآن أصبحت نشطة
                self._enable_app_functions()
                self._show_toast("تم تحديث معلومات الاشتراك بنجاح. البرنامج نشط.", type="success")

        elif not error_message: # لا توجد بيانات محدثة ولا يوجد خطأ (حالة غير متوقعة)
            logger.warning("AnemApp: Received empty data in subscription update without error from listener.")
            # يمكن اعتبار هذا خطأ فادحًا إذا كان من المفترض دائمًا وجود بيانات
            # critical_message = "فقد الاتصال ببيانات الاشتراك. قد تحتاج لإعادة التفعيل."
            # critical_error_occurred = True


        if critical_error_occurred:
            final_critical_msg = critical_message if critical_message else "حدث خطأ في حالة الاشتراك يمنع استخدام البرنامج."
            self._show_critical_subscription_error(final_critical_msg) # هذا سيعطل وظائف التطبيق
            self._clear_local_activation_and_state(f"Critical subscription issue: {final_critical_msg}") # مسح التفعيل المحلي
            if not self.activation_dialog_open: # فقط إذا لم يكن حوار التفعيل مفتوحًا بالفعل
                logger.info("AnemApp: Attempting to re-show activation dialog due to critical subscription error.")
                QTimer.singleShot(100, lambda: self._initialize_and_check_activation()) # محاولة إعادة التفعيل

    def _show_critical_subscription_error(self, message):
        logger.critical(f"AnemApp: Critical subscription error: {message}")
        if not self.activation_dialog_open: # لا تظهر رسالة إذا كان حوار التفعيل مفتوحًا
            QMessageBox.critical(self, "خطأ في الاشتراك", message + "\nسيتم تعطيل وظائف البرنامج.", QMessageBox.Ok)
        self._disable_app_functions() # تعطيل وظائف التطبيق

    def _disable_app_functions(self):
        logger.info("AnemApp: Disabling application functions.")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.add_member_button.setEnabled(False)
        self.remove_member_button.setEnabled(False)
        if hasattr(self, 'settings_action'): self.settings_action.setEnabled(False)
        if self.monitoring_thread.isRunning(): # إيقاف المراقبة إذا كانت تعمل
            self.stop_monitoring()

    def _enable_app_functions(self):
        logger.info("AnemApp: Enabling application functions.")
        self.start_button.setEnabled(True)
        # self.stop_button سيتغير بناءً على حالة المراقبة
        self.add_member_button.setEnabled(True)
        self.remove_member_button.setEnabled(True)
        if hasattr(self, 'settings_action'): self.settings_action.setEnabled(True)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)

        menubar = self.menuBar()
        file_menu = menubar.addMenu("ملف")
        self.settings_action = QAction(QIcon.fromTheme("preferences-system"), "الإعدادات...", self)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(self.settings_action)

        tools_menu = menubar.addMenu("أدوات")
        self.toggle_search_filter_action = QAction("إظهار/إخفاء البحث والفلترة", self)
        self.toggle_search_filter_action.setCheckable(True)
        self.toggle_search_filter_action.setChecked(True)
        self.toggle_search_filter_action.triggered.connect(self.toggle_search_filter_bar)
        tools_menu.addAction(self.toggle_search_filter_action)

        self.toggle_details_action = QAction("إظهار التفاصيل", self)
        self.toggle_details_action.setCheckable(True)
        self.toggle_details_action.setChecked(False)
        self.toggle_details_action.triggered.connect(self.toggle_column_visibility)
        tools_menu.addAction(self.toggle_details_action)

        self.view_subscription_action = QAction(QIcon.fromTheme("security-high", self.style().standardIcon(QStyle.SP_MessageBoxInformation)), "عرض تفاصيل الاشتراك", self)
        self.view_subscription_action.triggered.connect(self._show_subscription_details_dialog)
        tools_menu.addAction(self.view_subscription_action)


        file_menu.addSeparator()
        exit_action = QAction(QIcon.fromTheme("application-exit"), "خروج", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        header_frame = QFrame(self)
        header_frame.setObjectName("HeaderFrame")
        header_layout = QHBoxLayout(header_frame)
        app_title_label = QLabel("برنامج إدارة مواعيد منحة البطالة", self)
        header_layout.addWidget(app_title_label, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        header_layout.addStretch()
        self.datetime_label = QLabel(self)
        self.datetime_label.setObjectName("datetime_label")
        header_layout.addWidget(self.datetime_label, alignment=Qt.AlignRight | Qt.AlignVCenter)
        self.update_datetime() # تحديث أولي
        self.datetime_timer = QTimer(self)
        self.datetime_timer.timeout.connect(self.update_datetime)
        self.datetime_timer.start(1000) # تحديث كل ثانية
        main_layout.addWidget(header_frame)

        self.search_filter_frame = QFrame(self)
        self.search_filter_frame.setObjectName("SearchFilterFrame")
        search_filter_layout = QHBoxLayout(self.search_filter_frame)
        search_filter_layout.setSpacing(10)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("بحث بالاسم, NIN, الوسيط...")
        self.search_input.textChanged.connect(self.apply_filter_and_search)
        search_filter_layout.addWidget(self.search_input, 2)

        self.filter_by_combo = QComboBox(self)
        self.filter_by_combo.addItem("فلترة حسب...", None)
        self.filter_by_combo.addItem("الحالة", "status")
        self.filter_by_combo.addItem("لديه موعد", "has_rdv")
        self.filter_by_combo.addItem("مستفيد حاليًا", "have_allocation")
        self.filter_by_combo.addItem("تم تحميل PDF التعهد", "pdf_honneur")
        self.filter_by_combo.addItem("تم تحميل PDF الموعد", "pdf_rdv")
        self.filter_by_combo.currentIndexChanged.connect(self.on_filter_by_changed)
        search_filter_layout.addWidget(self.filter_by_combo, 1)

        self.filter_value_combo = QComboBox(self)
        self.filter_value_combo.setVisible(False)
        self.filter_value_combo.currentIndexChanged.connect(self.apply_filter_and_search)
        search_filter_layout.addWidget(self.filter_value_combo, 1)

        self.clear_filter_button = QPushButton("مسح الفلتر", self)
        self.clear_filter_button.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        self.clear_filter_button.clicked.connect(self.clear_filter_and_search)
        search_filter_layout.addWidget(self.clear_filter_button)

        main_layout.addWidget(self.search_filter_frame)


        main_controls_frame = QFrame(self)
        main_controls_layout = QHBoxLayout(main_controls_frame)
        section_title_label = QLabel("إدارة المستفيدين", self)
        section_title_label.setObjectName("section_title_label")
        main_controls_layout.addWidget(section_title_label, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        main_controls_layout.addStretch()
        main_layout.addWidget(main_controls_frame)


        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.status_bar_label = QLabel("جاهز.")
        self.last_scan_label = QLabel("")
        self.countdown_label = QLabel("")
        self.statusBar.addWidget(self.status_bar_label, 1)
        self.statusBar.addPermanentWidget(self.countdown_label)
        self.statusBar.addPermanentWidget(self.last_scan_label)


        self.table = QTableWidget(self)
        self.table.setColumnCount(self.COL_DETAILS + 1)
        self.table.setHorizontalHeaderLabels([
            "أيقونة", "الاسم الكامل", "رقم التعريف", "رقم الوسيط",
            "الحساب البريدي", "رقم الهاتف", "الحالة", "تاريخ الموعد", "آخر تحديث/خطأ"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)

        self.toggle_column_visibility(self.toggle_details_action.isChecked()) # تطبيق الحالة الأولية

        header.setSectionResizeMode(self.COL_ICON, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_FULL_NAME_AR, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_PHONE_NUMBER, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeToContents)
        header.setMinimumSectionSize(150)
        header.setSectionResizeMode(self.COL_RDV_DATE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_DETAILS, QHeaderView.Stretch)


        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.itemDoubleClicked.connect(self.edit_member_details)
        self.table.verticalHeader().setVisible(True) # إظهار أرقام الصفوف
        main_layout.addWidget(self.table)


        bottom_controls_layout = QHBoxLayout()
        self.add_member_button = QPushButton("إضافة عضو", self)
        self.add_member_button.setObjectName("add_member_button")
        self.add_member_button.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        self.add_member_button.clicked.connect(self.add_member)
        bottom_controls_layout.addWidget(self.add_member_button)
        self.remove_member_button = QPushButton("حذف المحدد", self)
        self.remove_member_button.setObjectName("remove_member_button")
        self.remove_member_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.remove_member_button.clicked.connect(self.remove_member)
        bottom_controls_layout.addWidget(self.remove_member_button)
        bottom_controls_layout.addStretch()
        self.start_button = QPushButton("بدء المراقبة", self)
        self.start_button.setObjectName("start_button")
        self.start_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_button.clicked.connect(self.start_monitoring)
        bottom_controls_layout.addWidget(self.start_button)
        self.stop_button = QPushButton("إيقاف المراقبة", self)
        self.stop_button.setObjectName("stop_button")
        self.stop_button.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_monitoring)
        bottom_controls_layout.addWidget(self.stop_button)
        main_layout.addLayout(bottom_controls_layout)

        # تعطيل الوظائف مبدئيًا إذا لم يكن التفعيل ناجحًا
        if not self.activation_successful or \
           (self.current_subscription_data and self.current_subscription_data.get("status", "").upper() != "ACTIVE"):
            self._disable_app_functions()
        else:
            self._enable_app_functions() # تمكين إذا كان التفعيل ناجحًا

        self.update_status_bar_message("التطبيق جاهز.", is_general_message=True)

    def toggle_search_filter_bar(self, checked):
        self.search_filter_frame.setVisible(checked)
        self.toggle_search_filter_action.setChecked(checked) # مزامنة حالة الأكشن

    def on_filter_by_changed(self, index):
        filter_key = self.filter_by_combo.itemData(index)
        self.filter_value_combo.clear()
        self.filter_value_combo.setVisible(False)

        if filter_key == "status":
            statuses = sorted(list(set(m.status for m in self.members_list)))
            self.filter_value_combo.addItem("اختر الحالة...", None)
            for status in statuses:
                self.filter_value_combo.addItem(status, status)
            self.filter_value_combo.setVisible(True)
        elif filter_key in ["has_rdv", "have_allocation", "pdf_honneur", "pdf_rdv"]:
            self.filter_value_combo.addItem("اختر القيمة...", None)
            self.filter_value_combo.addItem("نعم", True)
            self.filter_value_combo.addItem("لا", False)
            self.filter_value_combo.setVisible(True)
        # لا حاجة لاستدعاء apply_filter_and_search هنا، سيتم استدعاؤه عند تغيير filter_value_combo أو البحث
        self.apply_filter_and_search() # استدعاء الفلترة عند تغيير نوع الفلتر الرئيسي أيضًا

    def clear_filter_and_search(self):
        self.search_input.clear()
        self.filter_by_combo.setCurrentIndex(0) # هذا سيؤدي إلى استدعاء on_filter_by_changed الذي بدوره يستدعي apply_filter_and_search
        # self.filter_value_combo.clear() # سيتم مسحه بواسطة on_filter_by_changed
        # self.filter_value_combo.setVisible(False) # سيتم إخفاؤه بواسطة on_filter_by_changed
        # self.is_filter_active = False # سيتم تحديثه بواسطة apply_filter_and_search
        # self.update_table() # سيتم تحديثه بواسطة apply_filter_and_search
        self._show_toast("تم مسح الفلتر بنجاح.", type="info")
        self.update_status_bar_message("تم مسح الفلتر.", is_general_message=True)


    def apply_filter_and_search(self):
        search_term = self.search_input.text().lower().strip()
        filter_key = self.filter_by_combo.itemData(self.filter_by_combo.currentIndex())
        filter_value_data = self.filter_value_combo.itemData(self.filter_value_combo.currentIndex())

        current_list_to_filter = list(self.members_list) # ابدأ دائمًا من القائمة الكاملة

        self.is_filter_active = bool(search_term or (filter_key and filter_value_data is not None))

        if not self.is_filter_active:
            self.filtered_members_list = list(self.members_list) # عرض جميع الأعضاء
            self.update_table()
            if hasattr(self, '_last_filter_applied') and self._last_filter_applied: # فقط إذا كان هناك فلتر مطبق سابقًا
                self.update_status_bar_message("تم عرض جميع الأعضاء.", is_general_message=True)
            self._last_filter_applied = False # تتبع حالة الفلتر
            return

        temp_filtered_list = []

        for member in current_list_to_filter:
            match_search = True
            if search_term:
                match_search = (search_term in (member.nin or "").lower() or
                                search_term in (member.wassit_no or "").lower() or
                                search_term in (member.get_full_name_ar() or "").lower() or
                                search_term in (member.nom_fr or "").lower() or
                                search_term in (member.prenom_fr or "").lower() or
                                search_term in (member.phone_number or "").lower() or
                                search_term in (member.ccp or "").lower())

            match_filter = True
            if filter_key and filter_value_data is not None: # فقط إذا تم اختيار قيمة للفلتر
                if filter_key == "status":
                    match_filter = member.status == filter_value_data
                elif filter_key == "has_rdv":
                    match_filter = member.already_has_rdv == filter_value_data
                elif filter_key == "have_allocation":
                    match_filter = member.have_allocation == filter_value_data
                elif filter_key == "pdf_honneur":
                    match_filter = bool(member.pdf_honneur_path) == filter_value_data
                elif filter_key == "pdf_rdv":
                    match_filter = bool(member.pdf_rdv_path) == filter_value_data

            if match_search and match_filter:
                temp_filtered_list.append(member)

        self.filtered_members_list = temp_filtered_list
        self.update_table() # تحديث الجدول بالقائمة المفلترة
        self.update_status_bar_message(f"تم تطبيق الفلتر. عدد النتائج: {len(self.filtered_members_list)}", is_general_message=True)
        self._last_filter_applied = True # تتبع حالة الفلتر

    def show_table_context_menu(self, position):
        selected_items = self.table.selectedItems()
        item_at_pos = self.table.itemAt(position) # الحصول على العنصر عند موضع النقر

        if not item_at_pos and not selected_items: # إذا لم يكن هناك عنصر محدد أو نقر على عنصر
            return

        row_index_in_table = -1
        if item_at_pos: # إذا تم النقر على عنصر، استخدم صفه
            row_index_in_table = item_at_pos.row()
        elif selected_items: # إذا لم يتم النقر على عنصر ولكن هناك تحديد، استخدم صف أول عنصر محدد
            row_index_in_table = selected_items[0].row()

        if row_index_in_table < 0: return # لم يتم تحديد صف صالح

        current_list_for_context = self.filtered_members_list if self.is_filter_active else self.members_list
        if row_index_in_table >= len(current_list_for_context): return # تحقق من الحدود

        member = current_list_for_context[row_index_in_table]
        try:
            original_member_index = self.members_list.index(member) # الحصول على الفهرس الأصلي
        except ValueError:
            logger.error(f"العضو {member.nin} من القائمة المفلترة غير موجود في القائمة الرئيسية.")
            self._show_toast(f"خطأ: العضو {self._get_member_display_name_with_index(member, -1)} غير موجود بشكل صحيح.", type="error")
            return

        menu = QMenu(self)
        member_display_name_with_index = self._get_member_display_name_with_index(member, original_member_index)

        view_action = QAction(QIcon.fromTheme("document-properties"), f"عرض معلومات {member_display_name_with_index}", self)
        view_action.triggered.connect(lambda: self.view_member_info(original_member_index))
        menu.addAction(view_action)

        check_now_action = QAction(QIcon.fromTheme("system-search"), f"فحص الآن لـ {member_display_name_with_index}", self)
        check_now_action.triggered.connect(lambda: self.check_member_now(original_member_index))
        menu.addAction(check_now_action)

        can_download_any_pdf = bool(member.pre_inscription_id) and \
                               member.status in ["لديه موعد مسبق", "تم الحجز", "مكتمل", "فشل تحميل PDF", "مستفيد حاليًا من المنحة"]

        download_all_action = QAction(QIcon.fromTheme("document-save-all", QIcon.fromTheme("document-save")), "تحميل جميع الشهادات", self)
        download_all_action.setEnabled(can_download_any_pdf)
        download_all_action.triggered.connect(lambda: self.download_all_member_pdfs(original_member_index))
        menu.addAction(download_all_action)

        menu.addSeparator()

        edit_action = QAction(QIcon.fromTheme("document-edit"), f"تعديل بيانات {member_display_name_with_index}", self)
        # تمرير عنصر الجدول (أو None إذا لم يتم النقر على عنصر) إلى edit_member_details
        edit_action.triggered.connect(lambda: self.edit_member_details(self.table.item(row_index_in_table, 0)))
        menu.addAction(edit_action)

        delete_action = QAction(QIcon.fromTheme("edit-delete"), f"حذف {member_display_name_with_index}", self)
        delete_action.triggered.connect(lambda: self.remove_specific_member(original_member_index))
        menu.addAction(delete_action)

        menu.exec_(self.table.viewport().mapToGlobal(position))

    def view_member_info(self, original_member_index):
        if 0 <= original_member_index < len(self.members_list):
            member = self.members_list[original_member_index]
            member_display_name = self._get_member_display_name_with_index(member, original_member_index)
            logger.info(f"طلب عرض معلومات العضو: {member_display_name}")
            self.update_status_bar_message(f"عرض معلومات العضو: {member_display_name}", is_general_message=True)
            dialog = ViewMemberDialog(member, self)
            dialog.exec_()
        else:
            logger.warning(f"view_member_info: فهرس خاطئ {original_member_index}")
            self._show_toast("خطأ في عرض معلومات العضو (فهرس غير صالح).", type="error")

    def check_member_now(self, original_member_index):
        if not self.activation_successful or (self.current_subscription_data and self.current_subscription_data.get("status","").upper() != "ACTIVE"):
            self._show_toast("لا يمكن إجراء الفحص. البرنامج غير مفعل أو الاشتراك غير نشط.", type="error")
            return

        if 0 <= original_member_index < len(self.members_list):
            member = self.members_list[original_member_index]
            member_display_name = self._get_member_display_name_with_index(member, original_member_index)

            if member.is_processing: # التحقق إذا كان العضو قيد المعالجة بالفعل
                 self._show_toast(f"العضو '{member_display_name}' قيد المعالجة حاليًا. يرجى الانتظار.", type="warning")
                 return

            if self.single_check_thread and self.single_check_thread.isRunning():
                self._show_toast("فحص آخر قيد التنفيذ بالفعل. يرجى الانتظار.", type="warning")
                return

            logger.info(f"طلب فحص فوري للعضو: {member_display_name}")
            self.update_status_bar_message(f"بدء الفحص الفوري للعضو: {member_display_name}...", is_general_message=False)
            self._show_toast(f"بدء الفحص الفوري للعضو: {member_display_name}", type="info")

            self.single_check_thread = SingleMemberCheckThread(member, original_member_index, self.api_client, self.settings.copy())
            self.single_check_thread.update_member_gui_signal.connect(self.update_member_gui_in_table)
            self.single_check_thread.new_data_fetched_signal.connect(self.update_member_name_in_table)
            self.single_check_thread.member_processing_started_signal.connect(lambda idx: self.handle_member_processing_signal(idx, True))
            self.single_check_thread.member_processing_finished_signal.connect(lambda idx: self.handle_member_processing_signal(idx, False))
            self.single_check_thread.global_log_signal.connect(self.update_status_bar_message)
            self.single_check_thread.start()
        else:
            logger.warning(f"check_member_now: فهرس خاطئ {original_member_index}")
            self._show_toast("خطأ في بدء الفحص الفوري (فهرس غير صالح).", type="error")

    def download_all_member_pdfs(self, original_member_index):
        if not self.activation_successful or (self.current_subscription_data and self.current_subscription_data.get("status","").upper() != "ACTIVE"):
            self._show_toast("لا يمكن تحميل الشهادات. البرنامج غير مفعل أو الاشتراك غير نشط.", type="error")
            return

        if not (0 <= original_member_index < len(self.members_list)):
            self._show_toast("فهرس عضو غير صالح لتحميل الشهادات.", type="error")
            return

        member = self.members_list[original_member_index]
        member_display_name = self._get_member_display_name_with_index(member, original_member_index)

        if member.is_processing and self.active_download_all_pdfs_threads.get(original_member_index): # تحقق إذا كان قيد المعالجة بواسطة هذا الخيط
            self._show_toast(f"تحميل شهادات العضو '{member_display_name}' قيد التنفيذ بالفعل.", type="warning")
            return

        if self.active_download_all_pdfs_threads.get(original_member_index) and self.active_download_all_pdfs_threads[original_member_index].isRunning():
            self._show_toast(f"تحميل شهادات العضو '{member_display_name}' قيد التنفيذ بالفعل.", type="warning")
            return

        if not member.pre_inscription_id:
            self._show_toast(f"ID التسجيل المسبق مفقود للعضو {member_display_name}. لا يمكن تحميل الشهادات.", type="error")
            return

        logger.info(f"طلب تحميل جميع الشهادات للعضو: {member_display_name}")
        self.update_status_bar_message(f"بدء تحميل جميع الشهادات لـ {member_display_name}...", is_general_message=False)
        self._show_toast(f"بدء تحميل جميع الشهادات لـ {member_display_name}", type="info")

        all_pdfs_thread = DownloadAllPdfsThread(member, original_member_index, self.api_client)
        all_pdfs_thread.all_pdfs_download_finished_signal.connect(self.handle_all_pdfs_download_finished)
        all_pdfs_thread.individual_pdf_status_signal.connect(self.handle_individual_pdf_status)
        all_pdfs_thread.member_processing_started_signal.connect(lambda idx: self.handle_member_processing_signal(idx, True))
        # ربط انتهاء الخيط بـ _clear_active_download_thread لضمان تنظيف الحالة
        all_pdfs_thread.member_processing_finished_signal.connect(lambda idx, ri=original_member_index: self._clear_active_download_thread(ri))
        all_pdfs_thread.global_log_signal.connect(self.update_status_bar_message)

        self.active_download_all_pdfs_threads[original_member_index] = all_pdfs_thread
        all_pdfs_thread.start()

    def _clear_active_download_thread(self, original_member_index):
        if original_member_index in self.active_download_all_pdfs_threads:
            del self.active_download_all_pdfs_threads[original_member_index]
        # التأكد من أن is_processing يتم تحديثها بشكل صحيح
        self.handle_member_processing_signal(original_member_index, False) # استدعاء هذا لتحديث is_processing
        if 0 <= original_member_index < len(self.members_list):
            member = self.members_list[original_member_index]
            member_display_name = self._get_member_display_name_with_index(member, original_member_index)
            self.update_status_bar_message(f"انتهت معالجة تحميل الشهادات للعضو: {member_display_name}", is_general_message=True)


    def handle_individual_pdf_status(self, original_member_index, pdf_type, file_path_or_status_msg_from_thread, success, error_msg_for_toast_from_thread):
        if not (0 <= original_member_index < len(self.members_list)):
            return
        member = self.members_list[original_member_index]

        pdf_type_ar = "التعهد" if pdf_type == "HonneurEngagementReport" else "الموعد"
        member_name_display = self._get_member_display_name_with_index(member, original_member_index)

        if success:
            file_path = file_path_or_status_msg_from_thread # إذا نجح، فهذا هو المسار
            if pdf_type == "HonneurEngagementReport":
                member.pdf_honneur_path = file_path
            elif pdf_type == "RdvReport":
                member.pdf_rdv_path = file_path

            activity_detail = f"تم تحميل شهادة {pdf_type_ar} بنجاح إلى {os.path.basename(file_path)}."
            member.set_activity_detail(file_path_or_status_msg_from_thread if os.path.exists(file_path_or_status_msg_from_thread) else activity_detail)
            toast_msg = f"للعضو {member_name_display}: {activity_detail}\nالمسار: {file_path}"
            self._show_toast(toast_msg, type="success", duration=5000)
            self.update_status_bar_message(f"تم تحميل شهادة {pdf_type_ar} للعضو {member_name_display}.", is_general_message=True)
        else:
            activity_detail = file_path_or_status_msg_from_thread # إذا فشل، فهذه رسالة الخطأ
            member.set_activity_detail(activity_detail, is_error=True)
            toast_msg = f"للعضو {member_name_display}: فشل تحميل شهادة {pdf_type_ar}. السبب: {error_msg_for_toast_from_thread or activity_detail}"
            self._show_toast(toast_msg, type="error", duration=6000)
            self.update_status_bar_message(f"فشل تحميل شهادة {pdf_type_ar} للعضو {member_name_display}.", is_general_message=True)

        self.update_member_gui_in_table(original_member_index, member.status, member.last_activity_detail, get_icon_name_for_status(member.status))
        self.save_members_data()


    def handle_all_pdfs_download_finished(self, original_member_index, honneur_path, rdv_path, overall_status_msg, all_success, first_error_msg):
        if not (0 <= original_member_index < len(self.members_list)):
            logger.warning(f"handle_all_pdfs_download_finished: فهرس خاطئ {original_member_index}")
            return

        member = self.members_list[original_member_index]
        member_name_display = self._get_member_display_name_with_index(member, original_member_index)

        if honneur_path: member.pdf_honneur_path = honneur_path
        if rdv_path: member.pdf_rdv_path = rdv_path

        if all_success:
            if member.status != "مستفيد حاليًا من المنحة": # لا تغير الحالة إذا كان مستفيدًا بالفعل
                # إذا تم تحميل ملف التعهد، وملف الموعد (إذا كان لديه موعد)، أو ملف التعهد فقط (إذا لم يكن لديه موعد)
                if (member.pdf_honneur_path and member.pdf_rdv_path) or \
                   (member.pdf_honneur_path and not (member.already_has_rdv or member.rdv_id or member.status == "تم الحجز")):
                    member.status = "مكتمل"
                elif member.pdf_honneur_path or member.pdf_rdv_path : # إذا تم تحميل أحدهما على الأقل
                     member.status = "تم الحجز" # أو أي حالة مناسبة أخرى

            member.set_activity_detail(overall_status_msg)
            final_toast_msg = f"للعضو {member_name_display}: {overall_status_msg}"
            self._show_toast(final_toast_msg, type="success", duration=7000)
            self.update_status_bar_message(f"اكتمل تحميل شهادات العضو {member_name_display}.", is_general_message=True)

            # فتح المجلد بعد التحميل الناجح
            folder_to_open = None
            if honneur_path: folder_to_open = os.path.dirname(honneur_path)
            elif rdv_path: folder_to_open = os.path.dirname(rdv_path)

            # إذا لم يتم تحديد مسار، حاول بناء المسار الافتراضي
            if not folder_to_open and member.pre_inscription_id: # تأكد من وجود pre_inscription_id
                documents_location = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
                base_app_dir_name = "ملفات_المنحة_البرنامج"
                member_name_for_folder_path = member.get_full_name_ar()
                if not member_name_for_folder_path or member_name_for_folder_path.isspace():
                    member_name_for_folder_path = member.nin # استخدام NIN كاسم مجلد احتياطي
                safe_folder_name_part = "".join(c for c in member_name_for_folder_path if c.isalnum() or c in (' ', '_', '-')).rstrip().replace(" ", "_")
                if not safe_folder_name_part: safe_folder_name_part = member.nin # احتياطي آخر
                folder_to_open = os.path.join(documents_location, base_app_dir_name, safe_folder_name_part)


            if folder_to_open and os.path.exists(folder_to_open):
                reply = QMessageBox.question(self, 'فتح المجلد', f"تم حفظ الملفات بنجاح في المجلد:\n{folder_to_open}\n\nهل تريد فتح هذا المجلد؟",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if reply == QMessageBox.Yes:
                    try:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.realpath(folder_to_open)))
                    except Exception as e_open:
                        logger.error(f"فشل فتح مجلد الملفات: {e_open}")
                        self._show_toast(f"فشل فتح مجلد الملفات: {e_open}", type="warning")
        else:
            if "فشل تحميل PDF" not in member.status and member.status != "مستفيد حاليًا من المنحة": # لا تغير الحالة إذا كان مستفيدًا
                member.status = "فشل تحميل PDF"

            final_detail_msg = overall_status_msg
            if first_error_msg and first_error_msg not in final_detail_msg: # إضافة الخطأ الأول إذا لم يكن موجودًا بالفعل
                final_detail_msg += f" (الخطأ الأول: {first_error_msg.split(':')[0]})" # عرض الجزء الأول من الخطأ فقط
            member.set_activity_detail(final_detail_msg, is_error=True)
            final_toast_msg = f"للعضو {member_name_display}: فشل تحميل بعض الشهادات.\n{overall_status_msg}"
            self._show_toast(final_toast_msg, type="error", duration=7000)
            self.update_status_bar_message(f"فشل تحميل بعض شهادات العضو {member_name_display}.", is_general_message=True)

        self.update_member_gui_in_table(original_member_index, member.status, member.last_activity_detail, get_icon_name_for_status(member.status))
        self.save_members_data()


    def remove_specific_member(self, original_member_index):
        if not (0 <= original_member_index < len(self.members_list)):
            self._show_toast("فهرس عضو غير صالح للحذف.", type="error")
            return

        member_to_remove = self.members_list[original_member_index]
        member_display_name = self._get_member_display_name_with_index(member_to_remove, original_member_index)
        confirm_delete = QMessageBox.question(self, "تأكيد الحذف",
                                              f"هل أنت متأكد أنك تريد حذف العضو '{member_display_name}'؟",
                                              QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm_delete == QMessageBox.No:
            return

        self.members_list.pop(original_member_index) # الحذف من القائمة الرئيسية

        if self.is_filter_active: # إذا كان الفلتر نشطًا، أعد تطبيقه
            self.apply_filter_and_search()
        else: # إذا لم يكن الفلتر نشطًا، قم بتحديث الجدول مباشرة
            self.update_table()

        logger.info(f"تم حذف العضو: {member_display_name}")
        self.update_status_bar_message(f"تم حذف العضو: {member_display_name}", is_general_message=True)
        self._show_toast(f"تم حذف العضو: {member_display_name}", type="info")
        self.save_members_data() # حفظ التغييرات

        # تحديث فهرس المراقبة إذا لزم الأمر
        if self.monitoring_thread and self.monitoring_thread.current_member_index_to_process >= len(self.members_list):
            self.monitoring_thread.current_member_index_to_process = 0 # أو أي منطق آخر مناسب لإعادة التعيين


    def load_app_settings(self):
        loaded_settings = None
        primary_path = SETTINGS_FILE # من config.py، يشير الآن إلى APP_DATA_DIR
        backup_path = SETTINGS_FILE_BAK # من config.py

        if os.path.exists(primary_path):
            try:
                with open(primary_path, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                logger.info(f"تم تحميل الإعدادات من الملف الأساسي: {primary_path}")
            except json.JSONDecodeError:
                logger.error(f"خطأ في فك تشفير JSON للملف الأساسي {primary_path}. محاولة تحميل النسخة الاحتياطية.")
                loaded_settings = None # ضمان أن loaded_settings فارغ إذا فشل التحميل
            except Exception as e:
                logger.exception(f"خطأ غير متوقع عند تحميل الإعدادات من {primary_path}: {e}")
                loaded_settings = None

        if loaded_settings is None and os.path.exists(backup_path): # فقط إذا فشل التحميل من الأساسي
            try:
                with open(backup_path, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                logger.info(f"تم تحميل الإعدادات من الملف الاحتياطي: {backup_path}")
                # محاولة استعادة الملف الأساسي من النسخة الاحتياطية
                try:
                    shutil.copy2(backup_path, primary_path)
                    logger.info(f"تم استعادة الملف الأساسي {primary_path} من النسخة الاحتياطية {backup_path}.")
                except Exception as e_copy:
                    logger.error(f"فشل في استعادة الملف الأساسي من النسخة الاحتياطية: {e_copy}")
            except json.JSONDecodeError:
                logger.error(f"خطأ في فك تشفير JSON للملف الاحتياطي {backup_path}.")
                loaded_settings = None
            except Exception as e:
                logger.exception(f"خطأ غير متوقع عند تحميل الإعدادات من {backup_path}: {e}")
                loaded_settings = None

        if loaded_settings is not None:
            self.settings = loaded_settings
            # ضمان وجود جميع المفاتيح الافتراضية
            for key, default_value in DEFAULT_SETTINGS.items():
                if key not in self.settings:
                    self.settings[key] = default_value
                    logger.info(f"تمت إضافة المفتاح المفقود '{key}' إلى الإعدادات بالقيمة الافتراضية.")
            # حفظ الإعدادات إذا تم إضافة مفاتيح مفقودة
            if any(key not in loaded_settings for key in DEFAULT_SETTINGS.keys()):
                self.save_app_settings() # حفظ الإعدادات المحدثة
        else:
            logger.warning(f"لم يتم العثور على ملف الإعدادات ({primary_path}) أو الملف الاحتياطي ({backup_path})، أو كلاهما تالف. تم استخدام الإعدادات الافتراضية.")
            self.settings = DEFAULT_SETTINGS.copy()
            if not hasattr(self, 'toast_notifications'): # التأكد من التهيئة قبل الاستخدام
                self.toast_notifications = []
            self._show_toast("ملف الإعدادات غير موجود أو تالف. تم استخدام الإعدادات الافتراضية.", type="warning", duration=5000)
            self.save_app_settings() # حفظ الإعدادات الافتراضية


    def save_app_settings(self):
        primary_path = SETTINGS_FILE # من config.py
        tmp_path = SETTINGS_FILE_TMP # من config.py
        bak_path = SETTINGS_FILE_BAK # من config.py
        try:
            # الكتابة إلى ملف مؤقت أولاً
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
            # إذا كان الملف الأساسي موجودًا، قم بإنشاء نسخة احتياطية منه
            if os.path.exists(primary_path):
                try:
                    shutil.copy2(primary_path, bak_path) # استخدام copy2 للحفاظ على الميتاداتا
                    logger.debug(f"تم إنشاء نسخة احتياطية من {primary_path} إلى {bak_path}")
                except Exception as e_bak:
                    logger.error(f"فشل في إنشاء نسخة احتياطية لملف الإعدادات {primary_path}: {e_bak}")
            # استبدال الملف الأساسي بالملف المؤقت (عملية ذرية على معظم الأنظمة)
            os.replace(tmp_path, primary_path)
            logger.info(f"تم حفظ الإعدادات بنجاح في {primary_path}")
        except Exception as e:
            logger.exception(f"خطأ عند حفظ الإعدادات في {primary_path}: {e}")
            self._show_toast(f"فشل حفظ الإعدادات: {e}", type="error")
            # محاولة حذف الملف المؤقت إذا كان لا يزال موجودًا بعد خطأ
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as e_del_tmp:
                    logger.error(f"فشل في حذف الملف المؤقت للإعدادات {tmp_path} بعد خطأ في الحفظ: {e_del_tmp}")

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings.copy(), self) # تمرير نسخة من الإعدادات
        if dialog.exec_() == SettingsDialog.Accepted:
            new_settings = dialog.get_settings()
            self.settings.update(new_settings) # تحديث الإعدادات في الذاكرة
            self.save_app_settings() # حفظ الإعدادات المحدثة في الملف
            self.apply_app_settings() # تطبيق الإعدادات على المكونات النشطة
            self._show_toast("تم حفظ الإعدادات بنجاح وتطبيقها.", type="success")
            logger.info("تم تحديث إعدادات التطبيق.")
            self.update_status_bar_message("تم تحديث الإعدادات.", is_general_message=True)


    def apply_app_settings(self):
        # إعادة تهيئة AnemAPIClient بالإعدادات الجديدة
        self.api_client = AnemAPIClient(
            initial_backoff_general=self.settings.get(SETTING_BACKOFF_GENERAL, DEFAULT_SETTINGS[SETTING_BACKOFF_GENERAL]),
            initial_backoff_429=self.settings.get(SETTING_BACKOFF_429, DEFAULT_SETTINGS[SETTING_BACKOFF_429]),
            request_timeout=self.settings.get(SETTING_REQUEST_TIMEOUT, DEFAULT_SETTINGS[SETTING_REQUEST_TIMEOUT])
        )

        # تحديث إعدادات خيط المراقبة إذا كان يعمل
        if self.monitoring_thread.isRunning():
            self.monitoring_thread.update_thread_settings(self.settings.copy())
            monitoring_interval_minutes = self.settings.get(SETTING_MONITORING_INTERVAL, DEFAULT_SETTINGS[SETTING_MONITORING_INTERVAL])
            self.update_status_bar_message(f"المراقبة جارية (الدورة كل {monitoring_interval_minutes} دقيقة)...", is_general_message=False)
        else: # إذا لم يكن يعمل، فقط قم بتحديث إعداداته الداخلية
            self.monitoring_thread.settings = self.settings.copy()
            self.monitoring_thread._apply_settings() # استدعاء _apply_settings لتحديث المتغيرات الداخلية للخيط


    def _get_member_display_name_with_index(self, member, original_index):
        name_part = member.get_full_name_ar()
        if not name_part or name_part.isspace(): # إذا كان الاسم فارغًا أو مسافات فقط
            name_part = member.nin # استخدم NIN كاسم بديل
        return f"{name_part} (رقم {original_index + 1})"


    def _show_toast(self, message, type="info", duration=4000, member_obj=None, original_idx_if_member=None):
        max_toast_len = 150 # الحد الأقصى لطول رسالة التوست
        display_message = message

        # إذا كان التوست متعلقًا بعضو معين، قم بتضمين اسمه/رقم التعريف الخاص به
        if member_obj is not None and original_idx_if_member is not None:
            member_display_intro = self._get_member_display_name_with_index(member_obj, original_idx_if_member)
            full_message_with_member = f"{member_display_intro}: {message}"
            if len(full_message_with_member) > max_toast_len:
                # اقتطاع الرسالة إذا كانت طويلة جدًا مع اسم العضو
                remaining_len = max_toast_len - len(member_display_intro) - 5 # ترك مساحة لـ "...: "
                if remaining_len > 10 : # تأكد من وجود مساحة كافية للرسالة المقتطعة
                     display_message = f"{member_display_intro}: {message[:remaining_len]}..."
                else: # إذا لم تكن هناك مساحة كافية، اعرض فقط اسم العضو مع "..."
                     display_message = f"{member_display_intro}..."
            else:
                display_message = full_message_with_member
        elif len(message) > max_toast_len: # إذا كانت الرسالة عامة وطويلة
            display_message = message[:max_toast_len] + "..."

        toast = ToastNotification(self) # إنشاء إشعار توست جديد
        self.toast_notifications.append(toast) # إضافته إلى قائمة التوستات النشطة
        toast.showMessage(display_message, type, duration, parent_window=self) # عرض التوست
        # ربط انتهاء مؤقت التوست بإزالته من القائمة
        toast.timer.timeout.connect(lambda t=toast: self._remove_toast_reference(t))


    def _remove_toast_reference(self, toast_instance):
        if toast_instance in self.toast_notifications:
            self.toast_notifications.remove(toast_instance)


    def load_stylesheet(self):
        try:
            resolved_stylesheet_file = resource_path(STYLESHEET_FILE) # STYLESHEET_FILE من config
            with open(resolved_stylesheet_file, "r", encoding="utf-8") as f:
                style = f.read()
                self.setStyleSheet(style)
        except FileNotFoundError:
            logger.warning(f"ملف التنسيق {STYLESHEET_FILE} (المسار المحلول: {resolved_stylesheet_file if 'resolved_stylesheet_file' in locals() else 'غير محدد'}) غير موجود. سيتم استخدام التنسيق الافتراضي.")
            self._show_toast(f"ملف التنسيق {STYLESHEET_FILE} غير موجود.", type="warning")
        except Exception as e:
            logger.error(f"خطأ في تحميل ملف التنسيق {STYLESHEET_FILE}: {e}")
            self._show_toast(f"خطأ في تحميل ملف التنسيق: {e}", type="error")

    def update_datetime(self):
        now = QDateTime.currentDateTime()
        # استخدام QLocale للغة العربية (الجزائر) لتنسيق التاريخ والوقت
        arabic_locale = QLocale(QLocale.Arabic, QLocale.Algeria)
        # تنسيق التاريخ والوقت: اسم اليوم، اليوم الشهر السنة - الساعة:الدقيقة:الثانية صباحًا/مساءً
        self.datetime_label.setText(arabic_locale.toString(now, "dddd, dd MMMM yyyy - hh:mm:ss AP"))


    def toggle_column_visibility(self, checked):
        # إظهار أو إخفاء الأعمدة التفصيلية بناءً على حالة الزر
        self.table.setColumnHidden(self.COL_NIN, not checked)
        self.table.setColumnHidden(self.COL_WASSIT, not checked)
        self.table.setColumnHidden(self.COL_CCP, not checked)
        self.table.setColumnHidden(self.COL_PHONE_NUMBER, not checked)
        # تحديث نص زر التبديل
        self.toggle_details_action.setText("إخفاء التفاصيل" if checked else "إظهار التفاصيل")
        self.update_status_bar_message(f"تم {'إظهار' if checked else 'إخفاء'} الأعمدة التفصيلية.", is_general_message=True)


    def update_active_row_spinner_display(self):
        if self.active_spinner_row_in_view == -1 or not (0 <= self.active_spinner_row_in_view < self.table.rowCount()):
            return # لا يوجد صف نشط للسبينر أو الفهرس خارج الحدود

        current_list_displayed = self.filtered_members_list if self.is_filter_active else self.members_list

        # التحقق إذا كان الفهرس لا يزال صالحًا في القائمة المعروضة
        if self.active_spinner_row_in_view >= len(current_list_displayed):
            self.row_spinner_timer.stop()
            self.active_spinner_row_in_view = -1
            return

        member = current_list_displayed[self.active_spinner_row_in_view]
        try:
            original_member_index = self.members_list.index(member) # الحصول على الفهرس الأصلي
        except ValueError: # إذا لم يعد العضو موجودًا في القائمة الرئيسية
            self.row_spinner_timer.stop()
            self.active_spinner_row_in_view = -1
            return

        # إذا لم يعد العضو قيد المعالجة (باستثناء حالات خاصة مثل تحميل PDF أو فحص فردي لا يزال جاريًا)
        if not member.is_processing:
            # تحقق إذا كان هناك خيط تحميل PDF نشط لهذا العضو
            is_still_pdf_downloading = self.active_download_all_pdfs_threads.get(original_member_index) and \
                                       self.active_download_all_pdfs_threads[original_member_index].isRunning()
            # تحقق إذا كان هناك خيط فحص فردي نشط لهذا العضو
            is_still_single_checking = self.single_check_thread and \
                                       self.single_check_thread.isRunning() and \
                                       self.single_check_thread.index == original_member_index

            if not is_still_pdf_downloading and not is_still_single_checking: # إذا لم تكن هناك عمليات أخرى نشطة
                self.row_spinner_timer.stop()
                self.active_spinner_row_in_view = -1
            # تحديث واجهة المستخدم لتعكس الحالة النهائية (إزالة السبينر)
            self.update_member_gui_in_table(original_member_index, member.status, member.last_activity_detail, get_icon_name_for_status(member.status))
            return

        # تحديث حرف السبينر
        self.spinner_char_idx = (self.spinner_char_idx + 1) % len(self.spinner_chars)
        char = self.spinner_chars[self.spinner_char_idx]

        icon_item_in_table = self.table.item(self.active_spinner_row_in_view, self.COL_ICON)
        if icon_item_in_table:
            icon_item_in_table.setText(char) # عرض حرف السبينر
            icon_item_in_table.setIcon(QIcon()) # إزالة الأيقونة


    def handle_member_processing_signal(self, original_member_index, is_processing_now):
        if not (0 <= original_member_index < len(self.members_list)):
            logger.warning(f"HMP Signal: فهرس العضو الأصلي غير صالح {original_member_index}")
            return

        member = self.members_list[original_member_index]
        member.is_processing = is_processing_now # تحديث حالة المعالجة للعضو

        # البحث عن الصف المقابل في الجدول (قد يكون مفلترًا)
        row_in_table_to_update = -1
        current_list_displayed = self.filtered_members_list if self.is_filter_active else self.members_list
        try:
            row_in_table_to_update = current_list_displayed.index(member)
        except ValueError: # إذا لم يتم العثور على العضو في القائمة المعروضة حاليًا (نادر)
            return

        if not (0 <= row_in_table_to_update < self.table.rowCount()):
             logger.warning(f"HMP Signal: فهرس الجدول المحسوب {row_in_table_to_update} خارج الحدود لـ {self.table.rowCount()} صفوف.")
             return

        member_display_name = self._get_member_display_name_with_index(member, original_member_index)
        if is_processing_now:
            self.active_spinner_row_in_view = row_in_table_to_update # تحديد الصف النشط للسبينر
            self.spinner_char_idx = 0 # إعادة تعيين فهرس السبينر

            # تحديد الصف وجعله مرئيًا
            self.table.selectRow(row_in_table_to_update)
            first_column_item = self.table.item(row_in_table_to_update, 0) # أي عنصر في الصف
            if first_column_item:
                self.table.scrollToItem(first_column_item, QAbstractItemView.EnsureVisible)

            icon_item = self.table.item(row_in_table_to_update, self.COL_ICON)
            if icon_item:
                icon_item.setText(self.spinner_chars[self.spinner_char_idx]) # عرض أول حرف سبينر
                icon_item.setIcon(QIcon()) # إزالة الأيقونة

            self.highlight_processing_row(row_in_table_to_update, force_processing_display=True) # تمييز الصف

            if not self.row_spinner_timer.isActive(): # بدء مؤقت السبينر إذا لم يكن نشطًا
                self.row_spinner_timer.start(self.row_spinner_timer_interval)

            self.update_status_bar_message(f"جاري معالجة العضو: {member_display_name}...", is_general_message=False)

        else: # إذا انتهت المعالجة
            # تحقق إذا كان هناك عمليات أخرى لا تزال نشطة لهذا العضو (مثل تحميل PDF أو فحص فردي)
            is_still_pdf_downloading = self.active_download_all_pdfs_threads.get(original_member_index) and \
                                       self.active_download_all_pdfs_threads[original_member_index].isRunning()
            is_still_single_checking = self.single_check_thread and \
                                       self.single_check_thread.isRunning() and \
                                       self.single_check_thread.index == original_member_index

            if not is_still_pdf_downloading and not is_still_single_checking: # فقط إذا لم تكن هناك عمليات أخرى
                if self.active_spinner_row_in_view == row_in_table_to_update: # إذا كان هذا هو الصف النشط للسبينر
                    self.row_spinner_timer.stop()
                    self.active_spinner_row_in_view = -1 # إلغاء تحديد الصف النشط للسبينر
                    icon_item = self.table.item(row_in_table_to_update, self.COL_ICON)
                    if icon_item:
                        icon_item.setText("") # إزالة حرف السبينر

            self.highlight_processing_row(row_in_table_to_update, force_processing_display=False) # إزالة تمييز الصف


    def highlight_processing_row(self, row_index_in_table, force_processing_display=None):
        if not (0 <= row_index_in_table < self.table.rowCount()):
            return # الفهرس خارج الحدود

        current_list_displayed = self.filtered_members_list if self.is_filter_active else self.members_list
        if row_index_in_table >= len(current_list_displayed): # تحقق إضافي
            return

        member = current_list_displayed[row_index_in_table]
        is_processing_flag = force_processing_display if force_processing_display is not None else member.is_processing

        item_for_selection_check = self.table.item(row_index_in_table, 0) # أي عمود للتحقق من التحديد
        is_row_selected_by_user_or_code = False
        if item_for_selection_check:
            is_row_selected_by_user_or_code = item_for_selection_check.isSelected() # التحقق من التحديد

        # ألوان الخلفية
        default_bg_color = self.table.palette().color(QPalette.Base)
        alternate_bg_color = QColor(self.table.palette().color(QPalette.AlternateBase)) if self.table.alternatingRowColors() else default_bg_color
        processing_bg_color = QColorConstants.PROCESSING_ROW_DARK_THEME
        selection_bg_color_from_qss = QColor("#00A2E8") # لون التحديد من QSS

        for col in range(self.table.columnCount()):
            item = self.table.item(row_index_in_table, col)
            if item:
                if is_processing_flag: # إذا كان الصف قيد المعالجة
                    item.setBackground(processing_bg_color)
                    item.setForeground(Qt.white)
                elif is_row_selected_by_user_or_code: # إذا كان الصف محددًا
                    if item.background() != selection_bg_color_from_qss: # تجنب إعادة التعيين غير الضرورية
                         item.setBackground(selection_bg_color_from_qss)
                    if item.foreground().color() != Qt.white: # تأكد من لون النص
                         item.setForeground(Qt.white)
                else: # إذا لم يكن قيد المعالجة ولا محددًا (الحالة العادية)
                    status_text_for_color = member.status
                    specific_color = None
                    # تحديد لون خاص بناءً على حالة العضو
                    if status_text_for_color == "مستفيد حاليًا من المنحة": specific_color = QColorConstants.BENEFITING_GREEN_DARK_THEME
                    elif status_text_for_color == "بيانات الإدخال خاطئة": specific_color = QColorConstants.PINK_DARK_THEME
                    elif status_text_for_color == "لديه موعد مسبق": specific_color = QColorConstants.LIGHT_BLUE_DARK_THEME
                    elif status_text_for_color == "غير مؤهل للحجز": specific_color = QColorConstants.ORANGE_RED_DARK_THEME
                    elif status_text_for_color == "مكتمل": specific_color = QColorConstants.LIGHT_GREEN_DARK_THEME
                    elif "فشل" in status_text_for_color or "غير مؤهل" in status_text_for_color or "خطأ" in status_text_for_color:
                        specific_color = QColorConstants.LIGHT_PINK_DARK_THEME
                    elif "يتطلب تسجيل مسبق" in status_text_for_color: specific_color = QColorConstants.LIGHT_YELLOW_DARK_THEME

                    if specific_color:
                        item.setBackground(specific_color)
                    else: # إذا لم يكن هناك لون خاص، استخدم الألوان الافتراضية/المتناوبة
                        if self.table.alternatingRowColors() and row_index_in_table % 2 != 0 :
                            item.setBackground(alternate_bg_color)
                        else:
                            item.setBackground(default_bg_color)
                    item.setForeground(self.table.palette().color(QPalette.Text)) # لون النص الافتراضي


    def add_member(self):
        if not self.activation_successful or (self.current_subscription_data and self.current_subscription_data.get("status","").upper() != "ACTIVE"):
            self._show_toast("لا يمكن إضافة أعضاء. البرنامج غير مفعل أو الاشتراك غير نشط.", type="error")
            return

        dialog = AddMemberDialog(self)
        if dialog.exec_() == AddMemberDialog.Accepted:
            data = dialog.get_data()
            # التحقق من صحة البيانات المدخلة
            if not (data["nin"] and data["wassit_no"] and data["ccp"]):
                self._show_toast("يرجى ملء حقول رقم التعريف، رقم الوسيط، والحساب البريدي.", type="warning")
                return
            if len(data["nin"]) != 18:
                self._show_toast("رقم التعريف الوطني يجب أن يتكون من 18 رقمًا.", type="error")
                return
            if len(data["ccp"]) != 12: # CCP هو 10 أرقام + مفتاح رقمين
                self._show_toast("رقم الحساب البريدي يجب أن يتكون من 12 رقمًا (10 للحساب + 2 للمفتاح).", type="error")
                return

            # التحقق من عدم تكرار العضو
            for idx, m in enumerate(self.members_list):
                if m.nin == data["nin"] or m.wassit_no == data["wassit_no"]:
                    member_name_display = self._get_member_display_name_with_index(m, idx)
                    msg = f"العضو '{member_name_display}' موجود بالفعل ببيانات مشابهة."
                    self._show_toast(msg, type="warning")
                    logger.warning(f"محاولة إضافة عضو مكرر: {data['nin']}/{data['wassit_no']} - {msg}")
                    return

            member = Member(data["nin"], data["wassit_no"], data["ccp"], data["phone_number"])
            self.members_list.append(member)

            if self.is_filter_active: # إذا كان الفلتر نشطًا، أعد تطبيقه
                self.apply_filter_and_search()
            else: # إذا لم يكن الفلتر نشطًا، قم بتحديث الجدول مباشرة
                self.update_table()

            current_original_index = self.members_list.index(member) # الحصول على الفهرس الأصلي للعضو الجديد
            member_display_name_add = self._get_member_display_name_with_index(member, current_original_index)
            logger.info(f"تمت إضافة العضو: {member_display_name_add}, Phone={data['phone_number']}")
            self.update_status_bar_message(f"تمت إضافة العضو: {member_display_name_add}. جاري جلب المعلومات الأولية...", is_general_message=False)
            self._show_toast(f"تمت إضافة العضو: {member_display_name_add}. جاري جلب المعلومات الأولية...", type="info")

            # بدء خيط جلب المعلومات الأولية للعضو الجديد
            fetch_thread = FetchInitialInfoThread(member, current_original_index, self.api_client, self.settings.copy())
            fetch_thread.update_member_gui_signal.connect(self.update_member_gui_in_table)
            fetch_thread.new_data_fetched_signal.connect(self.update_member_name_in_table)
            fetch_thread.member_processing_started_signal.connect(lambda idx: self.handle_member_processing_signal(idx, True))
            # عند انتهاء جلب المعلومات الأولية، قم بتشغيل الفحص الفوري
            fetch_thread.member_processing_finished_signal.connect(
                lambda idx, new_member_original_idx=current_original_index: self._trigger_auto_check_after_add(new_member_original_idx)
            )
            self.initial_fetch_threads.append(fetch_thread)
            fetch_thread.start()

    def _trigger_auto_check_after_add(self, original_member_index):
        """
        يتم استدعاؤها بعد انتهاء FetchInitialInfoThread للعضو المضاف حديثًا.
        تقوم ببدء فحص فوري (SingleMemberCheckThread) للعضو.
        """
        if 0 <= original_member_index < len(self.members_list):
            member = self.members_list[original_member_index]
            member_display_name = self._get_member_display_name_with_index(member, original_member_index)
            logger.info(f"اكتمل جلب المعلومات الأولية للعضو {member_display_name}. بدء الفحص التلقائي الفوري...")
            self._show_toast(f"بدء الفحص التلقائي الفوري للعضو {member_display_name}.", type="info")
            self.check_member_now(original_member_index) # استدعاء وظيفة الفحص الفوري
        else:
            logger.warning(f"_trigger_auto_check_after_add: فهرس خاطئ {original_member_index}")


    def edit_member_details(self, item):
        if not self.activation_successful or (self.current_subscription_data and self.current_subscription_data.get("status","").upper() != "ACTIVE"):
            self._show_toast("لا يمكن تعديل الأعضاء. البرنامج غير مفعل أو الاشتراك غير نشط.", type="error")
            return

        row_in_table = -1
        if not item: # إذا تم استدعاء الوظيفة بدون عنصر (مثلاً من قائمة السياق بدون نقر مزدوج)
            selected_rows = self.table.selectionModel().selectedRows()
            if not selected_rows: return # لا يوجد تحديد
            row_in_table = selected_rows[0].row() # استخدام أول صف محدد
        else:
            row_in_table = item.row() # استخدام صف العنصر المنقور عليه

        current_list_for_edit = self.filtered_members_list if self.is_filter_active else self.members_list
        if not (0 <= row_in_table < len(current_list_for_edit)): return # تحقق من الحدود

        member_to_edit_from_display = current_list_for_edit[row_in_table]
        try:
            original_member_index = self.members_list.index(member_to_edit_from_display) # الحصول على الفهرس الأصلي
            member_to_edit = self.members_list[original_member_index] # الحصول على الكائن الفعلي من القائمة الرئيسية
        except ValueError:
            member_display_name_err = self._get_member_display_name_with_index(member_to_edit_from_display, -1)
            logger.error(f"فشل العثور على العضو {member_display_name_err} في القائمة الرئيسية عند التعديل.")
            self._show_toast(f"خطأ: فشل العثور على العضو {member_display_name_err} للتعديل.", type="error")
            return

        member_display_name_edit_title = self._get_member_display_name_with_index(member_to_edit, original_member_index)
        dialog = EditMemberDialog(member_to_edit, self)
        if dialog.exec_() == EditMemberDialog.Accepted:
            new_data = dialog.get_data()
            if not (new_data["nin"] and new_data["wassit_no"] and new_data["ccp"]):
                self._show_toast("يرجى ملء حقول رقم التعريف، رقم الوسيط، والحساب البريدي.", type="warning")
                return
            if len(new_data["nin"]) != 18:
                self._show_toast("رقم التعريف الوطني يجب أن يتكون من 18 رقمًا.", type="error")
                return
            if len(new_data["ccp"]) != 12:
                self._show_toast("رقم الحساب البريدي يجب أن يتكون من 12 رقمًا (10 للحساب + 2 للمفتاح).", type="error")
                return

            nin_changed = member_to_edit.nin != new_data["nin"]
            wassit_changed = member_to_edit.wassit_no != new_data["wassit_no"]

            # التحقق من التكرار إذا تم تغيير NIN أو Wassit
            if nin_changed or wassit_changed:
                for idx, m in enumerate(self.members_list):
                    if idx == original_member_index: # تخطي العضو الحالي
                        continue
                    if m.nin == new_data["nin"] or m.wassit_no == new_data["wassit_no"]:
                        conflicting_member_display = self._get_member_display_name_with_index(m, idx)
                        self._show_toast(f"البيانات الجديدة (NIN أو رقم الوسيط) تتعارض مع العضو '{conflicting_member_display}'. لم يتم الحفظ.", type="error")
                        logger.warning(f"فشل تعديل العضو {member_display_name_edit_title} بسبب تكرار مع {conflicting_member_display}")
                        return

            # تحديث بيانات العضو
            member_to_edit.nin = new_data["nin"]
            member_to_edit.wassit_no = new_data["wassit_no"]
            member_to_edit.ccp = new_data["ccp"]
            member_to_edit.phone_number = new_data["phone_number"]

            member_display_after_edit = self._get_member_display_name_with_index(member_to_edit, original_member_index)

            if nin_changed or wassit_changed: # إذا تم تغيير المعرفات الرئيسية
                logger.info(f"تم تغيير المعرفات الرئيسية للعضو {member_display_after_edit}. إعادة تعيين الحالة وجلب المعلومات.")
                # إعادة تعيين حالة العضو ومعلوماته
                member_to_edit.status = "جديد" # أو أي حالة أولية مناسبة
                member_to_edit.set_activity_detail("تم تعديل المعرفات، يتطلب إعادة التحقق.")
                member_to_edit.nom_fr = ""
                member_to_edit.prenom_fr = ""
                member_to_edit.nom_ar = ""
                member_to_edit.prenom_ar = ""
                member_to_edit.pre_inscription_id = None
                member_to_edit.demandeur_id = None
                member_to_edit.structure_id = None
                member_to_edit.rdv_date = None
                member_to_edit.rdv_id = None
                member_to_edit.rdv_source = None
                member_to_edit.pdf_honneur_path = None
                member_to_edit.pdf_rdv_path = None
                member_to_edit.has_actual_pre_inscription = False
                member_to_edit.already_has_rdv = False
                member_to_edit.consecutive_failures = 0
                member_to_edit.is_processing = False # ضمان أنه ليس قيد المعالجة
                member_to_edit.have_allocation = False
                member_to_edit.allocation_details = {}

                if self.is_filter_active: self.apply_filter_and_search()
                else: self.update_table_row(original_member_index, member_to_edit) # تحديث الصف في الجدول

                self.update_status_bar_message(f"تم تعديل بيانات العضو {member_display_after_edit}. جاري إعادة جلب المعلومات...", is_general_message=False)
                self._show_toast(f"تم تعديل بيانات العضو {member_display_after_edit}. جاري إعادة جلب المعلومات...", type="info")

                # بدء خيط جلب المعلومات الأولية من جديد
                fetch_thread = FetchInitialInfoThread(member_to_edit, original_member_index, self.api_client, self.settings.copy())
                fetch_thread.update_member_gui_signal.connect(self.update_member_gui_in_table)
                fetch_thread.new_data_fetched_signal.connect(self.update_member_name_in_table)
                fetch_thread.member_processing_started_signal.connect(lambda idx: self.handle_member_processing_signal(idx, True))
                # عند انتهاء جلب المعلومات، قم بتشغيل الفحص الفوري
                fetch_thread.member_processing_finished_signal.connect(
                     lambda idx, edited_member_idx=original_member_index: self._trigger_auto_check_after_add(edited_member_idx)
                )
                self.initial_fetch_threads.append(fetch_thread)
                fetch_thread.start()
            else: # إذا لم يتم تغيير المعرفات الرئيسية
                if self.is_filter_active: self.apply_filter_and_search()
                else: self.update_table_row(original_member_index, member_to_edit) # تحديث الصف في الجدول
                self.update_status_bar_message(f"تم تعديل بيانات العضو: {member_display_after_edit}", is_general_message=True)
                self._show_toast(f"تم تعديل بيانات العضو: {member_display_after_edit}", type="success")

            self.save_members_data() # حفظ التغييرات


    def remove_member(self):
        if not self.activation_successful or (self.current_subscription_data and self.current_subscription_data.get("status","").upper() != "ACTIVE"):
            self._show_toast("لا يمكن حذف الأعضاء. البرنامج غير مفعل أو الاشتراك غير نشط.", type="error")
            return

        selected_rows_in_table = self.table.selectionModel().selectedRows()
        if not selected_rows_in_table:
            self._show_toast("يرجى تحديد عضو واحد على الأقل لحذفه.", type="warning")
            return

        confirm_msg = f"هل أنت متأكد أنك تريد حذف {len(selected_rows_in_table)} عضو/أعضاء محددين؟"
        if len(selected_rows_in_table) == 1: # تخصيص الرسالة إذا كان عضو واحد محدد
            row_in_table = selected_rows_in_table[0].row()
            current_list_for_display = self.filtered_members_list if self.is_filter_active else self.members_list
            if 0 <= row_in_table < len(current_list_for_display):
                member_to_remove_display_obj = current_list_for_display[row_in_table]
                original_idx_for_display_remove = -1
                try:
                    original_idx_for_display_remove = self.members_list.index(member_to_remove_display_obj)
                except ValueError:
                    pass # تجاهل إذا لم يتم العثور عليه (نادر)
                member_to_remove_display_name = self._get_member_display_name_with_index(member_to_remove_display_obj, original_idx_for_display_remove)
                confirm_msg = f"هل أنت متأكد أنك تريد حذف العضو '{member_to_remove_display_name}'؟"


        confirm_delete = QMessageBox.question(self, "تأكيد الحذف", confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm_delete == QMessageBox.No:
            return

        members_to_delete_from_display = [] # قائمة بالأعضاء المراد حذفهم من العرض الحالي
        for index_obj in selected_rows_in_table:
            row_in_table = index_obj.row()
            current_list_for_display = self.filtered_members_list if self.is_filter_active else self.members_list
            if 0 <= row_in_table < len(current_list_for_display):
                members_to_delete_from_display.append(current_list_for_display[row_in_table])

        deleted_count = 0
        for member_to_delete in members_to_delete_from_display:
            if member_to_delete in self.members_list: # التأكد من وجود العضو في القائمة الرئيسية
                original_idx_before_delete = self.members_list.index(member_to_delete)
                deleted_member_display_name = self._get_member_display_name_with_index(member_to_delete, original_idx_before_delete)
                self.members_list.remove(member_to_delete) # الحذف من القائمة الرئيسية
                logger.info(f"تم حذف العضو: {deleted_member_display_name}")
                deleted_count +=1
            else:
                logger.warning(f"محاولة حذف عضو {member_to_delete.nin} غير موجود في القائمة الرئيسية.")

        if self.is_filter_active: # إذا كان الفلتر نشطًا، أعد تطبيقه
            self.apply_filter_and_search()
        else: # إذا لم يكن الفلتر نشطًا، قم بتحديث الجدول مباشرة
            self.update_table()

        if deleted_count > 0:
            self.update_status_bar_message(f"تم حذف {deleted_count} عضو/أعضاء.", is_general_message=True)
            self._show_toast(f"تم حذف {deleted_count} عضو/أعضاء بنجاح.", type="info")

        self.save_members_data() # حفظ التغييرات
        # تحديث فهرس المراقبة إذا لزم الأمر
        if self.monitoring_thread and self.monitoring_thread.current_member_index_to_process >= len(self.members_list):
            self.monitoring_thread.current_member_index_to_process = 0 # أو أي منطق آخر مناسب لإعادة التعيين


    def update_table(self):
        self.table.setRowCount(0) # مسح الجدول قبل إعادة الملء
        list_to_display = self.filtered_members_list if self.is_filter_active else self.members_list
        for row_idx, member_obj in enumerate(list_to_display):
            self.table.insertRow(row_idx)
            self.update_table_row(row_idx, member_obj) # ملء بيانات الصف
        if not self.is_filter_active: # حفظ البيانات فقط عند عرض القائمة الكاملة (تجنب الحفظ المتكرر عند الفلترة)
            self.save_members_data()

    def update_table_row(self, row_in_table, member):
        # أيقونة الحالة
        item_icon = QTableWidgetItem()
        item_icon.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row_in_table, self.COL_ICON, item_icon) # سيتم تحديث الأيقونة لاحقًا

        # الاسم الكامل
        item_full_name_ar = QTableWidgetItem(member.get_full_name_ar())
        item_full_name_ar.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row_in_table, self.COL_FULL_NAME_AR, item_full_name_ar)

        # رقم التعريف الوطني
        item_nin = QTableWidgetItem(member.nin)
        item_nin.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row_in_table, self.COL_NIN, item_nin)

        # رقم الوسيط
        item_wassit = QTableWidgetItem(member.wassit_no)
        item_wassit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row_in_table, self.COL_WASSIT, item_wassit)

        # رقم الحساب البريدي (مع التنسيق)
        ccp_display = member.ccp
        if len(member.ccp) == 12: # تنسيق CCP إذا كان 12 رقمًا
             ccp_display = f"{member.ccp[:10]} {member.ccp[10:]}"
        item_ccp = QTableWidgetItem(ccp_display)
        item_ccp.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row_in_table, self.COL_CCP, item_ccp)

        # رقم الهاتف
        item_phone = QTableWidgetItem(member.phone_number or "") # عرض فارغ إذا لم يكن هناك رقم
        item_phone.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row_in_table, self.COL_PHONE_NUMBER, item_phone)

        # الحالة (سيتم تحديثها مع الأيقونة)
        item_status = QTableWidgetItem()
        item_status.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row_in_table, self.COL_STATUS, item_status)

        # تاريخ الموعد (مع مصدره)
        rdv_date_display_text = member.rdv_date if member.rdv_date else ""
        if member.rdv_date:
            if member.rdv_source == "system":
                rdv_date_display_text += " (نظام)"
            elif member.rdv_source == "discovered":
                rdv_date_display_text += " (مكتشف)"
        item_rdv = QTableWidgetItem(rdv_date_display_text)
        item_rdv.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.table.setItem(row_in_table, self.COL_RDV_DATE, item_rdv)

        # آخر تحديث/خطأ (مع تلميح للتفاصيل الكاملة)
        detail_to_show = member.last_activity_detail # الرسالة المختصرة
        item_details = QTableWidgetItem(detail_to_show)
        item_details.setToolTip(member.full_last_activity_detail) # الرسالة الكاملة كتلميح
        item_details.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row_in_table, self.COL_DETAILS, item_details)

        # تحديث الأيقونة والحالة الفعلية باستخدام update_member_gui_in_table
        try:
            original_member_index = self.members_list.index(member) # الحصول على الفهرس الأصلي
            # استدعاء الوظيفة التي تحدث الأيقونة والحالة بناءً على الفهرس الأصلي
            self.update_member_gui_in_table(original_member_index, member.status, member.last_activity_detail, get_icon_name_for_status(member.status))
        except ValueError: # إذا لم يتم العثور على العضو في القائمة الرئيسية (نادر)
            status_item = self.table.item(row_in_table, self.COL_STATUS)
            if status_item: status_item.setText(member.status)
            icon_item = self.table.item(row_in_table, self.COL_ICON)
            if icon_item:
                qt_icon = self.style().standardIcon(getattr(QStyle, get_icon_name_for_status(member.status), QStyle.SP_CustomBase))
                icon_item.setIcon(qt_icon)
                icon_item.setText("") # إزالة أي نص من خلية الأيقونة


    def update_member_gui_in_table(self, original_member_index, status_text, detail_text, icon_name_str):
        if not (0 <= original_member_index < len(self.members_list)):
            return # الفهرس الأصلي غير صالح

        member = self.members_list[original_member_index] # الحصول على العضو من القائمة الرئيسية

        # البحث عن الصف المقابل في الجدول (قد يكون مفلترًا)
        row_in_table_to_update = -1
        current_list_displayed = self.filtered_members_list if self.is_filter_active else self.members_list
        try:
            row_in_table_to_update = current_list_displayed.index(member)
        except ValueError: # إذا لم يتم العثور على العضو في القائمة المعروضة حاليًا
            return

        if not (0 <= row_in_table_to_update < self.table.rowCount()):
             return # الفهرس المحسوب للجدول خارج الحدود

        # تحديث البيانات الأساسية التي قد تتغير (مثل الاسم بعد الجلب الأولي)
        self.table.item(row_in_table_to_update, self.COL_FULL_NAME_AR).setText(member.get_full_name_ar())
        self.table.item(row_in_table_to_update, self.COL_NIN).setText(member.nin)
        self.table.item(row_in_table_to_update, self.COL_WASSIT).setText(member.wassit_no)
        ccp_display = member.ccp
        if len(member.ccp) == 12: ccp_display = f"{member.ccp[:10]} {member.ccp[10:]}"
        self.table.item(row_in_table_to_update, self.COL_CCP).setText(ccp_display)
        self.table.item(row_in_table_to_update, self.COL_PHONE_NUMBER).setText(member.phone_number or "")

        # تحديث تاريخ الموعد (قد يتغير)
        rdv_date_display_text = member.rdv_date if member.rdv_date else ""
        if member.rdv_date:
            if member.rdv_source == "system":
                rdv_date_display_text += " (نظام)"
            elif member.rdv_source == "discovered":
                rdv_date_display_text += " (مكتشف)"
        self.table.item(row_in_table_to_update, self.COL_RDV_DATE).setText(rdv_date_display_text)

        # تحديث التفاصيل (الرسالة المختصرة والتلميح)
        detail_to_show_gui = member.last_activity_detail # الرسالة المختصرة من الكائن
        self.table.item(row_in_table_to_update, self.COL_DETAILS).setText(detail_to_show_gui)
        self.table.item(row_in_table_to_update, self.COL_DETAILS).setToolTip(member.full_last_activity_detail) # الرسالة الكاملة

        # تحديث الحالة والأيقونة
        icon_item = self.table.item(row_in_table_to_update, self.COL_ICON)
        status_text_item = self.table.item(row_in_table_to_update, self.COL_STATUS)
        status_text_item.setText(status_text) # تحديث نص الحالة

        if icon_item:
            # إذا كان الصف هو الصف النشط للسبينر والعضو قيد المعالجة، لا تغير الأيقونة (دع السبينر يعمل)
            if self.active_spinner_row_in_view == row_in_table_to_update and member.is_processing:
                icon_item.setIcon(QIcon()) # قد يكون النص هو السبينر
            else: # وإلا، قم بتحديث الأيقونة
                qt_icon = self.style().standardIcon(getattr(QStyle, icon_name_str, QStyle.SP_CustomBase))
                icon_item.setIcon(qt_icon)
                icon_item.setText("") # تأكد من إزالة أي نص من خلية الأيقونة

        # تحديث لون خلفية الصف
        self.highlight_processing_row(row_in_table_to_update, force_processing_display=None)

        # منطق التوست (مع التحقق من suppress_initial_messages)
        msg_attr_prefix = f"_toast_shown_{original_member_index}_" # بادئة لأسماء متغيرات التوست
        if not self.suppress_initial_messages: # فقط إذا لم يتم كبت الرسائل الأولية
            current_status_for_toast = status_text # الحالة الحالية للتوست

            # إذا كانت الحالة تشير إلى خطأ
            if "فشل" in current_status_for_toast or "خطأ" in current_status_for_toast or "غير مؤهل" in current_status_for_toast:
                error_attr = msg_attr_prefix + current_status_for_toast.replace(" ", "_") # اسم متغير فريد للخطأ
                if not hasattr(self, error_attr) or not getattr(self, error_attr): # إذا لم يتم عرض هذا الخطأ من قبل
                    self._show_toast(f"{member.full_last_activity_detail}", type="error", duration=5000, member_obj=member, original_idx_if_member=original_member_index)
                    setattr(self, error_attr, True) # وضع علامة بأنه تم عرضه
                    # مسح علامات التوستات الأخرى لهذا العضو
                    for attr_suffix in ["input_error", "has_rdv", "booking_ineligible", "completed_or_benefiting", "success_generic"]:
                        if hasattr(self, msg_attr_prefix + attr_suffix):
                            delattr(self, msg_attr_prefix + attr_suffix)
            # إذا كانت الحالة تشير إلى نجاح
            elif current_status_for_toast == "مكتمل" or current_status_for_toast == "مستفيد حاليًا من المنحة" or current_status_for_toast == "تم الحجز":
                success_attr = msg_attr_prefix + "success_generic" # اسم متغير فريد للنجاح
                if not hasattr(self, success_attr) or not getattr(self, success_attr): # إذا لم يتم عرض هذا النجاح من قبل
                    self._show_toast(f"{detail_text}", type="success", duration=5000, member_obj=member, original_idx_if_member=original_member_index)
                    setattr(self, success_attr, True) # وضع علامة بأنه تم عرضه
                    # مسح علامات التوستات الأخرى
                    for attr_suffix in ["input_error", "has_rdv", "booking_ineligible", "error_generic"]:
                         if hasattr(self, msg_attr_prefix + attr_suffix):
                            delattr(self, msg_attr_prefix + attr_suffix)
            else: # للحالات الأخرى، قم بمسح جميع علامات التوست السابقة لهذا العضو
                for attr_suffix in ["input_error", "has_rdv", "booking_ineligible", "completed_or_benefiting", "success_generic", "error_generic"] + [current_status_for_toast.replace(" ", "_")]:
                    if hasattr(self, msg_attr_prefix + attr_suffix):
                        delattr(self, msg_attr_prefix + attr_suffix)


    def update_member_name_in_table(self, original_member_index, nom_ar, prenom_ar):
        if 0 <= original_member_index < len(self.members_list):
            member = self.members_list[original_member_index]
            member.nom_ar = nom_ar
            member.prenom_ar = prenom_ar

            # البحث عن الصف المقابل في الجدول (قد يكون مفلترًا)
            row_in_table_to_update = -1
            current_list_displayed = self.filtered_members_list if self.is_filter_active else self.members_list
            try:
                row_in_table_to_update = current_list_displayed.index(member)
                if 0 <= row_in_table_to_update < self.table.rowCount():
                    full_name_item = self.table.item(row_in_table_to_update, self.COL_FULL_NAME_AR)
                    if full_name_item:
                        full_name_item.setText(member.get_full_name_ar()) # تحديث الاسم في الجدول
                    if not self.suppress_initial_messages: # عرض توست إذا لم يتم كبت الرسائل
                        self._show_toast(f"تم تحديث اسم العضو.", type="info", member_obj=member, original_idx_if_member=original_member_index)
            except ValueError: # إذا لم يتم العثور على العضو في القائمة المعروضة
                pass # لا تفعل شيئًا، سيتم تحديثه عند إعادة رسم الجدول بالكامل
            self.save_members_data() # حفظ البيانات بعد تحديث الاسم


    def update_status_bar_message(self, message, is_general_message=True, member_obj=None, original_idx_if_member=None):
        final_message = message
        if member_obj and original_idx_if_member is not None and original_idx_if_member >= 0:
            member_display = self._get_member_display_name_with_index(member_obj, original_idx_if_member)
            final_message = f"{member_display}: {message}"

        if hasattr(self, 'status_bar_label'): # تأكد من وجود الشريط
            self.status_bar_label.setText(final_message)

        if hasattr(self, 'last_scan_label'): # تأكد من وجود ملصق آخر مسح
            # تحديث وقت آخر مسح لبعض الرسائل المحددة أو إذا لم تكن رسالة عامة
            if not is_general_message or "انتهاء دورة الفحص" in message or "بدء دورة فحص جديدة" in message or "استئناف المراقبة" in message or "الموقع لا يزال غير متاح" in message or "اكتمل الفحص الأولي" in message:
                self.last_scan_label.setText(f"آخر تحديث: {time.strftime('%H:%M:%S')}")
            elif is_general_message: # مسح وقت آخر مسح للرسائل العامة
                self.last_scan_label.setText("")

        if hasattr(self, 'countdown_label'): # مسح العد التنازلي إذا كانت رسالة عامة ولم يتم تحديث آخر مسح
            if is_general_message and hasattr(self, 'last_scan_label') and self.last_scan_label.text() == "":
                 self.countdown_label.setText("")


    def update_countdown_timer_display(self, time_remaining_str):
        if hasattr(self, 'countdown_label'): # تأكد من وجود الملصق
            self.countdown_label.setText(time_remaining_str)


    def start_monitoring(self):
        if not self.activation_successful or not self.current_subscription_data or self.current_subscription_data.get("status","").upper() != "ACTIVE":
            self._show_toast("لا يمكن بدء المراقبة. البرنامج غير مفعل أو الاشتراك غير نشط.", type="error")
            return

        if not self.members_list:
            self._show_toast("يرجى إضافة أعضاء أولاً لبدء المراقبة.", type="warning")
            return
        if not self.monitoring_thread.isRunning():
            logger.info("بدء المراقبة...")
            self.monitoring_thread.members_list_ref = self.members_list # تحديث مرجع قائمة الأعضاء
            self.monitoring_thread.is_running = True
            self.monitoring_thread.is_connection_lost_mode = False # إعادة التعيين عند البدء
            self.monitoring_thread.current_member_index_to_process = 0 # البدء من الأول
            self.monitoring_thread.consecutive_network_error_trigger_count = 0 # إعادة التعيين
            self.monitoring_thread.update_thread_settings(self.settings.copy()) # تطبيق الإعدادات الحالية
            self.monitoring_thread.start()
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.add_member_button.setEnabled(False) # تعطيل الإضافة أثناء المراقبة
            self.remove_member_button.setEnabled(False) # تعطيل الحذف أثناء المراقبة
            monitoring_interval_minutes = self.settings.get(SETTING_MONITORING_INTERVAL, DEFAULT_SETTINGS[SETTING_MONITORING_INTERVAL])
            self.update_status_bar_message(f"بدأت المراقبة (الدورة كل {monitoring_interval_minutes} دقيقة)...", is_general_message=False)
            self._show_toast(f"بدأت المراقبة (الدورة كل {monitoring_interval_minutes} دقيقة).", type="info")
        else:
            self._show_toast("المراقبة جارية بالفعل.", type="info")
            self.update_status_bar_message("المراقبة جارية بالفعل.", is_general_message=True)


    def stop_monitoring(self):
        if self.monitoring_thread.isRunning():
            logger.info("تم طلب إيقاف المراقبة.")
            self.monitoring_thread.stop_monitoring() # إرسال إشارة الإيقاف للخيط
            # إيقاف مؤقت السبينر إذا كان نشطًا وتحديث واجهة المستخدم للصف النشط
            if self.row_spinner_timer.isActive():
                self.row_spinner_timer.stop()
                if self.active_spinner_row_in_view != -1 and self.active_spinner_row_in_view < self.table.rowCount():
                    current_list_displayed = self.filtered_members_list if self.is_filter_active else self.members_list
                    if self.active_spinner_row_in_view < len(current_list_displayed):
                        member_at_spinner = current_list_displayed[self.active_spinner_row_in_view]
                        try:
                            original_member_index = self.members_list.index(member_at_spinner)
                            if 0 <= original_member_index < len(self.members_list):
                                member = self.members_list[original_member_index]
                                member.is_processing = False # ضمان أن الحالة ليست قيد المعالجة
                                self.update_member_gui_in_table(original_member_index, member.status, member.last_activity_detail, get_icon_name_for_status(member.status))
                        except ValueError:
                             pass # تجاهل إذا لم يتم العثور عليه
                self.active_spinner_row_in_view = -1 # إعادة تعيين الصف النشط للسبينر

            # تمكين/تعطيل الأزرار بناءً على حالة التفعيل
            if self.activation_successful and self.current_subscription_data and self.current_subscription_data.get("status","").upper() == "ACTIVE":
                self._enable_app_functions() # تمكين الوظائف إذا كان الاشتراك لا يزال نشطًا
            else:
                self._disable_app_functions() # تعطيل إذا لم يكن كذلك
                self.stop_button.setEnabled(False) # زر الإيقاف يجب أن يكون معطلاً دائمًا عند الإيقاف

            self.update_status_bar_message("تم إيقاف المراقبة بنجاح.", is_general_message=True)
            self._show_toast("تم إيقاف المراقبة.", type="info")
            self.update_countdown_timer_display("") # مسح العد التنازلي
            # التأكد من أن جميع الأعضاء ليسوا في حالة "is_processing"
            for i in range(len(self.members_list)):
                if self.members_list[i].is_processing:
                    self.members_list[i].is_processing = False
                    self.update_member_gui_in_table(i, self.members_list[i].status, self.members_list[i].last_activity_detail, get_icon_name_for_status(self.members_list[i].status))
        else:
            self._show_toast("المراقبة ليست جارية حاليًا.", type="info")
            self.update_status_bar_message("المراقبة ليست جارية.", is_general_message=True)


    def load_members_data(self):
        self.suppress_initial_messages = True # كبت رسائل التوست أثناء التحميل الأولي
        loaded_successfully = False
        primary_path = DATA_FILE # المسار من config.py
        backup_path = DATA_FILE_BAK # المسار من config.py

        if os.path.exists(primary_path):
            try:
                with open(primary_path, 'r', encoding='utf-8') as f:
                    data_list = json.load(f)
                    self.members_list = [Member.from_dict(data) for data in data_list]
                    for member in self.members_list: # ضمان أن is_processing هي False عند التحميل
                        member.is_processing = False
                    loaded_successfully = True
                    logger.info(f"تم تحميل بيانات {len(self.members_list)} أعضاء من {primary_path}")
            except json.JSONDecodeError:
                logger.error(f"خطأ في فك تشفير JSON للملف الأساسي {primary_path}. محاولة تحميل النسخة الاحتياطية.")
            except Exception as e:
                logger.exception(f"خطأ غير متوقع عند تحميل البيانات من {primary_path}: {e}")
        else:
            logger.info(f"الملف الأساسي {primary_path} غير موجود. محاولة تحميل النسخة الاحتياطية.")

        if not loaded_successfully and os.path.exists(backup_path): # إذا فشل التحميل من الأساسي أو لم يكن موجودًا
            try:
                with open(backup_path, 'r', encoding='utf-8') as f:
                    data_list = json.load(f)
                    self.members_list = [Member.from_dict(data) for data in data_list]
                    for member in self.members_list: # ضمان أن is_processing هي False
                        member.is_processing = False
                    loaded_successfully = True
                    logger.info(f"تم تحميل بيانات {len(self.members_list)} أعضاء من الملف الاحتياطي {backup_path}")
                    self.update_status_bar_message(f"تم استعادة البيانات من النسخة الاحتياطية.", is_general_message=True)
                    self._show_toast(f"تم استعادة بيانات الأعضاء من نسخة احتياطية: {backup_path}", type="info", duration=5000)
                    # محاولة استعادة الملف الأساسي من النسخة الاحتياطية
                    try:
                        shutil.copy2(backup_path, primary_path)
                        logger.info(f"تم استعادة الملف الأساسي {primary_path} من النسخة الاحتياطية {backup_path}.")
                    except Exception as e_copy:
                        logger.error(f"فشل في استعادة الملف الأساسي من النسخة الاحتياطية: {e_copy}")
            except json.JSONDecodeError:
                logger.error(f"خطأ في فك تشفير JSON للملف الاحتياطي {backup_path}. قد يكون الملف تالفًا.")
                self.update_status_bar_message(f"خطأ في قراءة ملف البيانات الاحتياطي {backup_path}.", is_general_message=True)
                self._show_toast(f"خطأ في ملف البيانات الاحتياطي {backup_path}. قد يكون الملف تالفًا. تم بدء البرنامج بقائمة فارغة.", type="error", duration=6000)
            except Exception as e:
                logger.exception(f"خطأ غير متوقع عند تحميل البيانات من الملف الاحتياطي {backup_path}: {e}")
                self.update_status_bar_message(f"خطأ غير متوقع عند تحميل البيانات الاحتياطية: {e}", is_general_message=True)
                self._show_toast(f"خطأ غير متوقع عند تحميل البيانات الاحتياطية: {e}", type="error", duration=6000)

        if not loaded_successfully: # إذا فشل التحميل من كلا الملفين
            self.members_list = []
            logger.info(f"لم يتم العثور على ملف البيانات ({primary_path}) أو الملف الاحتياطي ({backup_path})، أو كلاهما تالف. سيبدأ البرنامج بقائمة فارغة.")
            self.update_status_bar_message(f"ملف البيانات غير موجود أو تالف. يمكنك إضافة أعضاء جدد.", is_general_message=True)

        self.filtered_members_list = list(self.members_list) # تهيئة القائمة المفلترة
        self.update_table() # تحديث الجدول بالبيانات المحملة

        # إلغاء كبت رسائل التوست بعد فترة قصيرة للسماح للواجهة بالاستقرار
        QTimer.singleShot(200, lambda: setattr(self, 'suppress_initial_messages', False))


    def save_members_data(self):
        primary_path = DATA_FILE # المسار من config.py
        tmp_path = DATA_FILE_TMP # المسار من config.py
        bak_path = DATA_FILE_BAK # المسار من config.py
        try:
            data_to_save = []
            for member in self.members_list:
                member_dict = member.to_dict()
                member_dict['is_processing'] = False # ضمان أن is_processing لا يتم حفظها كـ True
                data_to_save.append(member_dict)

            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)

            if os.path.exists(primary_path):
                try:
                    shutil.copy2(primary_path, bak_path) # استخدام copy2 للحفاظ على الميتاداتا
                    logger.debug(f"تم إنشاء نسخة احتياطية من {primary_path} إلى {bak_path}")
                except Exception as e_bak:
                    logger.error(f"فشل في إنشاء نسخة احتياطية لملف بيانات الأعضاء {primary_path}: {e_bak}")

            os.replace(tmp_path, primary_path) # استبدال الملف الأساسي بالملف المؤقت
            logger.info(f"تم حفظ بيانات الأعضاء بنجاح في {primary_path}")

        except Exception as e:
            logger.exception(f"خطأ عند حفظ بيانات الأعضاء في {primary_path}: {e}")
            self.update_status_bar_message(f"خطأ عند حفظ البيانات: {e}", is_general_message=True)
            self._show_toast(f"فشل حفظ بيانات الأعضاء: {e}", type="error")
            if os.path.exists(tmp_path): # محاولة حذف الملف المؤقت إذا كان لا يزال موجودًا
                try:
                    os.remove(tmp_path)
                except Exception as e_del_tmp:
                    logger.error(f"فشل في حذف الملف المؤقت لبيانات الأعضاء {tmp_path} بعد خطأ في الحفظ: {e_del_tmp}")


    def closeEvent(self, event):
        logger.info("إغلاق التطبيق...")
        self.update_status_bar_message("جاري إغلاق التطبيق...", is_general_message=True)

        # إيقاف خيط التفعيل إذا كان يعمل
        if self.activation_thread and self.activation_thread.isRunning():
            logger.info("Stopping active activation thread before closing...")
            self.activation_thread.stop()
            self.activation_thread.wait(1500) # انتظار حتى 1.5 ثانية

        # إيقاف مستمع تحديثات الاشتراك
        if self.activated_code_id and self.firebase_service and self.firebase_service.is_initialized():
            logger.info(f"AnemApp: Stopping listener for activation code {self.activated_code_id} before closing.")
            self.firebase_service.stop_listening_to_code_changes(self.activated_code_id)

        # إيقاف خيط المراقبة
        if self.monitoring_thread.isRunning():
            logger.info("إيقاف المراقبة قبل الإغلاق...")
            self.monitoring_thread.stop_monitoring()
            if not self.monitoring_thread.wait(3000): # انتظار حتى 3 ثواني
                logger.warning("خيط المراقبة لم ينتهِ في الوقت المناسب.")

        # حفظ البيانات والإعدادات
        self.save_members_data()
        self.save_app_settings()

        # إيقاف الخيوط الأخرى
        for thread in self.initial_fetch_threads:
            if thread.isRunning():
                thread.quit() # طلب إنهاء الخيط
                if not thread.wait(2000): # انتظار حتى ثانيتين
                    logger.warning(f"الخيط {thread} لم ينتهِ في الوقت المناسب عند الإغلاق.")

        if self.single_check_thread and self.single_check_thread.isRunning():
            self.single_check_thread.quit()
            if not self.single_check_thread.wait(1000): # انتظار ثانية واحدة
                 logger.warning("خيط الفحص الفردي لم ينته في الوقت المناسب.")

        active_pdf_dl_threads_copy = list(self.active_download_all_pdfs_threads.values()) # نسخة لتجنب التعديل أثناء التكرار
        if active_pdf_dl_threads_copy:
            for pdf_thread in active_pdf_dl_threads_copy:
                if pdf_thread.isRunning():
                    pdf_thread.stop() # استخدام stop إذا كانت الطريقة مخصصة للإيقاف الآمن
                    if not pdf_thread.wait(2000): # انتظار ثانيتين
                        logger.warning(f"خيط تحميل جميع ملفات PDF {pdf_thread} لم ينتهِ في الوقت المناسب.")
            self.active_download_all_pdfs_threads.clear() # مسح القاموس

        # إيقاف المؤقتات
        if hasattr(self, 'datetime_timer') and self.datetime_timer.isActive(): self.datetime_timer.stop()
        if hasattr(self, 'row_spinner_timer') and self.row_spinner_timer.isActive(): self.row_spinner_timer.stop()
        logger.info("تم إغلاق التطبيق.")
        super().closeEvent(event)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = AnemApp()

    # التحقق إذا كان يجب إظهار الواجهة الرئيسية
    # _should_initialize_ui يتم تعيينه بعد _initialize_and_check_activation
    # و _initialize_and_check_activation يعتمد على self.activation_successful
    if not main_window.activation_successful or not main_window._should_initialize_ui:
        logger.critical("__main__: Activation failed or UI should not be initialized. Application will exit.")
        # لا حاجة لـ sys.exit(1) هنا لأن البرنامج سينتهي بشكل طبيعي إذا لم يتم إظهار النافذة
        # أو يمكن إضافته إذا كنت تريد رمز خروج محدد للفشل
    else:
        main_window.show()
        sys.exit(app.exec_())
