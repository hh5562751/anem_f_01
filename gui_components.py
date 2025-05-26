# gui_components.py (User App - Updated Dialogs V2 - Enhanced ActivationDialog UI)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QDialog, QFormLayout, QDialogButtonBox,
    QSpinBox, QStyle, QApplication, QDesktopWidget, QTextEdit,
    QScrollArea, QFrame,QSizePolicy, QGridLayout, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QEasingCurve, QPropertyAnimation, QRegularExpression, pyqtSignal, QDateTime
from PyQt5.QtGui import QIcon, QRegularExpressionValidator, QColor, QPixmap, QFont

from utils import QColorConstants # Assuming utils.py is available and contains QColorConstants
import datetime # Ensure datetime is imported for type checking


class ToastNotification(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.ToolTip | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)

        self.background_widget = QWidget(self)
        self.background_widget.setObjectName("toastBackground")

        toast_layout = QHBoxLayout(self.background_widget)
        toast_layout.setContentsMargins(10, 8, 10, 8)
        toast_layout.setSpacing(8)

        self.icon_label = QLabel(self.background_widget)
        self.icon_label.setObjectName("toastIconLabel")
        toast_layout.addWidget(self.icon_label)

        self.message_label = QLabel(self.background_widget)
        self.message_label.setObjectName("toastMessageLabel")
        self.message_label.setWordWrap(True)
        toast_layout.addWidget(self.message_label)

        self.layout.addWidget(self.background_widget)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._start_fade_out)

        self.animation = QPropertyAnimation(self, b"windowOpacity", self)
        self.animation.setDuration(500)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.finished.connect(self._on_animation_finished)

    def _on_animation_finished(self):
        if self.windowOpacity() == 0:
            self.hide()

    def _start_fade_out(self):
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.start()

    def showMessage(self, message, type="info", duration=4000, parent_window=None):
        self.message_label.setText(message)
        self.setWindowOpacity(0.0)

        self.background_widget.setProperty("toastType", type)
        self.message_label.setProperty("toastType", type)
        self.icon_label.setProperty("toastType", type)

        self.style().unpolish(self.background_widget)
        self.style().polish(self.background_widget)
        self.style().unpolish(self.message_label)
        self.style().polish(self.message_label)
        self.style().unpolish(self.icon_label)
        self.style().polish(self.icon_label)
        
        icon = QIcon()
        if type == "error":
            icon = self.style().standardIcon(QStyle.SP_MessageBoxCritical)
        elif type == "warning":
            icon = self.style().standardIcon(QStyle.SP_MessageBoxWarning)
        elif type == "success":
            icon = self.style().standardIcon(QStyle.SP_DialogApplyButton)
        else:
            icon = self.style().standardIcon(QStyle.SP_MessageBoxInformation)
        
        self.icon_label.setPixmap(icon.pixmap(24, 24))

        self.adjustSize()

        if parent_window:
            parent_geo = parent_window.geometry()
            screen_geo = QApplication.desktop().availableGeometry(parent_window)

            pos_x = parent_geo.left() + 15
            pos_y = parent_geo.bottom() - self.height() - 15
            
            if pos_x + self.width() > screen_geo.right() - 10:
                 pos_x = screen_geo.right() - self.width() - 10
            
            if pos_y + self.height() > screen_geo.bottom() - 40 or \
               parent_window.isMinimized() or parent_geo.width() < 200 or parent_geo.height() < 100:
                
                pos_x = screen_geo.left() + 20
                if pos_x + self.width() > screen_geo.right() - 20 :
                     pos_x = screen_geo.right() - self.width() - 20
                pos_y = screen_geo.bottom() - self.height() - 50
            
            self.move(QPoint(int(pos_x), int(pos_y)))
        else:
            screen_geo = QApplication.desktop().availableGeometry()
            self.move(screen_geo.width() - self.width() - 20, screen_geo.height() - self.height() - 50)

        self.show()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()
        self.timer.start(duration)


class AddMemberDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إضافة عضو جديد")
        self.setModal(True)
        self.setLayoutDirection(Qt.RightToLeft)
        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)

        self.nin_input = QLineEdit(self)
        self.nin_input.setMaxLength(18)
        self.nin_input.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]{1,18}")))

        self.wassit_no_input = QLineEdit(self)
        self.ccp_input = QLineEdit(self)
        self.ccp_input.setMaxLength(13)
        self.ccp_input.textChanged.connect(self.format_ccp_input)

        self.phone_number_input = QLineEdit(self)
        self.phone_number_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9\s\+\-\(\)]{0,20}$")))
        self.phone_number_input.setMaxLength(20)


        layout.addRow("رقم التعريف الوطني (NIN):", self.nin_input)
        layout.addRow("رقم طالب الشغل (الوسيط):", self.wassit_no_input)
        layout.addRow("رقم الحساب البريدي (CCP):", self.ccp_input)
        layout.addRow("رقم الهاتف:", self.phone_number_input)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Ok).setText("إضافة")
        self.buttons.button(QDialogButtonBox.Cancel).setText("إلغاء")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def format_ccp_input(self, text):
        cleaned_text = ''.join(filter(str.isdigit, text))
        if len(cleaned_text) > 12:
            cleaned_text = cleaned_text[:12]
        if len(cleaned_text) > 10:
            formatted_text = f"{cleaned_text[:10]} {cleaned_text[10:]}"
        else:
            formatted_text = cleaned_text
        self.ccp_input.blockSignals(True)
        self.ccp_input.setText(formatted_text)
        self.ccp_input.setCursorPosition(len(formatted_text))
        self.ccp_input.blockSignals(False)

    def get_data(self):
        ccp_raw = self.ccp_input.text().replace(" ", "")
        return {
            "nin": self.nin_input.text().strip(),
            "wassit_no": self.wassit_no_input.text().strip(),
            "ccp": ccp_raw,
            "phone_number": self.phone_number_input.text().strip()
        }

class EditMemberDialog(QDialog):
    def __init__(self, member, parent=None):
        super().__init__(parent)
        self.member = member
        self.setWindowTitle(f"تعديل بيانات العضو: {member.get_full_name_ar() or member.nin}".strip())
        self.setModal(True)
        self.setMinimumWidth(450)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)

        self.full_name_label = QLabel(f"<b>الاسم الكامل:</b> {member.get_full_name_ar() or '(غير متوفر بعد)'}", self)
        layout.addRow(self.full_name_label)

        self.nin_input = QLineEdit(member.nin, self)
        self.nin_input.setMaxLength(18)
        self.nin_input.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]{1,18}")))

        self.wassit_no_input = QLineEdit(member.wassit_no, self)
        self.ccp_input = QLineEdit(self)
        self.ccp_input.setMaxLength(13)
        self.ccp_input.textChanged.connect(self.format_ccp_input_edit)
        self.format_ccp_input_edit(member.ccp)

        self.phone_number_input = QLineEdit(member.phone_number, self)
        self.phone_number_input.setValidator(QRegularExpressionValidator(QRegularExpression(r"^[0-9\s\+\-\(\)]{0,20}$")))
        self.phone_number_input.setMaxLength(20)

        layout.addRow("رقم التعريف الوطني (NIN):", self.nin_input)
        layout.addRow("رقم طالب الشغل (الوسيط):", self.wassit_no_input)
        layout.addRow("رقم الحساب البريدي (CCP):", self.ccp_input)
        layout.addRow("رقم الهاتف:", self.phone_number_input)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Save).setText("حفظ")
        self.buttons.button(QDialogButtonBox.Cancel).setText("إلغاء")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def format_ccp_input_edit(self, text):
        cleaned_text = ''.join(filter(str.isdigit, text))
        if len(cleaned_text) > 12:
            cleaned_text = cleaned_text[:12]
        if len(cleaned_text) > 10:
            formatted_text = f"{cleaned_text[:10]} {cleaned_text[10:]}"
        else:
            formatted_text = cleaned_text
        
        current_cursor_pos = self.ccp_input.cursorPosition()
        self.ccp_input.blockSignals(True)
        self.ccp_input.setText(formatted_text)
        if len(text) == len(formatted_text):
            self.ccp_input.setCursorPosition(current_cursor_pos)
        else:
            self.ccp_input.setCursorPosition(len(formatted_text))
        self.ccp_input.blockSignals(False)


    def get_data(self):
        ccp_raw = self.ccp_input.text().replace(" ", "")
        return {
            "nin": self.nin_input.text().strip(),
            "wassit_no": self.wassit_no_input.text().strip(),
            "ccp": ccp_raw,
            "phone_number": self.phone_number_input.text().strip()
        }

class SettingsDialog(QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إعدادات التطبيق")
        self.setModal(True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(400)

        from config import ( 
            SETTING_MIN_MEMBER_DELAY, SETTING_MAX_MEMBER_DELAY,
            SETTING_MONITORING_INTERVAL, SETTING_BACKOFF_429,
            SETTING_BACKOFF_GENERAL, SETTING_REQUEST_TIMEOUT, DEFAULT_SETTINGS
        )

        self.current_settings = current_settings
        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)

        self.min_delay_spin = QSpinBox(self)
        self.min_delay_spin.setRange(1, 300)
        self.min_delay_spin.setValue(self.current_settings.get(SETTING_MIN_MEMBER_DELAY, DEFAULT_SETTINGS[SETTING_MIN_MEMBER_DELAY]))
        self.min_delay_spin.setSuffix(" ثانية")

        self.max_delay_spin = QSpinBox(self)
        self.max_delay_spin.setRange(1, 600)
        self.max_delay_spin.setValue(self.current_settings.get(SETTING_MAX_MEMBER_DELAY, DEFAULT_SETTINGS[SETTING_MAX_MEMBER_DELAY]))
        self.max_delay_spin.setSuffix(" ثانية")

        self.monitoring_interval_spin = QSpinBox(self)
        self.monitoring_interval_spin.setRange(1, 120)
        self.monitoring_interval_spin.setValue(self.current_settings.get(SETTING_MONITORING_INTERVAL, DEFAULT_SETTINGS[SETTING_MONITORING_INTERVAL]))
        self.monitoring_interval_spin.setSuffix(" دقيقة")

        self.backoff_429_spin = QSpinBox(self)
        self.backoff_429_spin.setRange(10, 3600)
        self.backoff_429_spin.setValue(self.current_settings.get(SETTING_BACKOFF_429, DEFAULT_SETTINGS[SETTING_BACKOFF_429]))
        self.backoff_429_spin.setSuffix(" ثانية")

        self.backoff_general_spin = QSpinBox(self)
        self.backoff_general_spin.setRange(1, 300)
        self.backoff_general_spin.setValue(self.current_settings.get(SETTING_BACKOFF_GENERAL, DEFAULT_SETTINGS[SETTING_BACKOFF_GENERAL]))
        self.backoff_general_spin.setSuffix(" ثانية")
        
        self.request_timeout_spin = QSpinBox(self)
        self.request_timeout_spin.setRange(5, 120)
        self.request_timeout_spin.setValue(self.current_settings.get(SETTING_REQUEST_TIMEOUT, DEFAULT_SETTINGS[SETTING_REQUEST_TIMEOUT]))
        self.request_timeout_spin.setSuffix(" ثانية")


        layout.addRow("أقل تأخير بين الأعضاء:", self.min_delay_spin)
        layout.addRow("أقصى تأخير بين الأعضاء:", self.max_delay_spin)
        layout.addRow("الفاصل الزمني لدورة المراقبة:", self.monitoring_interval_spin)
        layout.addRow("تأخير أولي لخطأ 429 (طلبات كثيرة):", self.backoff_429_spin)
        layout.addRow("تأخير أولي للأخطاء العامة:", self.backoff_general_spin)
        layout.addRow("مهلة الطلب للواجهة البرمجية (API):", self.request_timeout_spin)


        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttons.button(QDialogButtonBox.Save).setText("حفظ الإعدادات")
        self.buttons.button(QDialogButtonBox.Cancel).setText("إلغاء")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)

    def get_settings(self):
        from config import ( 
            SETTING_MIN_MEMBER_DELAY, SETTING_MAX_MEMBER_DELAY,
            SETTING_MONITORING_INTERVAL, SETTING_BACKOFF_429,
            SETTING_BACKOFF_GENERAL, SETTING_REQUEST_TIMEOUT
        )
        min_val = self.min_delay_spin.value()
        max_val = self.max_delay_spin.value()
        if min_val > max_val:
            min_val = max_val
            self.min_delay_spin.setValue(min_val)

        return {
            SETTING_MIN_MEMBER_DELAY: min_val,
            SETTING_MAX_MEMBER_DELAY: max_val,
            SETTING_MONITORING_INTERVAL: self.monitoring_interval_spin.value(),
            SETTING_BACKOFF_429: self.backoff_429_spin.value(),
            SETTING_BACKOFF_GENERAL: self.backoff_general_spin.value(),
            SETTING_REQUEST_TIMEOUT: self.request_timeout_spin.value()
        }

class ViewMemberDialog(QDialog):
    def __init__(self, member, parent=None):
        super().__init__(parent)
        self.member = member
        self.setWindowTitle(f"عرض معلومات العضو: {self.member.get_full_name_ar() or self.member.nin}")
        self.setModal(True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(550)
        self.setMinimumHeight(400)
        
        main_dialog_layout = QVBoxLayout(self)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_widget = QWidget()
        form_layout = QFormLayout(content_widget)
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setSpacing(10)

        def add_read_only_field(label_text, value_text):
            value_edit = QLineEdit(str(value_text) if value_text is not None else "")
            value_edit.setReadOnly(True)
            value_edit.setStyleSheet("QLineEdit:read-only { background-color: #3E4A5C; color: #E0E0E0; border: 1px solid #4A5568; }")
            form_layout.addRow(label_text, value_edit)

        add_read_only_field("الاسم الكامل (عربي):", self.member.get_full_name_ar())
        add_read_only_field("الاسم (لاتيني):", self.member.nom_fr)
        add_read_only_field("اللقب (لاتيني):", self.member.prenom_fr)
        add_read_only_field("رقم التعريف الوطني (NIN):", self.member.nin)
        add_read_only_field("رقم طالب الشغل (الوسيط):", self.member.wassit_no)
        
        ccp_display = self.member.ccp
        if len(self.member.ccp) == 12:
             ccp_display = f"{self.member.ccp[:10]} {self.member.ccp[10:]}"
        add_read_only_field("رقم الحساب البريدي (CCP):", ccp_display)
        add_read_only_field("رقم الهاتف:", self.member.phone_number)
        add_read_only_field("الحالة الحالية:", self.member.status)
        
        rdv_date_display = self.member.rdv_date or "لا يوجد"
        if self.member.rdv_date:
            if self.member.rdv_source == "system":
                rdv_date_display += " (نظام)"
            elif self.member.rdv_source == "discovered":
                 rdv_date_display += " (مكتشف)"
        add_read_only_field("تاريخ الموعد:", rdv_date_display)
        
        details_label = QLabel("آخر تحديث/خطأ (كامل):")
        self.details_text_edit = QTextEdit(self.member.full_last_activity_detail or "لا يوجد")
        self.details_text_edit.setReadOnly(True)
        self.details_text_edit.setFixedHeight(80)
        self.details_text_edit.setStyleSheet("QTextEdit:read-only { background-color: #3E4A5C; color: #E0E0E0; border: 1px solid #4A5568; }")
        form_layout.addRow(details_label, self.details_text_edit)

        add_read_only_field("ID التسجيل المسبق:", self.member.pre_inscription_id or "N/A")
        add_read_only_field("ID طالب الشغل:", self.member.demandeur_id or "N/A")
        add_read_only_field("ID الهيكل:", self.member.structure_id or "N/A")
        add_read_only_field("ID الموعد:", self.member.rdv_id or "N/A")
        add_read_only_field("مصدر الموعد:", self.member.rdv_source or "غير محدد")
        add_read_only_field("مسار ملف الالتزام:", self.member.pdf_honneur_path or "لم يتم التحميل")
        add_read_only_field("مسار ملف الموعد:", self.member.pdf_rdv_path or "لم يتم التحميل")
        add_read_only_field("لديه تسجيل مسبق فعلي؟:", "نعم" if self.member.has_actual_pre_inscription else "لا")
        add_read_only_field("لديه موعد بالفعل؟:", "نعم" if self.member.already_has_rdv else "لا")
        add_read_only_field("عدد مرات الفشل المتتالية:", str(self.member.consecutive_failures))
        add_read_only_field("مستفيد حاليًا من المنحة؟:", "نعم" if self.member.have_allocation else "لا")
        
        if self.member.have_allocation and self.member.allocation_details:
            allocation_details_str = ", ".join(f"{key}: {value}" for key, value in self.member.allocation_details.items())
            add_read_only_field("تفاصيل الاستفادة:", allocation_details_str or "لا توجد تفاصيل")

        scroll_area.setWidget(content_widget)
        main_dialog_layout.addWidget(scroll_area)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.close_button = QPushButton("إغلاق")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        button_layout.addStretch()
        main_dialog_layout.addLayout(button_layout)

class SubscriptionDetailsDialog(QDialog):
    def __init__(self, subscription_data, parent=None):
        super().__init__(parent)
        self.subscription_data = subscription_data if subscription_data else {} 
        self.setWindowTitle("تفاصيل الاشتراك الحالي")
        self.setModal(True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(550)
        self.setObjectName("SubscriptionDetailsDialog")

        main_layout = QVBoxLayout(self)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        content_widget = QWidget()
        self.form_layout = QFormLayout(content_widget)
        self.form_layout.setLabelAlignment(Qt.AlignRight)
        self.form_layout.setSpacing(12) 
        self.form_layout.setContentsMargins(10, 5, 10, 5)


        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._update_countdown_display)

        self._populate_details()

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area)

        close_button = QPushButton("إغلاق", self)
        close_button.setIcon(self.style().standardIcon(QStyle.SP_DialogCloseButton))
        close_button.clicked.connect(self.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(close_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        
        self.setStyleSheet("""
            QDialog#SubscriptionDetailsDialog { background-color: #2B2B2B; border: 1px solid #4A4A4A; }
            SubscriptionDetailsDialog QLabel { color: #E0E0E0; font-family: "Tajawal Regular"; font-size: 10pt; padding: 2px; }
            SubscriptionDetailsDialog QLabel#DialogTitleLabel { font-family: "Tajawal Bold"; font-size: 15pt; color: #00BFFF; padding-bottom: 8px; border-bottom: 1px solid #4A4A4A; margin-bottom: 10px;}
            SubscriptionDetailsDialog QLabel[isBold="true"] { font-family: "Tajawal Medium"; font-weight: bold; color: #B0C4DE; } 
            SubscriptionDetailsDialog QLabel#ExpiryCountdownLabel { font-family: "Tajawal Bold"; color: #FFD700; } 
            SubscriptionDetailsDialog QTextEdit#ActivatedDevicesText { background-color: #363636; color: #D3D3D3; border: 1px solid #505050; border-radius: 4px; font-family: "Consolas", "Courier New", monospace; font-size: 9pt; }
            SubscriptionDetailsDialog QPushButton { min-width: 90px; }
        """)

    def _add_detail_row(self, label_text, value_widget_or_text, is_value_html=False):
        label = QLabel(f"{label_text}:")
        label.setProperty("isBold", True) 
        
        if isinstance(value_widget_or_text, QWidget):
            value_widget = value_widget_or_text
        else:
            value_widget = QLabel(str(value_widget_or_text) if value_widget_or_text is not None else "غير محدد")
            value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_widget.setWordWrap(True)
            if is_value_html:
                value_widget.setTextFormat(Qt.RichText) 
        
        self.form_layout.addRow(label, value_widget)
        return value_widget


    def _format_datetime_display(self, dt_object, show_timezone_info=True):
        if not dt_object or not isinstance(dt_object, datetime.datetime):
            return "غير محدد"
        try:
            if dt_object.tzinfo is None:
                dt_object = dt_object.replace(tzinfo=datetime.timezone.utc)
            else:
                dt_object = dt_object.astimezone(datetime.timezone.utc)

            q_dt = QDateTime(dt_object.year, dt_object.month, dt_object.day,
                             dt_object.hour, dt_object.minute, dt_object.second, Qt.UTC)
            if q_dt.isValid():
                local_time_str = q_dt.toLocalTime().toString("yyyy/MM/dd - hh:mm:ss AP")
                return f"{local_time_str} (بالتوقيت المحلي)" if show_timezone_info else local_time_str
            
            fallback_str = dt_object.strftime("%Y/%m/%d - %H:%M:%S")
            return f"{fallback_str} (UTC - خطأ تحويل)" if show_timezone_info else fallback_str
        except Exception:
            return str(dt_object)

    def _format_remaining_time(self, expiry_datetime_utc):
        if not expiry_datetime_utc or not isinstance(expiry_datetime_utc, datetime.datetime):
            return "N/A"
        
        if expiry_datetime_utc.tzinfo is None:
            expiry_datetime_utc = expiry_datetime_utc.replace(tzinfo=datetime.timezone.utc)

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        remaining_delta = expiry_datetime_utc - now_utc

        if remaining_delta.total_seconds() <= 0:
            self.countdown_timer.stop()
            return "منتهي الصلاحية"

        days = remaining_delta.days
        hours, remainder = divmod(remaining_delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0: parts.append(f"{days} يوم")
        if hours > 0: parts.append(f"{hours} ساعة")
        if minutes > 0: parts.append(f"{minutes} دقيقة")
        if not parts or (days == 0 and hours == 0 and minutes < 5):
            parts.append(f"{seconds} ثانية")
        
        return " ".join(parts) if parts else "لحظات قليلة"

    def _populate_details(self):
        while self.form_layout.rowCount() > 0:
            self.form_layout.removeRow(0)

        title_label = QLabel("معلومات الاشتراك الحالي")
        title_label.setObjectName("DialogTitleLabel") 
        title_label.setAlignment(Qt.AlignCenter)
        self.form_layout.addRow(title_label)
        
        self.form_layout.addRow(QFrame(self)) 

        self._add_detail_row("كود التفعيل", self.subscription_data.get("id", "غير متوفر"))
        
        status = self.subscription_data.get("status", "غير معروف").upper()
        status_display_ar = {"ACTIVE": "نشط", "EXPIRED": "منتهي الصلاحية", "REVOKED": "تم إلغاؤه", "UNUSED": "غير مستخدم"}.get(status, status)
        status_color = {"ACTIVE": "#2ECC71", "EXPIRED": "#F39C12", "REVOKED": "#E74C3C", "UNUSED": "#BDC3C7"}.get(status, "#E0E0E0")
        self._add_detail_row("حالة الكود", f"<span style='color:{status_color}; font-weight:bold;'>{status_display_ar}</span>", is_value_html=True)

        duration_data = self.subscription_data.get('validityDuration')
        validity_duration_str = "غير محددة"
        is_trial = False
        if isinstance(duration_data, dict):
            unit = duration_data.get('unit')
            value = duration_data.get('value')
            total_days_equivalent = 0

            if unit == "days":
                total_days_equivalent = int(value or 0)
                validity_duration_str = f"{value} يومًا"
                if "value_hours" in duration_data and duration_data.get('value_hours', 0) > 0 : validity_duration_str += f" و {duration_data['value_hours']} ساعة"
                if "value_minutes" in duration_data and duration_data.get('value_minutes', 0) > 0: validity_duration_str += f" و {duration_data['value_minutes']} دقيقة"
            elif unit == "hours":
                total_days_equivalent = int(value or 0) / 24
                validity_duration_str = f"{value} ساعة"
                if "value_minutes" in duration_data and duration_data.get('value_minutes', 0) > 0: validity_duration_str += f" و {duration_data['value_minutes']} دقيقة"
            elif unit == "minutes":
                total_days_equivalent = int(value or 0) / (24 * 60)
                validity_duration_str = f"{value} دقيقة"
            elif unit == "none":
                validity_duration_str = "بدون انتهاء صلاحية (دائم)"
            
            if unit != "none" and total_days_equivalent > 0 and total_days_equivalent <= 7: 
                is_trial = True
                validity_duration_str += " <span style='color:#FFD700;'>(فترة تجريبية)</span>"
        
        self._add_detail_row("مدة الصلاحية المحددة", validity_duration_str, is_value_html=True)


        self.actual_expires_at_label = self._add_detail_row("تاريخ الانتهاء الفعلي", "", is_value_html=True)
        self._update_countdown_display()

        self.form_layout.addRow(QFrame(self)) 

        self._add_detail_row("تاريخ إنشاء الكود", self._format_datetime_display(self.subscription_data.get("createdAt")))
        self._add_detail_row("تاريخ تفعيل الكود (أول مرة)", self._format_datetime_display(self.subscription_data.get("activatedAt")))
        if self.subscription_data.get("revokedAt"):
            self._add_detail_row("تاريخ إلغاء الكود", self._format_datetime_display(self.subscription_data.get("revokedAt")))

        self.form_layout.addRow(QFrame(self)) 
        self._add_detail_row("الحد الأقصى للأجهزة", str(self.subscription_data.get("deviceLimit", 1)))
        
        activated_devices = self.subscription_data.get("activatedDevices", [])
        if isinstance(activated_devices, list) and activated_devices:
            devices_section_label = QLabel(f"الأجهزة المفعلة حاليًا ({len(activated_devices)} من {self.subscription_data.get('deviceLimit', 1)}):")
            devices_section_label.setProperty("isBold", True)
            self.form_layout.addRow(devices_section_label)

            devices_text_edit = QTextEdit()
            devices_text_edit.setObjectName("ActivatedDevicesText")
            devices_text_edit.setReadOnly(True)
            devices_text_edit.setFixedHeight(min(150, len(activated_devices) * 80))
            
            html_output = "<div style='padding: 5px;'>"
            for i, device_info in enumerate(activated_devices):
                if isinstance(device_info, dict):
                    dev_id = device_info.get("generated_device_id", "معرف غير متوفر")
                    hostname = device_info.get("hostname", device_info.get("system_username", "جهاز غير مسمى"))
                    os_platform = device_info.get("os_platform", "نظام غير معروف")
                    activated_at_device_ts = device_info.get('activationTimestamp')
                    activated_at_device_str = self._format_datetime_display(activated_at_device_ts, show_timezone_info=False)
                    
                    html_output += f"<div style='margin-bottom: 8px; border-bottom: 1px dashed #444; padding-bottom: 5px;'>"
                    html_output += f"<b>الجهاز {i+1}:</b> {hostname} ({os_platform})<br>"
                    html_output += f"&nbsp;&nbsp;المعرف: <span style='font-family: Consolas, monospace;'>{dev_id}</span><br>"
                    html_output += f"&nbsp;&nbsp;تاريخ تفعيل هذا الجهاز: {activated_at_device_str}</div>"
                else:
                    html_output += f"<div style='margin-bottom: 8px;'><b>الجهاز {i+1} (بيانات غير قياسية):</b> {str(device_info)}</div>"
            html_output += "</div>"
            devices_text_edit.setHtml(html_output)
            self.form_layout.addRow(devices_text_edit)
        else:
            self._add_detail_row("الأجهزة المفعلة", "لا توجد أجهزة مفعلة حاليًا بهذا الكود.")


    def _update_countdown_display(self):
        actual_expires_at = self.subscription_data.get("actualExpiresAt")
        status = self.subscription_data.get("status", "UNKNOWN").upper()

        if status == "ACTIVE" and actual_expires_at and isinstance(actual_expires_at, datetime.datetime):
            remaining_str = self._format_remaining_time(actual_expires_at)
            expiry_display_text = self._format_datetime_display(actual_expires_at)
            if "منتهي الصلاحية" not in remaining_str and "N/A" not in remaining_str:
                self.actual_expires_at_label.setText(f"{expiry_display_text}<br><b id='ExpiryCountdownLabel'>متبقي: {remaining_str}</b>")
                if not self.countdown_timer.isActive():
                    self.countdown_timer.start(1000)
            else: 
                self.actual_expires_at_label.setText(f"{expiry_display_text} (<span style='color:{'#F39C12' if 'منتهي' in remaining_str else '#E0E0E0'};'>{remaining_str}</span>)")
                self.countdown_timer.stop()
        
        elif status == "EXPIRED":
            expiry_display_text = self._format_datetime_display(actual_expires_at)
            self.actual_expires_at_label.setText(f"<span style='color:#F39C12;'>منتهي الصلاحية</span> ({expiry_display_text})")
            self.countdown_timer.stop()
        elif status == "REVOKED":
            revoked_date_display = self._format_datetime_display(self.subscription_data.get('revokedAt'))
            self.actual_expires_at_label.setText(f"<span style='color:#E74C3C;'>تم إلغاؤه</span> ({revoked_date_display})")
            self.countdown_timer.stop()
        elif self.subscription_data.get('validityDuration', {}).get('unit') == 'none' and status == "UNUSED":
             self.actual_expires_at_label.setText("دائم (يبدأ عند التفعيل الأول)")
             self.countdown_timer.stop()
        elif self.subscription_data.get('validityDuration', {}).get('unit') == 'none' and status == "ACTIVE":
             self.actual_expires_at_label.setText("دائم (نشط)")
             self.countdown_timer.stop()
        else:
            self.actual_expires_at_label.setText(self._format_datetime_display(actual_expires_at))
            self.countdown_timer.stop()
            
    def closeEvent(self, event):
        self.countdown_timer.stop()
        super().closeEvent(event)

class ActivationDialog(QDialog):
    # إشارة تصدر عند محاولة التفعيل، تحمل الكود المدخل
    activation_attempted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تفعيل البرنامج")
        self.setModal(True)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(480) # زيادة العرض قليلًا
        self.setObjectName("ActivationDialog")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint) # إزالة زر المساعدة

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(25, 25, 25, 25) # زيادة الهوامش
        main_layout.setSpacing(18) # زيادة التباعد

        # --- قسم العنوان والأيقونة ---
        header_frame = QFrame(self)
        header_frame.setObjectName("ActivationHeaderFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0,0,0,0)
        header_layout.setSpacing(15) # تباعد بين الأيقونة والعنوان

        self.icon_label = QLabel(self)
        # استخدام أيقونة مفتاح أو قفل أو درع أكثر تعبيرًا
        key_icon_pixmap = QPixmap(self.style().standardIcon(QStyle.SP_MessageBoxInformation).pixmap(64, 64)) # استخدام أيقونة أكبر
        # يمكنك استبدالها بأيقونة مخصصة إذا أردت:
        # from utils import resource_path
        # key_icon_pixmap = QPixmap(resource_path("icons/key_icon.png")).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.icon_label.setPixmap(key_icon_pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.icon_label)

        title_font = QFont("Tajawal Bold", 18) # خط أكبر وأكثر بروزًا للعنوان
        self.title_label = QLabel("تفعيل البرنامج", self)
        self.title_label.setFont(title_font)
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter) # محاذاة لليسار (يمين في RTL)
        self.title_label.setObjectName("ActivationTitleLabel")
        header_layout.addWidget(self.title_label, 1) # السماح للعنوان بالتمدد
        
        main_layout.addWidget(header_frame)
        
        # --- قسم التعليمات ---
        self.instruction_label = QLabel("الرجاء إدخال كود التفعيل الخاص بك للمتابعة.", self)
        self.instruction_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter) # محاذاة لليمين
        self.instruction_label.setWordWrap(True)
        self.instruction_label.setObjectName("ActivationInstructionLabel")
        main_layout.addWidget(self.instruction_label)

        # --- قسم حقل الإدخال ---
        self.activation_code_input = QLineEdit(self)
        self.activation_code_input.setPlaceholderText("أدخل كود التفعيل هنا")
        self.activation_code_input.setAlignment(Qt.AlignCenter)
        self.activation_code_input.setMinimumHeight(40) # زيادة ارتفاع الحقل
        self.activation_code_input.setObjectName("ActivationCodeInput")
        # إضافة تأثير ظل بسيط
        shadow_effect = QGraphicsDropShadowEffect(self)
        shadow_effect.setBlurRadius(10)
        shadow_effect.setColor(QColor(0,0,0,80))
        shadow_effect.setOffset(2,2)
        self.activation_code_input.setGraphicsEffect(shadow_effect)
        main_layout.addWidget(self.activation_code_input)

        # --- قسم رسالة الحالة ---
        self.status_message_area = QTextEdit(self)
        self.status_message_area.setReadOnly(True)
        self.status_message_area.setObjectName("ActivationStatusMessageArea")
        self.status_message_area.setMinimumHeight(70) # زيادة ارتفاع منطقة الرسالة
        self.status_message_area.setMaximumHeight(130)
        self.status_message_area.setAlignment(Qt.AlignCenter)
        self.status_message_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded) # إظهار شريط التمرير عند الحاجة
        main_layout.addWidget(self.status_message_area)
        
        # --- فاصل ---
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setObjectName("ActivationLineSeparator")
        main_layout.addWidget(line)

        # --- قسم الأزرار ---
        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.setSpacing(12) # زيادة التباعد بين الأزرار

        self.activate_button = QPushButton("تفعيل", self)
        self.activate_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.activate_button.setObjectName("ActivationActivateButton")
        self.activate_button.setFixedHeight(40) # تحديد ارتفاع موحد للأزرار
        self.buttons_layout.addWidget(self.activate_button)

        self.cancel_button = QPushButton("إلغاء", self)
        self.cancel_button.setIcon(self.style().standardIcon(QStyle.SP_DialogCancelButton))
        self.cancel_button.setObjectName("ActivationCancelButton")
        self.cancel_button.setFixedHeight(40)
        self.buttons_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(self.buttons_layout)

        self.activate_button.clicked.connect(self._handle_activate_clicked)
        self.cancel_button.clicked.connect(self.reject)

        self._apply_styles() # تطبيق الأنماط من دالة منفصلة

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog#ActivationDialog {
                background-color: #2E3440; /* Nord Polar Night */
                border-radius: 8px; /* حواف دائرية للحوار */
            }
            QFrame#ActivationHeaderFrame {
                border-bottom: 1px solid #4C566A; /* Nord Frost - أغمق قليلاً */
                padding-bottom: 12px;
                margin-bottom: 8px;
            }
            QLabel#ActivationTitleLabel {
                color: #ECEFF4; /* Nord Snow Storm - فاتح */
                font-family: "Tajawal Bold";
            }
            QLabel#ActivationInstructionLabel {
                color: #D8DEE9; /* Nord Snow Storm - أفتح قليلاً */
                font-size: 10pt;
                font-family: "Tajawal Regular";
                padding-bottom: 5px; /* تباعد إضافي أسفل التعليمات */
            }
            QLineEdit#ActivationCodeInput {
                font-size: 13pt; /* خط أكبر لحقل الإدخال */
                font-family: "Tajawal Medium";
                background-color: #3B4252; /* Nord Polar Night - أفتح قليلاً */
                color: #ECEFF4;
                border: 1px solid #4C566A;
                border-radius: 6px; /* حواف دائرية أكثر */
                padding: 10px; /* زيادة الحشو الداخلي */
            }
            QLineEdit#ActivationCodeInput:focus {
                border: 1px solid #88C0D0; /* Nord Frost - أزرق فاتح */
                background-color: #434C5E; /* Nord Polar Night - أفتح عند التركيز */
            }
            QTextEdit#ActivationStatusMessageArea {
                font-family: "Tajawal Regular";
                font-size: 10pt;
                border: 1px solid #4C566A;
                border-radius: 6px;
                background-color: #3B4252;
                color: #D8DEE9;
                padding: 10px;
            }
            QFrame#ActivationLineSeparator {
                background-color: #4C566A;
                max-height: 1px;
            }
            QPushButton#ActivationActivateButton {
                background-color: #A3BE8C; /* Nord Frost - أخضر */
                color: #2E3440; /* لون النص داكن للتباين */
                font-family: "Tajawal Bold";
                padding: 10px 22px; /* زيادة الحشو الأفقي */
                border-radius: 6px;
                border: none; /* إزالة الحدود الافتراضية */
            }
            QPushButton#ActivationActivateButton:hover {
                background-color: #B4D0A0; /* أخضر أفتح عند المرور */
            }
            QPushButton#ActivationActivateButton:pressed {
                background-color: #90AB7C; /* أخضر أغمق عند الضغط */
            }
            QPushButton#ActivationActivateButton:disabled {
                background-color: #4C566A;
                color: #6c788c;
            }
            QPushButton#ActivationCancelButton {
                background-color: #BF616A; /* Nord Aurora - أحمر */
                color: #ECEFF4; /* لون نص فاتح */
                font-family: "Tajawal Bold";
                padding: 10px 22px;
                border-radius: 6px;
                border: none;
            }
            QPushButton#ActivationCancelButton:hover {
                background-color: #D08770; /* Nord Aurora - برتقالي/أحمر أفتح */
            }
            QPushButton#ActivationCancelButton:pressed {
                background-color: #AB545C; /* أحمر أغمق عند الضغط */
            }
        """)

    def _handle_activate_clicked(self):
        # إصدار الإشارة بالكود المدخل
        self.activation_attempted.emit(self.get_activation_code())
        # سيتم قبول الحوار أو رفضه من main_app.py بعد معالجة التفعيل

    def get_activation_code(self):
        return self.activation_code_input.text().strip().upper()

    def show_status_message(self, message, is_error=False, is_warning=False, is_success=False, is_waiting=False):
        display_message = message
        
        style_sheet_base = "font-family: 'Tajawal Regular'; font-weight: normal; padding: 8px;" # تعديل الوزن الافتراضي
        text_color = "#D8DEE9" # Nord Snow Storm - لون النص الافتراضي

        if is_waiting:
            display_message = f"⏳ {message}" # إضافة أيقونة انتظار بسيطة
            text_color = "#EBCB8B" # Nord Aurora - أصفر للانتظار
            self.activate_button.setEnabled(False)
            self.activation_code_input.setEnabled(False)
        else:
            self.activate_button.setEnabled(True)
            self.activation_code_input.setEnabled(True)

        if is_error:
            display_message = f"❌ {message}"
            text_color = "#BF616A" # Nord Aurora - أحمر للخطأ
            style_sheet_base += " font-weight: bold;"
        elif is_warning:
            display_message = f"⚠️ {message}"
            text_color = "#D08770" # Nord Aurora - برتقالي للتحذير
            style_sheet_base += " font-weight: bold;"
        elif is_success:
            display_message = f"✅ {message}"
            text_color = "#A3BE8C" # Nord Frost - أخضر للنجاح
            style_sheet_base += " font-weight: bold;"
        
        self.status_message_area.setText(display_message)
        self.status_message_area.setStyleSheet(f"color: {text_color}; {style_sheet_base}")
        QApplication.processEvents() # التأكد من تحديث الواجهة فورًا
