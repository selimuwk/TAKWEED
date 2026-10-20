# -*- coding: utf-8 -*-

import os
import json
import base64
import mimetypes
import threading

import requests

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform
from kivy.lang import Builder

from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.image import Image

# =========================================================
# SETTINGS
# =========================================================

API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzjpc555-5YWzUDNTAqaQ2xQP4F7C9FKNm3vbrQp80B_FuSxHQf0NdMvWRpb5gHX9Xvnw/exec"
)

CUSTOMER_CLASSES = [
    "DG-WS-NW",
    "DG-SVS-DC",
    "DG-RT-NR",
    "DG-SVS-SW",
    "DG-SVS-KR",
    "DG-MT-KSM",
    "DG-MT-PS",
    "DG-MT-KA",
    "FB-RT",
    "NDT-VEN",
    "NDT-INS",
    "CC-KA",
    "CC-RT",
    "CC-DS",
    "NDT-RT",
    "CC-WS",
    "PL-DG",
    "DG-EC-OEM",
    "DG-EC-OED",
    "NDT-CON",
    "DG-WS-KW",
    "CC-DRI",
    "DG-PC-PHA",
    "CC-CS",
    "FB-WS",
    "FB-SDS",
    "CC-OEM",
    "NDT-OED",
    "FB-DS",
]

STATEMENT_REQUIRED_CLASSES = {
    "DG-RT-NR",
    "FB-RT",
    "CC-RT",
    "NDT-RT",
}

MAX_PHOTO_SIZE = 8 * 1024 * 1024


# =========================================================
# GENERAL HELPERS
# =========================================================

def normalize_salesperson_id(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.endswith(".0"):
        value = value[:-2]

    return value


def valid_coordinates(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)

        return (
            -90 <= lat <= 90
            and -180 <= lon <= 180
            and not (lat == 0 and lon == 0)
        )
    except (ValueError, TypeError):
        return False


def api_post(payload):
    response = requests.post(
        API_URL,
        json=payload,
        timeout=90,
        headers={"Content-Type": "application/json"},
    )

    response.raise_for_status()

    try:
        result = response.json()
    except ValueError:
        raise Exception("استجابة Google Apps Script ليست JSON صالحًا.")

    if isinstance(result, dict) and result.get("ok") is False:
        raise Exception(
            result.get("message")
            or result.get("error")
            or "فشل تنفيذ العملية."
        )

    return result


def get_value(data, *keys, default=""):
    if not isinstance(data, dict):
        return default

    for key in keys:
        if key in data and data[key] is not None:
            return data[key]

    return default


# =========================================================
# MAIN APP
# =========================================================

class TakweedApp(App):

    def build(self):
        self.title = "TAKWEED Customer Coding"

        self.token = ""
        self.user = {}
        self.role = ""
        self.salesperson_id = ""

        self.mapping = {}
        self.areas = []
        self.selected_area = None

        self.photos = []
        self.current_requests = []

        self.gps_lat = None
        self.gps_lon = None
        self.gps_accuracy = None
        self.gps_started = False

        self.sm = ScreenManager()

        self.login_screen = Screen(name="login")
        self.home_screen = Screen(name="home")
        self.form_screen = Screen(name="customer_form")
        self.requests_screen = Screen(name="requests")

        self.sm.add_widget(self.login_screen)
        self.sm.add_widget(self.home_screen)
        self.sm.add_widget(self.form_screen)
        self.sm.add_widget(self.requests_screen)

        self.build_login_screen()
        self.build_home_screen()
        self.build_customer_form()

        self.sm.current = "login"

        return self.sm

    # -----------------------------------------------------
    # UI HELPERS
    # -----------------------------------------------------

    def make_label(self, text, size=16, height=dp(38)):
        return Label(
            text=str(text),
            size_hint_y=None,
            height=height,
            font_size=sp(size),
            color=(0.12, 0.16, 0.22, 1),
            halign="left",
            valign="middle",
        )

    def make_button(self, text, callback, height=48):
        button = Button(
            text=text,
            size_hint_y=None,
            height=dp(height),
            font_size=sp(16),
            background_normal="",
            background_color=(0.08, 0.36, 0.65, 1),
            color=(1, 1, 1, 1),
        )
        button.bind(on_release=lambda *_: callback())
        return button

    def make_input(self, hint, password=False, multiline=False):
        return TextInput(
            hint_text=hint,
            password=password,
            multiline=multiline,
            size_hint_y=None,
            height=dp(46 if not multiline else 90),
            font_size=sp(16),
            padding=[dp(10), dp(10)],
        )

    def make_spinner(self, values, text="اختر"):
        return Spinner(
            text=text,
            values=values,
            size_hint_y=None,
            height=dp(46),
            font_size=sp(15),
        )

    def show_message(self, title, message):
        content = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            padding=dp(12),
        )

        label = Label(
            text=str(message),
            halign="center",
            valign="middle",
        )
        label.bind(size=lambda obj, size: setattr(obj, "text_size", size))

        content.add_widget(label)

        close_btn = Button(
            text="موافق",
            size_hint_y=None,
            height=dp(44),
        )
        content.add_widget(close_btn)

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.9, 0.42),
            auto_dismiss=False,
        )

        close_btn.bind(on_release=popup.dismiss)
        popup.open()

    def show_loading(self, message="جاري التنفيذ..."):
        content = BoxLayout(
            orientation="vertical",
            padding=dp(20),
        )

        content.add_widget(
            Label(text=message, halign="center")
        )

        popup = Popup(
            title="TAKWEED",
            content=content,
            size_hint=(0.8, 0.25),
            auto_dismiss=False,
        )

        popup.open()
        return popup

    def run_api(self, payload, on_success, on_error=None, message="جاري الاتصال..."):
        popup = self.show_loading(message)

        def worker():
            try:
                result = api_post(payload)

                Clock.schedule_once(
                    lambda dt: self.finish_api(
                        popup, on_success, result
                    ),
                    0,
                )

            except Exception as exc:
                error_text = str(exc)

                Clock.schedule_once(
                    lambda dt: self.fail_api(
                        popup, on_error, error_text
                    ),
                    0,
                )

        threading.Thread(target=worker, daemon=True).start()

    def finish_api(self, popup, callback, result):
        popup.dismiss()

        if callback:
            callback(result)

    def fail_api(self, popup, callback, error):
        popup.dismiss()

        if callback:
            callback(error)
        else:
            self.show_message("خطأ", error)

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    def build_login_screen(self):
        root = BoxLayout(
            orientation="vertical",
            padding=dp(24),
            spacing=dp(12),
        )

        root.add_widget(
            Label(
                text="[b]TAKWEED[/b]\nCustomer Coding",
                markup=True,
                font_size=sp(26),
                size_hint_y=None,
                height=dp(100),
                color=(0.08, 0.36, 0.65, 1),
            )
        )

        root.add_widget(self.make_label("اسم المستخدم"))
        self.username_input = self.make_input("Username")
        root.add_widget(self.username_input)

        root.add_widget(self.make_label("كلمة المرور"))
        self.password_input = self.make_input(
            "Password",
            password=True,
        )
        root.add_widget(self.password_input)

        root.add_widget(
            self.make_button("تسجيل الدخول", self.login)
        )

        self.login_screen.add_widget(root)

    def login(self):
        username = self.username_input.text.strip()
        password = self.password_input.text

        if not username or not password:
            self.show_message(
                "تنبيه",
                "أدخل اسم المستخدم وكلمة المرور.",
            )
            return

        payload = {
            "action": "login",
            "username": username,
            "password": password,
        }

        self.run_api(
            payload,
            self.on_login_success,
            message="جاري تسجيل الدخول...",
        )

    def on_login_success(self, result):
        data = result.get("data", result) if isinstance(result, dict) else {}

        self.token = get_value(data, "token", "Token")
        self.user = get_value(data, "user", "User", default={})

        if not isinstance(self.user, dict):
            self.user = {}

        self.role = str(
            get_value(
                self.user,
                "Role",
                "role",
                default=get_value(data, "role", "Role"),
            )
        ).strip()

        self.salesperson_id = normalize_salesperson_id(
            get_value(
                self.user,
                "Salesperson ID",
                "SalespersonID",
                "salespersonId",
                "Salesperson Id",
            )
        )

        if not self.token:
            self.show_message(
                "تعذر تسجيل الدخول",
                "الاستجابة لم تحتوِ على Token. "
                "راجع أسماء الحقول التي يعيدها API.",
            )
            return

        self.update_home_screen()
        self.sm.current = "home"

        if self.role.lower() in (
            "rep",
            "sales rep",
            "retail rep",
        ):
            self.load_salesperson_mapping()

    # -----------------------------------------------------
    # HOME
    # -----------------------------------------------------

    def build_home_screen(self):
        self.home_layout = BoxLayout(
            orientation="vertical",
            padding=dp(18),
            spacing=dp(12),
        )

        self.home_title = Label(
            text="TAKWEED",
            font_size=sp(23),
            size_hint_y=None,
            height=dp(65),
            color=(0.08, 0.36, 0.65, 1),
        )

        self.home_layout.add_widget(self.home_title)

        self.home_buttons = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
        )

        self.home_layout.add_widget(self.home_buttons)

        self.home_layout.add_widget(
            self.make_button("تسجيل الخروج", self.logout)
        )

        self.home_screen.add_widget(self.home_layout)

    def update_home_screen(self):
        self.home_buttons.clear_widgets()

        username = get_value(
            self.user,
            "Username",
            "username",
            "Rep Name",
            "Name",
            default="",
        )

        self.home_title.text = (
            "TAKWEED\n" + str(username) + "\n" + self.role
        )

        if self.role.lower() in (
            "rep",
            "sales rep",
            "retail rep",
        ):
            self.home_buttons.add_widget(
                self.make_button(
                    "طلب تسجيل عميل جديد",
                    self.open_customer_form,
                )
            )

            self.home_buttons.add_widget(
                self.make_button(
                    "طلباتي",
                    self.load_my_requests,
                )
            )

        elif self.role.lower() in (
            "sector manager",
            "branch manager",
            "central admin",
        ):
            self.home_buttons.add_widget(
                self.make_button(
                    "مراجعة طلبات العملاء",
                    self.load_review_requests,
                )
            )

        else:
            self.home_buttons.add_widget(
                self.make_button(
                    "طلباتي",
                    self.load_my_requests,
                )
            )

            self.home_buttons.add_widget(
                self.make_button(
                    "مراجعة الطلبات",
                    self.load_review_requests,
                )
            )

    def logout(self):
        self.stop_gps()
        self.token = ""
        self.user = {}
        self.role = ""
        self.salesperson_id = ""
        self.sm.current = "login"

    # -----------------------------------------------------
    # SALESPERSON MAPPING
    # -----------------------------------------------------

    def load_salesperson_mapping(self):
        self.run_api(
            {
                "action": "getSalespersonMapping",
                "token": self.token,
            },
            self.on_mapping_loaded,
            message="جاري تحميل بيانات المندوب...",
        )

    def on_mapping_loaded(self, result):
        data = result.get("data", result) if isinstance(result, dict) else {}

        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get(
                "mapping",
                data.get("records", data.get("data", [])),
            )
        else:
            records = []

        self.mapping = {}

        if isinstance(records, list):
            for row in records:
                if not isinstance(row, dict):
                    continue

                sid = normalize_salesperson_id(
                    get_value(
                        row,
                        "Salesperson ID",
                        "SalespersonID",
                        "Salesperson Id",
                    )
                )

                if sid:
                    self.mapping[sid] = row

        if self.salesperson_id and self.mapping:
            if self.salesperson_id not in self.mapping:
                self.show_message(
                    "تنبيه",
                    "المندوب غير موجود في جدول "
                    "SALESPERSON_MAPPING الحالي.",
                )

    # -----------------------------------------------------
    # CUSTOMER FORM
    # -----------------------------------------------------

    def build_customer_form(self):
        scroll = ScrollView()

        self.form_layout = BoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(8),
            size_hint_y=None,
        )
        self.form_layout.bind(
            minimum_height=self.form_layout.setter("height")
        )

        self.form_layout.add_widget(
            self.make_label(
                "تسجيل عميل جديد",
                size=22,
                height=dp(55),
            )
        )

        self.customer_name = self.make_input("اسم العميل")
        self.form_layout.add_widget(self.make_label("Customer Name"))
        self.form_layout.add_widget(self.customer_name)

        self.customer_class = self.make_spinner(
            CUSTOMER_CLASSES,
            "اختر Customer Class",
        )
        self.form_layout.add_widget(self.make_label("Customer Class"))
        self.form_layout.add_widget(self.customer_class)

        self.statement_name = self.make_input("Statement Name")
        self.form_layout.add_widget(self.make_label("Statement Name"))
        self.form_layout.add_widget(self.statement_name)

        self.contact_person = self.make_input("Contact Person")
        self.form_layout.add_widget(self.make_label("Contact Person"))
        self.form_layout.add_widget(self.contact_person)

        self.address1 = self.make_input("Address 1")
        self.address2 = self.make_input("Address 2")

        self.form_layout.add_widget(self.make_label("Address 1"))
        self.form_layout.add_widget(self.address1)

        self.form_layout.add_widget(self.make_label("Address 2"))
        self.form_layout.add_widget(self.address2)

        self.form_layout.add_widget(self.make_label("المنطقة / Address 3"))

        self.area_search = self.make_input("ابحث باسم المنطقة")
        self.form_layout.add_widget(self.area_search)

        self.form_layout.add_widget(
            self.make_button(
                "بحث عن المنطقة",
                self.search_area,
            )
        )

        self.area_spinner = self.make_spinner(
            [],
            "اختر المنطقة",
        )
        self.area_spinner.bind(
            text=self.on_area_selected
        )
        self.form_layout.add_widget(self.area_spinner)

        self.phone1 = self.make_input("Phone 1")
        self.phone2 = self.make_input("Phone 2")
        self.phone3 = self.make_input("Phone 3")

        for title, widget in [
            ("Phone 1", self.phone1),
            ("Phone 2", self.phone2),
            ("Phone 3", self.phone3),
        ]:
            self.form_layout.add_widget(self.make_label(title))
            self.form_layout.add_widget(widget)

        # GPS
        self.form_layout.add_widget(
            self.make_label(
                "موقع العميل GPS",
                size=19,
                height=dp(45),
            )
        )

        self.gps_status = Label(
            text="لم يتم تحديد الموقع بعد",
            size_hint_y=None,
            height=dp(55),
            color=(0.2, 0.2, 0.2, 1),
        )
        self.form_layout.add_widget(self.gps_status)

        self.form_layout.add_widget(
            self.make_button(
                "تحديد موقعي الحالي GPS",
                self.get_current_location,
                height=54,
            )
        )

        self.lat_input = self.make_input("LAT")
        self.lon_input = self.make_input("LONG")

        # The fields are read-only: coordinates must come from GPS.
        self.lat_input.readonly = True
        self.lon_input.readonly = True

        self.form_layout.add_widget(self.make_label("LAT"))
        self.form_layout.add_widget(self.lat_input)

        self.form_layout.add_widget(self.make_label("LONG"))
        self.form_layout.add_widget(self.lon_input)

        self.form_layout.add_widget(
            self.make_label(
                "صور المحل",
                size=19,
                height=dp(45),
            )
        )

        self.photo_status = Label(
            text="لم يتم اختيار صور",
            size_hint_y=None,
            height=dp(45),
        )
        self.form_layout.add_widget(self.photo_status)

        self.form_layout.add_widget(
            self.make_button(
                "إضافة صورة للمحل",
                self.pick_photo,
            )
        )

        self.form_layout.add_widget(
            self.make_button(
                "إرسال طلب العميل",
                self.submit_customer_request,
                height=56,
            )
        )

        self.form_layout.add_widget(
            self.make_button(
                "رجوع",
                self.back_home,
            )
        )

        scroll.add_widget(self.form_layout)
        self.form_screen.add_widget(scroll)

    def open_customer_form(self):
        self.customer_name.text = ""
        self.customer_class.text = "اختر Customer Class"
        self.statement_name.text = ""
        self.contact_person.text = ""

        self.address1.text = ""
        self.address2.text = ""

        self.area_search.text = ""
        self.area_spinner.values = []
        self.area_spinner.text = "اختر المنطقة"

        self.phone1.text = ""
        self.phone2.text = ""
        self.phone3.text = ""

        self.lat_input.text = ""
        self.lon_input.text = ""

        self.gps_lat = None
        self.gps_lon = None
        self.gps_accuracy = None

        self.gps_status.text = "لم يتم تحديد الموقع بعد"

        self.photos = []
        self.photo_status.text = "لم يتم اختيار صور"

        self.selected_area = None

        self.sm.current = "customer_form"

    def back_home(self):
        self.stop_gps()
        self.sm.current = "home"

    # -----------------------------------------------------
    # GPS LOCATION
    # -----------------------------------------------------

    def get_current_location(self):
        if platform != "android":
            self.show_message(
                "GPS",
                "تحديد الموقع الفعلي يحتاج تجربة التطبيق "
                "على هاتف Android.",
            )
            return

        try:
            from android.permissions import (
                request_permissions,
                Permission,
            )

            permissions = [
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION,
            ]

            request_permissions(
                permissions,
                self.on_location_permissions,
            )

        except Exception as exc:
            self.show_message(
                "GPS",
                "تعذر طلب صلاحية الموقع: " + str(exc),
            )

    def on_location_permissions(self, permissions, grants):
        if not grants or not all(grants):
            Clock.schedule_once(
                lambda dt: self.show_message(
                    "صلاحية الموقع",
                    "يجب السماح للتطبيق بالوصول إلى الموقع "
                    "لتحديد إحداثيات العميل.",
                ),
                0,
            )
            return

        Clock.schedule_once(
            lambda dt: self.start_gps(),
            0,
        )

    def start_gps(self):
        try:
            from plyer import gps

            self.gps_status.text = (
                "جاري تحديد الموقع... انتظر حتى تتحسن الدقة"
            )

            gps.configure(
                on_location=self.on_gps_location,
                on_status=self.on_gps_status,
            )

            gps.start(
                minTime=1000,
                minDistance=1,
            )

            self.gps_started = True

        except Exception as exc:
            self.show_message(
                "GPS",
                "تعذر تشغيل GPS. تأكد من تفعيل خدمة الموقع "
                "على الهاتف.\n" + str(exc),
            )

    def on_gps_location(self, **kwargs):
        try:
            lat = float(kwargs.get("lat"))
            lon = float(kwargs.get("lon"))

            accuracy = kwargs.get("accuracy")

            Clock.schedule_once(
                lambda dt: self.update_gps_fields(
                    lat,
                    lon,
                    accuracy,
                ),
                0,
            )

        except (TypeError, ValueError):
            pass

    def on_gps_status(self, stype, status):
        message = f"{stype}: {status}"

        Clock.schedule_once(
            lambda dt: setattr(
                self.gps_status,
                "text",
                message,
            ),
            0,
        )

    def update_gps_fields(self, lat, lon, accuracy):
        if not valid_coordinates(lat, lon):
            self.gps_status.text = "إحداثيات غير صالحة، جاري إعادة المحاولة"
            return

        self.gps_lat = lat
        self.gps_lon = lon

        try:
            self.gps_accuracy = float(accuracy)
        except (TypeError, ValueError):
            self.gps_accuracy = None

        self.lat_input.text = f"{lat:.7f}"
        self.lon_input.text = f"{lon:.7f}"

        if self.gps_accuracy is not None:
            self.gps_status.text = (
                f"تم تحديد الموقع\n"
                f"الدقة التقريبية: {self.gps_accuracy:.1f} متر"
            )
        else:
            self.gps_status.text = "تم تحديد الموقع بنجاح"

    def stop_gps(self):
        if not self.gps_started:
            return

        try:
            from plyer import gps
            gps.stop()
        except Exception:
            pass

        self.gps_started = False

    # -----------------------------------------------------
    # AREA SEARCH
    # -----------------------------------------------------

    def search_area(self):
        query = self.area_search.text.strip()

        if not query:
            self.show_message(
                "تنبيه",
                "اكتب اسم المنطقة للبحث.",
            )
            return

        payload = {
            "action": "searchArea",
            "token": self.token,
            "query": query,
        }

        self.run_api(
            payload,
            self.on_areas_loaded,
            message="جاري البحث عن المنطقة...",
        )

    def on_areas_loaded(self, result):
        data = result.get("data", result) if isinstance(result, dict) else {}

        if isinstance(data, list):
            areas = data
        elif isinstance(data, dict):
            areas = data.get(
                "areas",
                data.get("results", data.get("data", [])),
            )
        else:
            areas = []

        self.areas = [
            area for area in areas
            if isinstance(area, dict)
        ]

        self.selected_area = None

        if not self.areas:
            self.area_spinner.values = []
            self.area_spinner.text = "لا توجد نتائج"
            self.show_message(
                "البحث",
                "لم يتم العثور على مناطق مطابقة.",
            )
            return

        self.area_spinner.values = [
            self.area_display_name(area)
            for area in self.areas
        ]

        self.area_spinner.text = "اختر المنطقة من النتائج"

    def area_display_name(self, area):
        return str(
            get_value(
                area,
                "Address 3",
                "Address3",
                "Area Name",
                "Area",
                "Name",
                "name",
            )
        )

    def on_area_selected(self, spinner, text):
        for area in self.areas:
            if self.area_display_name(area) == text:
                self.selected_area = area
                break

    # -----------------------------------------------------
    # PHOTO PICKER
    # -----------------------------------------------------

    def pick_photo(self):
        try:
            from plyer import filechooser

            filechooser.open_file(
                on_selection=self.on_photo_selected,
                filters=[
                    ["Image files", "*.png", "*.jpg", "*.jpeg", "*.webp"]
                ],
            )

        except Exception as exc:
            self.show_message(
                "الصور",
                "تعذر فتح معرض الصور.\n" + str(exc),
            )

    def on_photo_selected(self, selection):
        if not selection:
            return

        path = selection[0]

        if not os.path.isfile(path):
            self.show_message(
                "الصور",
                "تعذر الوصول إلى ملف الصورة المختار.",
            )
            return

        try:
            size = os.path.getsize(path)

            if size > MAX_PHOTO_SIZE:
                self.show_message(
                    "حجم الصورة",
                    "حجم الصورة أكبر من 8 MB. اختر صورة أصغر.",
                )
                return

            with open(path, "rb") as file:
                encoded = base64.b64encode(
                    file.read()
                ).decode("utf-8")

            mime_type = (
                mimetypes.guess_type(path)[0]
                or "image/jpeg"
            )

            photo = {
                "fileName": os.path.basename(path),
                "mimeType": mime_type,
                "base64": encoded,
            }

            self.photos.append(photo)

            self.photo_status.text = (
                f"عدد الصور المختارة: {len(self.photos)}"
            )

        except Exception as exc:
            self.show_message(
                "الصور",
                "تعذر قراءة الصورة: " + str(exc),
            )

    # -----------------------------------------------------
    # SUBMIT CUSTOMER REQUEST
    # -----------------------------------------------------

    def submit_customer_request(self):
        customer_name = self.customer_name.text.strip()
        customer_class = self.customer_class.text.strip()
        statement_name = self.statement_name.text.strip()

        if not customer_name:
            self.show_message(
                "بيانات ناقصة",
                "اكتب اسم العميل.",
            )
            return

        if customer_class not in CUSTOMER_CLASSES:
            self.show_message(
                "بيانات ناقصة",
                "اختر فئة العميل.",
            )
            return

        if (
            customer_class in STATEMENT_REQUIRED_CLASSES
            and not statement_name
        ):
            self.show_message(
                "بيانات ناقصة",
                "Statement Name مطلوب لهذه الفئة.",
            )
            return

        # Coordinates must come from the phone's location callback.
        if not valid_coordinates(self.gps_lat, self.gps_lon):
            self.show_message(
                "موقع العميل",
                "حدد موقع العميل من GPS قبل إرسال الطلب. "
                "لا يمكن إدخال الإحداثيات يدويًا.",
            )
            return

        if not self.selected_area:
            self.show_message(
                "المنطقة",
                "ابحث عن المنطقة واخترها من النتائج.",
            )
            return

        area = self.selected_area

        if self.role.lower() in (
            "rep",
            "sales rep",
            "retail rep",
        ):
            if not self.salesperson_id:
                self.show_message(
                    "بيانات المندوب",
                    "Salesperson ID غير موجود في بيانات المستخدم.",
                )
                return

            if self.mapping and self.salesperson_id not in self.mapping:
                self.show_message(
                    "بيانات المندوب",
                    "المندوب غير موجود في جدول "
                    "SALESPERSON_MAPPING الحالي.",
                )
                return

        data = {
            "Customer Name": customer_name,
            "Customer Class": customer_class,
            "Statement Name": statement_name,
            "Contact Person": self.contact_person.text.strip(),
            "Address 1": self.address1.text.strip(),
            "Address 2": self.address2.text.strip(),
            "Address 3": get_value(
                area, "Address 3", "Address3", "Area Name", "Area", "Name"
            ),
            "City": get_value(area, "City"),
            "State": get_value(area, "State"),
            "Country Code": get_value(area, "Country Code"),
            "Country": get_value(area, "Country"),
            "Phone 1": self.phone1.text.strip(),
            "Phone 2": self.phone2.text.strip(),
            "Phone 3": self.phone3.text.strip(),
            "LAT": self.gps_lat,
            "LONG": self.gps_lon,
            "RouteID": get_value(area, "RouteID"),
            "المنطقة الكبرى": get_value(
                area, "المنطقة الكبرى", "Major Region"
            ),
            "Area": get_value(area, "Area"),
            "Salesperson ID": self.salesperson_id,
            "Photos": self.photos,
        }

        payload = {
            "action": "submitRequest",
            "token": self.token,
            "data": data,
        }

        self.run_api(
            payload,
            self.on_request_submitted,
            message="جاري إرسال طلب تسجيل العميل...",
        )

    def on_request_submitted(self, result):
        self.stop_gps()

        self.show_message(
            "تم إرسال الطلب",
            "تم إرسال الطلب إلى النظام. "
            "راجع حالة الطلب من شاشة «طلباتي».",
        )

        self.sm.current = "home"

    # -----------------------------------------------------
    # MY REQUESTS
    # -----------------------------------------------------

    def load_my_requests(self):
        self.load_requests(
            action="myRequests",
            title="طلباتي",
        )

    def load_review_requests(self):
        self.load_requests(
            action="listRequests",
            title="مراجعة الطلبات",
        )

    def load_requests(self, action, title):
        payload = {
            "action": action,
            "token": self.token,
        }

        self.run_api(
            payload,
            lambda result: self.display_requests(result, title, action),
            message="جاري تحميل الطلبات...",
        )

    def display_requests(self, result, title, action):
        data = result.get("data", result) if isinstance(result, dict) else {}

        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get(
                "requests",
                data.get("records", data.get("data", [])),
            )
        else:
            records = []

        self.current_requests = [
            row for row in records
            if isinstance(row, dict)
        ]

        self.requests_screen.clear_widgets()

        root = BoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(8),
        )

        root.add_widget(
            Label(
                text=title,
                font_size=sp(22),
                size_hint_y=None,
                height=dp(50),
                color=(0.08, 0.36, 0.65, 1),
            )
        )

        scroll = ScrollView()
        list_layout = BoxLayout(
            orientation="vertical",
            spacing=dp(8),
            size_hint_y=None,
        )
        list_layout.bind(
            minimum_height=list_layout.setter("height")
        )

        for row in self.current_requests:
            request_id = get_value(
                row,
                "Request ID",
                "RequestID",
                "requestId",
            )

            name = get_value(
                row,
                "Customer Name",
                "CustomerName",
            )

            customer_class = get_value(
                row,
                "Customer Class",
                "CustomerClass",
            )

            status = get_value(row, "Status", "status")
            submitted = get_value(
                row,
                "Submitted At",
                "SubmittedAt",
            )

            card = BoxLayout(
                orientation="vertical",
                padding=dp(10),
                spacing=dp(5),
                size_hint_y=None,
                height=dp(180 if action == "listRequests" else 125),
            )

            card.add_widget(
                Label(
                    text=(
                        f"رقم الطلب: {request_id}\n"
                        f"اسم العميل: {name}\n"
                        f"الفئة: {customer_class}\n"
                        f"الحالة: {status}\n"
                        f"تاريخ الطلب: {submitted}"
                    ),
                    halign="left",
                    valign="middle",
                    color=(0.1, 0.1, 0.1, 1),
                )
            )

            if action == "listRequests":
                buttons = GridLayout(
                    cols=2,
                    spacing=dp(5),
                    size_hint_y=None,
                    height=dp(75),
                )

                buttons.add_widget(
                    self.make_button(
                        "موافقة",
                        lambda rid=request_id: self.review_request(
                            rid, "approve"
                        ),
                        height=34,
                    )
                )

                buttons.add_widget(
                    self.make_button(
                        "إرجاع للتعديل",
                        lambda rid=request_id: self.review_request(
                            rid, "return"
                        ),
                        height=34,
                    )
                )

                buttons.add_widget(
                    self.make_button(
                        "رفض",
                        lambda rid=request_id: self.review_request(
                            rid, "reject"
                        ),
                        height=34,
                    )
                )

                if self.role.lower() == "central admin":
                    buttons.add_widget(
                        self.make_button(
                            "تم الترميز",
                            lambda rid=request_id, st=status:
                            self.review_request(
                                rid,
                                "coded",
                                current_status=st,
                            ),
                            height=34,
                        )
                    )

                card.add_widget(buttons)

            list_layout.add_widget(card)

        if not self.current_requests:
            list_layout.add_widget(
                Label(
                    text="لا توجد طلبات.",
                    size_hint_y=None,
                    height=dp(60),
                )
            )

        scroll.add_widget(list_layout)
        root.add_widget(scroll)

        root.add_widget(
            self.make_button(
                "تحديث",
                lambda: self.load_requests(action, title),
            )
        )

        root.add_widget(
            self.make_button("رجوع", self.back_home)
        )

        self.requests_screen.add_widget(root)
        self.sm.current = "requests"

    # -----------------------------------------------------
    # REVIEW REQUESTS
    # -----------------------------------------------------

    def review_request(self, request_id, action_name, current_status=""):
        if not request_id:
            self.show_message(
                "خطأ",
                "رقم الطلب غير موجود.",
            )
            return

        if action_name == "coded":
            if self.role.lower() != "central admin":
                self.show_message(
                    "صلاحيات",
                    "عملية الترميز متاحة لـ Central Admin فقط.",
                )
                return

            if str(current_status).strip().lower() != "approved":
                self.show_message(
                    "الحالة",
                    "يمكن ترميز الطلب بعد الموافقة عليه فقط.",
                )
                return

            self.open_review_dialog(
                request_id,
                action_name,
                need_customer_number=True,
                need_notes=False,
            )

        elif action_name in ("return", "reject"):
            self.open_review_dialog(
                request_id,
                action_name,
                need_customer_number=False,
                need_notes=True,
            )

        else:
            self.open_review_dialog(
                request_id,
                action_name,
                need_customer_number=False,
                need_notes=False,
            )

    def open_review_dialog(
        self,
        request_id,
        action_name,
        need_customer_number=False,
        need_notes=False,
    ):
        content = BoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(8),
        )

        notes_input = TextInput(
            hint_text="ملاحظات",
            multiline=True,
            size_hint_y=None,
            height=dp(90),
        )

        customer_number_input = TextInput(
            hint_text="Customer Number",
            multiline=False,
            size_hint_y=None,
            height=dp(45),
        )

        if need_notes:
            content.add_widget(
                Label(
                    text="اكتب سبب الإرجاع أو الرفض",
                    size_hint_y=None,
                    height=dp(35),
                )
            )
            content.add_widget(notes_input)

        if need_customer_number:
            content.add_widget(
                Label(
                    text="أدخل رقم العميل بعد الترميز",
                    size_hint_y=None,
                    height=dp(35),
                )
            )
            content.add_widget(customer_number_input)

        buttons = BoxLayout(
            size_hint_y=None,
            height=dp(45),
            spacing=dp(8),
        )

        popup = Popup(
            title=f"طلب رقم {request_id}",
            content=content,
            size_hint=(0.9, 0.55),
            auto_dismiss=False,
        )

        def submit_action(*_):
            notes = notes_input.text.strip()
            customer_number = customer_number_input.text.strip()

            if need_notes and not notes:
                self.show_message(
                    "ملاحظات مطلوبة",
                    "اكتب سبب الإرجاع أو الرفض.",
                )
                return

            if need_customer_number and not customer_number:
                self.show_message(
                    "رقم العميل مطلوب",
                    "أدخل Customer Number.",
                )
                return

            popup.dismiss()

            payload = {
                "action": "actOnRequest",
                "token": self.token,
                "requestId": request_id,
                "actionName": action_name,
                "notes": notes,
                "customerNumber": customer_number,
            }

            self.run_api(
                payload,
                lambda result: self.on_review_completed(result),
                message="جاري تحديث الطلب...",
            )

        buttons.add_widget(
            Button(text="تنفيذ", on_release=submit_action)
        )

        buttons.add_widget(
            Button(text="إلغاء", on_release=popup.dismiss)
        )

        content.add_widget(buttons)
        popup.open()

    def on_review_completed(self, result):
        self.show_message(
            "تم تحديث الطلب",
            "تم إرسال الإجراء إلى النظام.",
        )

        Clock.schedule_once(
            lambda dt: self.load_review_requests(),
            0.3,
        )


# =========================================================
# FONT HELPER
# =========================================================

def sp(value):
    from kivy.metrics import sp as kivy_sp
    return kivy_sp(value)


if __name__ == "__main__":
    TakweedApp().run()