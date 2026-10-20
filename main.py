
# -*- coding: utf-8 -*-
import os
import json
import base64
import mimetypes
import threading
import time

import requests
import arabic_reshaper
from bidi.algorithm import get_display

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.utils import platform
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.resources import resource_add_path

from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup

from kivy.graphics import Color, RoundedRectangle, Rectangle


# =========================================================
# SETTINGS
# =========================================================

API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbzjpc555-5YWzUDNTAqaQ2xQP4F7C9FKNm3vbrQp80B_FuSxHQf0NdMvWRpb5gHX9Xvnw/exec"
)

CUSTOMER_CLASSES = [
    "DG-WS-NW", "DG-SVS-DC", "DG-RT-NR", "DG-SVS-SW",
    "DG-SVS-KR", "DG-MT-KSM", "DG-MT-PS", "DG-MT-KA",
    "FB-RT", "NDT-VEN", "NDT-INS", "CC-KA", "CC-RT",
    "CC-DS", "NDT-RT", "CC-WS", "PL-DG", "DG-EC-OEM",
    "DG-EC-OED", "NDT-CON", "DG-WS-KW", "CC-DRI",
    "DG-PC-PHA", "CC-CS", "FB-WS", "FB-SDS", "CC-OEM",
    "NDT-OED", "FB-DS",
]

STATEMENT_REQUIRED_CLASSES = {
    "DG-RT-NR",
    "FB-RT",
    "CC-RT",
    "NDT-RT",
}

MAX_PHOTO_SIZE = 8 * 1024 * 1024
GPS_TIMEOUT_SECONDS = 35

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "assets", "fonts")
ARABIC_FONT = os.path.join(FONT_DIR, "NotoNaskhArabic.ttf")

FONT_NAME = "Roboto"

if os.path.isfile(ARABIC_FONT):
    resource_add_path(FONT_DIR)
    try:
        LabelBase.register(
            name="TakweedArabic",
            fn_regular=ARABIC_FONT,
        )
        FONT_NAME = "TakweedArabic"
    except Exception as exc:
        print("Arabic font registration failed:", exc)

THEMES = {
    "light": {
        "bg": (0.96, 0.96, 0.985, 1),
        "card": (1, 1, 1, 1),
        "text": (0.12, 0.12, 0.20, 1),
        "muted": (0.40, 0.42, 0.50, 1),
        "primary": (0.39, 0.25, 0.83, 1),
        "secondary": (0.05, 0.66, 0.62, 1),
        "accent": (0.88, 0.23, 0.32, 1),
        "input": (0.95, 0.95, 0.98, 1),
        "border": (0.84, 0.85, 0.90, 1),
    },
    "dark": {
        "bg": (0.075, 0.075, 0.12, 1),
        "card": (0.13, 0.13, 0.20, 1),
        "text": (0.95, 0.94, 1, 1),
        "muted": (0.70, 0.70, 0.78, 1),
        "primary": (0.58, 0.43, 0.98, 1),
        "secondary": (0.12, 0.78, 0.75, 1),
        "accent": (0.90, 0.28, 0.38, 1),
        "input": (0.17, 0.17, 0.25, 1),
        "border": (0.28, 0.28, 0.37, 1),
    },
}


# =========================================================
# GENERAL HELPERS
# =========================================================

def arabic_display(value):
    """
    معالجة النصوص المعروضة فقط.
    لا تستخدم الدالة على بيانات API أو قيم TextInput.
    """
    text = str(value if value is not None else "")
    try:
        if not any("\u0600" <= char <= "\u06ff" for char in text):
            return text

        return get_display(
            arabic_reshaper.reshape(text),
            base_dir="R",
        )
    except Exception:
        return text


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
    except (TypeError, ValueError):
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
        raise Exception(
            "استجابة Google Apps Script ليست JSON صالحًا."
        )

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
# VISUAL WIDGETS
# =========================================================

class RoundedPanel(BoxLayout):

    def __init__(self, bg_color=None, radius=18, **kwargs):
        super().__init__(**kwargs)

        self.radius = dp(radius)

        with self.canvas.before:
            self._color = Color(
                *(bg_color or THEMES["light"]["card"])
            )
            self._shape = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[self.radius],
            )

        self.bind(
            pos=self._update_shape,
            size=self._update_shape,
        )

    def set_background(self, color):
        self._color.rgba = color

    def _update_shape(self, *_):
        self._shape.pos = self.pos
        self._shape.size = self.size


class AppButton(Button):

    def __init__(self, app=None, kind="primary", **kwargs):
        self.app_ref = app
        self.kind = kind

        super().__init__(**kwargs)

        self.background_normal = ""
        self.background_down = ""
        self.background_disabled_normal = ""
        self.background_color = (0, 0, 0, 0)

        self.font_name = FONT_NAME
        self.font_size = dp(15)
        self.bold = True
        self.halign = "center"
        self.valign = "middle"
        self.padding = [dp(10), dp(8)]

        self._radius = dp(15)

        with self.canvas.before:
            self._bg_color = Color(
                0.39, 0.25, 0.83, 1
            )
            self._bg_shape = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[self._radius],
            )

        self.bind(
            pos=self._update_bg,
            size=self._update_bg,
            state=self._update_state,
        )

        self.apply_theme()

    def apply_theme(self):
        if not self.app_ref:
            return

        colors = self.app_ref.colors

        if self.kind == "secondary":
            bg = colors["secondary"]
            fg = (0.02, 0.12, 0.13, 1)

        elif self.kind == "accent":
            bg = colors["accent"]
            fg = (1, 1, 1, 1)

        elif self.kind == "neutral":
            bg = colors["border"]
            fg = colors["text"]

        else:
            bg = colors["primary"]
            fg = (1, 1, 1, 1)

        self._bg_color.rgba = bg
        self.color = fg

    def _update_bg(self, *_):
        self._bg_shape.pos = self.pos
        self._bg_shape.size = self.size

    def _update_state(self, *_):
        self.opacity = 0.78 if self.state == "down" else 1


class SectionTitle(Label):

    def __init__(self, app=None, **kwargs):
        self.app_ref = app
        super().__init__(**kwargs)

        self.font_name = FONT_NAME
        self.font_size = dp(17)
        self.bold = True
        self.halign = "left"
        self.valign = "middle"

        if app:
            self.color = app.colors["text"]


class WidgetSpacer(BoxLayout):

    def __init__(self, height=dp(8), **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            height=height,
            **kwargs,
        )


# =========================================================
# MAIN APP
# =========================================================

class TakweedApp(App):

    def build(self):
        self.title = "TAKWEED Customer Coding"

        self.theme_mode = "light"
        self.colors = THEMES[self.theme_mode]

        self.token = ""
        self.user = {}
        self.role = ""
        self.salesperson_id = ""

        self.mapping = {}
        self.salesperson_mapping_row = {}

        self.areas = []
        self.selected_area = None
        self.photos = []
        self.current_requests = []

        self.gps_lat = None
        self.gps_lon = None
        self.gps_accuracy = None
        self.gps_started = False
        self.gps_timeout_event = None

        Window.clearcolor = self.colors["bg"]

        self.sm = ScreenManager()

        self.login_screen = Screen(name="login")
        self.home_screen = Screen(name="home")
        self.form_screen = Screen(name="customer_form")
        self.requests_screen = Screen(name="requests")

        for screen in (
            self.login_screen,
            self.home_screen,
            self.form_screen,
            self.requests_screen,
        ):
            self.sm.add_widget(screen)

        self.build_login_screen()
        self.build_home_screen()
        self.build_customer_form()

        self.sm.current = "login"

        return self.sm

    # -----------------------------------------------------
    # UI HELPERS
    # -----------------------------------------------------

    def make_label(
        self,
        text,
        size=16,
        height=dp(38),
        color=None,
        align="left",
    ):
        label = Label(
            text=arabic_display(text),
            size_hint_y=None,
            height=height,
            font_name=FONT_NAME,
            font_size=dp(size),
            color=color or self.colors["text"],
            halign=align,
            valign="middle",
        )

        label.bind(
            size=lambda obj, value: setattr(
                obj,
                "text_size",
                (max(value[0] - dp(8), 0), None),
            )
        )

        return label

    def make_button(
        self,
        text,
        callback,
        height=50,
        kind="primary",
    ):
        button = AppButton(
            app=self,
            kind=kind,
            text=arabic_display(text),
            size_hint_y=None,
            height=dp(height),
        )

        button.bind(
            on_release=lambda *_: callback()
        )

        return button

    def make_input(
        self,
        hint,
        password=False,
        multiline=False,
    ):
        return TextInput(
            hint_text=hint,
            password=password,
            multiline=multiline,
            size_hint_y=None,
            height=dp(46 if not multiline else 90),
            font_name=FONT_NAME,
            font_size=dp(15),
            padding=[dp(12), dp(12)],
            background_normal="",
            background_active="",
            background_color=self.colors["input"],
            foreground_color=self.colors["text"],
            cursor_color=self.colors["primary"],
            hint_text_color=self.colors["muted"],
            selection_color=(
                *self.colors["primary"][:3],
                0.35,
            ),
        )

    def make_spinner(self, values, text="اختر"):
        return Spinner(
            text=text,
            values=values,
            size_hint_y=None,
            height=dp(46),
            font_name=FONT_NAME,
            font_size=dp(14),
            background_normal="",
            background_color=self.colors["input"],
            color=self.colors["text"],
        )

    def add_card(self, parent, padding=14, spacing=8):
        card = RoundedPanel(
            orientation="vertical",
            padding=dp(padding),
            spacing=dp(spacing),
            size_hint_y=None,
            bg_color=self.colors["card"],
        )

        card.bind(
            minimum_height=card.setter("height")
        )

        parent.add_widget(card)
        return card

    def show_message(self, title, message):
        content = RoundedPanel(
            orientation="vertical",
            spacing=dp(12),
            padding=dp(16),
            bg_color=self.colors["card"],
        )

        label = Label(
            text=arabic_display(message),
            font_name=FONT_NAME,
            color=self.colors["text"],
            halign="center",
            valign="middle",
        )

        label.bind(
            size=lambda obj, value: setattr(
                obj, "text_size", value
            )
        )

        content.add_widget(label)

        popup = Popup(
            title=arabic_display(title),
            title_font=FONT_NAME,
            title_color=self.colors["text"],
            separator_color=self.colors["primary"],
            content=content,
            size_hint=(0.88, 0.42),
            auto_dismiss=False,
        )

        content.add_widget(
            self.make_button(
                "تمام",
                popup.dismiss,
                kind="secondary",
            )
        )

        popup.open()

    def show_loading(self, message="جاري التنفيذ..."):
        content = RoundedPanel(
            orientation="vertical",
            padding=dp(20),
            spacing=dp(10),
            bg_color=self.colors["card"],
        )

        content.add_widget(
            Label(
                text=arabic_display(message),
                font_name=FONT_NAME,
                color=self.colors["text"],
                halign="center",
            )
        )

        popup = Popup(
            title="TAKWEED",
            title_font=FONT_NAME,
            title_color=self.colors["text"],
            separator_color=self.colors["primary"],
            content=content,
            size_hint=(0.82, 0.25),
            auto_dismiss=False,
        )

        popup.open()
        return popup

    def run_api(
        self,
        payload,
        on_success,
        on_error=None,
        message="جاري الاتصال...",
    ):
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
                error = str(exc)

                Clock.schedule_once(
                    lambda dt: self.fail_api(
                        popup, on_error, error
                    ),
                    0,
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def finish_api(self, popup, callback, result):
        if popup:
            popup.dismiss()

        if callback:
            callback(result)

    def fail_api(self, popup, callback, error):
        if popup:
            popup.dismiss()

        if callback:
            callback(error)
        else:
            self.show_message("خطأ", error)

    def add_header(self, layout, title, subtitle=""):
        header = RoundedPanel(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(4),
            size_hint_y=None,
            height=dp(100 if subtitle else 72),
            bg_color=self.colors["primary"],
        )

        for text, size, color in (
            (title, 22, (1, 1, 1, 1)),
            (subtitle, 13, (0.94, 0.92, 1, 1)),
        ):
            if not text:
                continue

            label = Label(
                text=arabic_display(text),
                font_name=FONT_NAME,
                font_size=dp(size),
                bold=size > 18,
                color=color,
                halign="left",
                valign="middle",
            )

            label.bind(
                size=lambda obj, value: setattr(
                    obj,
                    "text_size",
                    (value[0], None),
                )
            )

            header.add_widget(label)

        layout.add_widget(header)

    def make_theme_button(self):
        return self.make_button(
            "تغيير المظهر: فاتح / داكن",
            self.toggle_theme,
            height=42,
            kind="neutral",
        )

    # -----------------------------------------------------
    # THEME
    # -----------------------------------------------------

    def toggle_theme(self):
        self.theme_mode = (
            "dark" if self.theme_mode == "light" else "light"
        )
        self.colors = THEMES[self.theme_mode]
        Window.clearcolor = self.colors["bg"]

        current = self.sm.current

        for screen in (
            self.login_screen,
            self.home_screen,
            self.form_screen,
            self.requests_screen,
        ):
            screen.clear_widgets()

        self.build_login_screen()
        self.build_home_screen()
        self.build_customer_form()

        if current == "requests":
            self.load_my_requests()
        else:
            self.sm.current = current

        if current == "home":
            self.update_home_screen()

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    def build_login_screen(self):
        root = BoxLayout(
            orientation="vertical",
            padding=dp(22),
            spacing=dp(14),
        )

        with root.canvas.before:
            Color(*self.colors["bg"])
            bg_rect = Rectangle(
                pos=root.pos,
                size=root.size,
            )

        root.bind(
            pos=lambda obj, value: setattr(bg_rect, "pos", value),
            size=lambda obj, value: setattr(bg_rect, "size", value),
        )

        root.add_widget(WidgetSpacer(dp(20)))

        logo = RoundedPanel(
            orientation="vertical",
            padding=dp(18),
            spacing=dp(6),
            size_hint_y=None,
            height=dp(155),
            bg_color=self.colors["primary"],
        )

        logo.add_widget(
            Label(
                text="TAKWEED",
                font_name=FONT_NAME,
                font_size=dp(30),
                bold=True,
                color=(1, 1, 1, 1),
            )
        )

        logo.add_widget(
            Label(
                text="Customer Coding",
                font_size=dp(15),
                color=(0.94, 0.92, 1, 1),
            )
        )

        root.add_widget(logo)

        card = RoundedPanel(
            orientation="vertical",
            padding=dp(18),
            spacing=dp(10),
            size_hint_y=None,
            height=dp(265),
            bg_color=self.colors["card"],
        )

        card.add_widget(
            self.make_label("أهلاً بيك", size=22, height=dp(42))
        )

        card.add_widget(
            self.make_label(
                "سجّل دخولك للمتابعة",
                size=14,
                height=dp(28),
                color=self.colors["muted"],
            )
        )

        card.add_widget(self.make_label("اسم المستخدم"))
        self.username_input = self.make_input("Username")
        card.add_widget(self.username_input)

        card.add_widget(self.make_label("كلمة المرور"))
        self.password_input = self.make_input(
            "Password",
            password=True,
        )
        card.add_widget(self.password_input)

        card.add_widget(
            self.make_button("دخول", self.login, height=48)
        )

        root.add_widget(card)
        root.add_widget(self.make_theme_button())
        root.add_widget(WidgetSpacer(dp(10)))

        self.login_screen.add_widget(root)

    def login(self):
        username = self.username_input.text.strip()
        password = self.password_input.text

        if not username or not password:
            self.show_message(
                "بيانات ناقصة",
                "أدخل اسم المستخدم وكلمة المرور.",
            )
            return

        self.run_api(
            {
                "action": "login",
                "username": username,
                "password": password,
            },
            self.on_login_success,
            message="جاري تسجيل الدخول...",
        )

    def on_login_success(self, result):
        data = (
            result.get("data", result)
            if isinstance(result, dict)
            else {}
        )

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
                "الاستجابة لم تحتوِ على Token. راجع API.",
            )
            return

        self.update_home_screen()
        self.sm.current = "home"

        if self.is_rep():
            self.load_salesperson_mapping()

    def is_rep(self):
        return self.role.strip().lower() in (
            "rep", "sales rep", "retail rep"
        )

    # -----------------------------------------------------
    # HOME
    # -----------------------------------------------------

    def build_home_screen(self):
        root = BoxLayout(
            orientation="vertical",
            padding=dp(16),
            spacing=dp(12),
        )

        self.add_header(
            root,
            "TAKWEED",
            "إدارة طلبات تسجيل العملاء",
        )

        root.add_widget(self.make_theme_button())

        self.home_title = self.make_label(
            "مرحباً بك",
            size=18,
            height=dp(58),
        )
        root.add_widget(self.home_title)

        self.home_buttons = BoxLayout(
            orientation="vertical",
            spacing=dp(12),
        )
        root.add_widget(self.home_buttons)
        root.add_widget(WidgetSpacer(1))

        root.add_widget(
            self.make_button(
                "تسجيل الخروج",
                self.logout,
                kind="accent",
            )
        )

        self.home_screen.add_widget(root)

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

        self.home_title.text = arabic_display(
            f"أهلاً {username}\nالصلاحية: {self.role}"
        )

        if self.is_rep():
            self.home_buttons.add_widget(
                self.make_button(
                    "تسجيل عميل جديد",
                    self.open_customer_form,
                    height=62,
                )
            )
            self.home_buttons.add_widget(
                self.make_button(
                    "طلباتي",
                    self.load_my_requests,
                    height=62,
                    kind="secondary",
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
                    height=62,
                    kind="secondary",
                )
            )

        else:
            self.home_buttons.add_widget(
                self.make_button(
                    "طلباتي",
                    self.load_my_requests,
                    height=62,
                    kind="secondary",
                )
            )
            self.home_buttons.add_widget(
                self.make_button(
                    "مراجعة الطلبات",
                    self.load_review_requests,
                    height=62,
                )
            )

    def logout(self):
        self.stop_gps()
        self.token = ""
        self.user = {}
        self.role = ""
        self.salesperson_id = ""
        self.mapping = {}
        self.salesperson_mapping_row = {}
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
        data = (
            result.get("data", result)
            if isinstance(result, dict)
            else {}
        )

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

        for row in records if isinstance(records, list) else []:
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

        self.salesperson_mapping_row = self.mapping.get(
            self.salesperson_id, {}
        )

        if self.salesperson_id and not self.salesperson_mapping_row:
            self.show_message(
                "تنبيه",
                "المندوب غير موجود في جدول SALESPERSON_MAPPING الحالي.",
            )

    def apply_salesperson_mapping(self):
        self.salesperson_mapping_row = self.mapping.get(
            normalize_salesperson_id(self.salesperson_id),
            {},
        )

        statement = get_value(
            self.salesperson_mapping_row,
            "Statement Name",
            "StatementName",
            "statementName",
        )

        if str(statement).strip():
            self.statement_name.text = str(statement).strip()

    # -----------------------------------------------------
    # CUSTOMER FORM
    # -----------------------------------------------------

    def build_customer_form(self):
        scroll = ScrollView()

        self.form_layout = BoxLayout(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(12),
            size_hint_y=None,
        )

        self.form_layout.bind(
            minimum_height=self.form_layout.setter("height")
        )

        self.add_header(
            self.form_layout,
            "عميل جديد",
            "أدخل البيانات الأساسية ثم أرسل الطلب للمراجعة",
        )

        self.form_layout.add_widget(self.make_theme_button())

        card = self.add_card(self.form_layout)
        card.add_widget(
            SectionTitle(
                app=self,
                text="بيانات العميل",
                size_hint_y=None,
                height=dp(35),
            )
        )

        self.customer_name = self.make_input("اسم العميل")
        card.add_widget(self.make_label("Customer Name"))
        card.add_widget(self.customer_name)

        self.customer_class = self.make_spinner(
            CUSTOMER_CLASSES,
            "اختر Customer Class",
        )
        card.add_widget(self.make_label("Customer Class"))
        card.add_widget(self.customer_class)

        self.statement_name = self.make_input("Statement Name")
        card.add_widget(self.make_label("Statement Name"))
        card.add_widget(self.statement_name)

        self.contact_person = self.make_input("Contact Person")
        card.add_widget(self.make_label("Contact Person"))
        card.add_widget(self.contact_person)

        card = self.add_card(self.form_layout)
        card.add_widget(
            SectionTitle(
                app=self,
                text="العنوان والمنطقة",
                size_hint_y=None,
                height=dp(35),
            )
        )

        self.address1 = self.make_input("Address 1")
        self.address2 = self.make_input("Address 2")

        card.add_widget(self.make_label("Address 1"))
        card.add_widget(self.address1)
        card.add_widget(self.make_label("Address 2"))
        card.add_widget(self.address2)

        self.area_search = self.make_input(
            "اكتب اسم المنطقة للبحث"
        )
        card.add_widget(self.make_label("ابحث عن المنطقة"))
        card.add_widget(self.area_search)

        card.add_widget(
            self.make_button(
                "بحث عن المنطقة",
                self.search_area,
                kind="secondary",
            )
        )

        self.area_spinner = self.make_spinner(
            [],
            "اختر المنطقة",
        )
        self.area_spinner.bind(text=self.on_area_selected)
        card.add_widget(self.area_spinner)

        card = self.add_card(self.form_layout)
        card.add_widget(
            SectionTitle(
                app=self,
                text="أرقام التواصل",
                size_hint_y=None,
                height=dp(35),
            )
        )

        self.phone1 = self.make_input("Phone 1")
        self.phone2 = self.make_input("Phone 2")
        self.phone3 = self.make_input("Phone 3")

        for title, field in (
            ("Phone 1", self.phone1),
            ("Phone 2", self.phone2),
            ("Phone 3", self.phone3),
        ):
            card.add_widget(self.make_label(title))
            card.add_widget(field)

        card = self.add_card(self.form_layout)
        card.add_widget(
            SectionTitle(
                app=self,
                text="موقع العميل",
                size_hint_y=None,
                height=dp(35),
            )
        )

        self.gps_status = self.make_label(
            "لم يتم تحديد الموقع بعد",
            size=14,
            height=dp(50),
            color=self.colors["muted"],
            align="center",
        )
        card.add_widget(self.gps_status)

        card.add_widget(
            self.make_button(
                "تحديد الموقع الحالي GPS",
                self.get_current_location,
                height=52,
                kind="secondary",
            )
        )

        self.lat_input = self.make_input("LAT")
        self.lon_input = self.make_input("LONG")
        self.lat_input.readonly = True
        self.lon_input.readonly = True

        card.add_widget(self.make_label("LAT"))
        card.add_widget(self.lat_input)
        card.add_widget(self.make_label("LONG"))
        card.add_widget(self.lon_input)

        card = self.add_card(self.form_layout)
        card.add_widget(
            SectionTitle(
                app=self,
                text="صور المحل",
                size_hint_y=None,
                height=dp(35),
            )
        )

        self.photo_status = self.make_label(
            "لم يتم اختيار صور",
            size=14,
            height=dp(38),
            color=self.colors["muted"],
        )
        card.add_widget(self.photo_status)

        card.add_widget(
            self.make_button(
                "إضافة صورة للمحل",
                self.pick_photo,
                kind="secondary",
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
                "رجوع للرئيسية",
                self.back_home,
                kind="neutral",
            )
        )

        self.form_layout.add_widget(WidgetSpacer(dp(12)))

        scroll.add_widget(self.form_layout)
        self.form_screen.add_widget(scroll)

    def open_customer_form(self):
        self.stop_gps()

        for field in (
            self.customer_name,
            self.contact_person,
            self.address1,
            self.address2,
            self.area_search,
            self.phone1,
            self.phone2,
            self.phone3,
            self.lat_input,
            self.lon_input,
        ):
            field.text = ""

        self.customer_class.text = "اختر Customer Class"
        self.statement_name.text = ""
        self.area_spinner.values = []
        self.area_spinner.text = "اختر المنطقة"

        self.selected_area = None
        self.photos = []

        self.photo_status.text = arabic_display(
            "لم يتم اختيار صور"
        )

        self.gps_lat = None
        self.gps_lon = None
        self.gps_accuracy = None

        self.gps_status.text = arabic_display(
            "لم يتم تحديد الموقع بعد"
        )

        self.apply_salesperson_mapping()
        self.sm.current = "customer_form"

    def back_home(self):
        self.stop_gps()
        self.sm.current = "home"

    # -----------------------------------------------------
    # GPS
    # -----------------------------------------------------

    def get_current_location(self):
        if platform != "android":
            self.show_message(
                "GPS",
                "تحديد الموقع الفعلي يحتاج تجربة التطبيق على هاتف Android.",
            )
            return

        if self.gps_started:
            self.gps_status.text = arabic_display(
                "جاري انتظار إحداثيات الموقع..."
            )
            return

        try:
            from android.permissions import (
                request_permissions,
                Permission,
            )

            request_permissions(
                [
                    Permission.ACCESS_FINE_LOCATION,
                    Permission.ACCESS_COARSE_LOCATION,
                ],
                self.on_location_permissions,
            )

        except Exception as exc:
            self.show_message(
                "GPS",
                "تعذر طلب صلاحية الموقع: " + str(exc),
            )

    def on_location_permissions(self, permissions, grants):
        if not grants or not any(grants):
            Clock.schedule_once(
                lambda dt: self.show_message(
                    "صلاحية الموقع",
                    "اسمح للتطبيق بالوصول إلى الموقع من إعدادات الهاتف.",
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

            self.gps_status.text = arabic_display(
                "جاري تحديد الموقع... فعّل الموقع وانتظر"
            )

            self.gps_started = True
            self.gps_timeout_event = Clock.schedule_once(
                self.gps_timeout,
                GPS_TIMEOUT_SECONDS,
            )

            gps.configure(
                on_location=self.on_gps_location,
                on_status=self.on_gps_status,
            )

            gps.start(
                minTime=1000,
                minDistance=0,
            )

        except Exception as exc:
            self.gps_started = False
            self.cancel_gps_timeout()
            self.show_message(
                "GPS",
                "تعذر تشغيل GPS. تأكد من تفعيل خدمة الموقع.\n"
                + str(exc),
            )

    def gps_timeout(self, *_):
        if self.gps_lat is None or self.gps_lon is None:
            self.stop_gps()

            self.gps_status.text = arabic_display(
                "لم يصل الموقع خلال 35 ثانية. فعّل GPS ثم حاول مرة أخرى."
            )

            self.show_message(
                "انتهت مهلة GPS",
                "لم يصل موقع صالح خلال 35 ثانية. فعّل الموقع، "
                "جرّب مكانًا مفتوحًا، ثم أعد المحاولة.",
            )

    def cancel_gps_timeout(self):
        if self.gps_timeout_event is not None:
            try:
                self.gps_timeout_event.cancel()
            except Exception:
                pass

            self.gps_timeout_event = None

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
            lambda dt: self.set_gps_status(message),
            0,
        )

    def set_gps_status(self, message):
        if hasattr(self, "gps_status"):
            self.gps_status.text = arabic_display(message)

    def update_gps_fields(self, lat, lon, accuracy):
        if not valid_coordinates(lat, lon):
            self.gps_status.text = arabic_display(
                "الإحداثيات غير صالحة، جاري المحاولة مرة أخرى"
            )
            return

        try:
            accuracy = (
                float(accuracy)
                if accuracy is not None
                else None
            )
        except (TypeError, ValueError):
            accuracy = None

        self.gps_lat = lat
        self.gps_lon = lon
        self.gps_accuracy = accuracy

        self.lat_input.text = f"{lat:.7f}"
        self.lon_input.text = f"{lon:.7f}"

        self.cancel_gps_timeout()
        self.stop_gps()

        if accuracy is not None:
            message = (
                "تم تحديد الموقع بنجاح\n"
                f"الدقة التقريبية: {accuracy:.1f} متر"
            )
        else:
            message = "تم تحديد الموقع بنجاح"

        self.gps_status.text = arabic_display(message)

    def stop_gps(self):
        self.cancel_gps_timeout()

        if self.gps_started:
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

        self.run_api(
            {
                "action": "searchArea",
                "token": self.token,
                "query": query,
            },
            self.on_areas_loaded,
            message="جاري البحث عن المنطقة...",
        )

    def on_areas_loaded(self, result):
        data = (
            result.get("data", result)
            if isinstance(result, dict)
            else {}
        )

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
                return

        if text in (
            "اختر المنطقة",
            "اختر المنطقة من النتائج",
            "لا توجد نتائج",
        ):
            self.selected_area = None

    # -----------------------------------------------------
    # PHOTO PICKER
    # -----------------------------------------------------

    def pick_photo(self):
        try:
            from plyer import filechooser

            filechooser.open_file(
                on_selection=self.on_photo_selected,
                filters=[
                    [
                        "Image files",
                        "*.png",
                        "*.jpg",
                        "*.jpeg",
                        "*.webp",
                    ]
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

        try:
            if not os.path.isfile(path):
                self.show_message(
                    "الصور",
                    "تعذر الوصول إلى ملف الصورة المختار.",
                )
                return

            if os.path.getsize(path) > MAX_PHOTO_SIZE:
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

            self.photos.append({
                "fileName": os.path.basename(path),
                "mimeType": mime_type,
                "base64": encoded,
            })

            self.photo_status.text = arabic_display(
                f"تم اختيار {len(self.photos)} صورة"
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
            self.show_message("بيانات ناقصة", "اكتب اسم العميل.")
            return

        if customer_class not in CUSTOMER_CLASSES:
            self.show_message("بيانات ناقصة", "اختر فئة العميل.")
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

        if not valid_coordinates(self.gps_lat, self.gps_lon):
            self.show_message(
                "موقع العميل",
                "حدد موقع العميل من GPS قبل إرسال الطلب.",
            )
            return

        if not self.selected_area:
            self.show_message(
                "المنطقة",
                "ابحث عن المنطقة واخترها من النتائج.",
            )
            return

        if self.is_rep():
            if not self.salesperson_id:
                self.show_message(
                    "بيانات المندوب",
                    "Salesperson ID غير موجود في بيانات المستخدم.",
                )
                return

            if (
                not self.mapping
                or self.salesperson_id not in self.mapping
            ):
                self.show_message(
                    "بيانات المندوب",
                    "المندوب غير موجود في جدول SALESPERSON_MAPPING الحالي.",
                )
                return

        area = self.selected_area
        mapping_row = self.mapping.get(
            self.salesperson_id,
            {},
        )

        data = {
            "Customer Name": customer_name,
            "Customer Class": customer_class,
            "Statement Name": statement_name,
            "Contact Person": self.contact_person.text.strip(),
            "Address 1": self.address1.text.strip(),
            "Address 2": self.address2.text.strip(),
            "Address 3": get_value(
                area,
                "Address 3",
                "Address3",
                "Area Name",
                "Area",
                "Name",
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
                area,
                "المنطقة الكبرى",
                "Major Region",
            ),
            "Area": get_value(area, "Area"),
            "Salesperson ID": self.salesperson_id,
            "Sales Territory": get_value(
                mapping_row, "Sales Territory"
            ),
            "User Defined 1": get_value(
                mapping_row, "User Defined 1"
            ),
            "User Defined 2": get_value(
                mapping_row, "User Defined 2"
            ),
            "Comment1": get_value(mapping_row, "Comment1"),
            "Comment2": get_value(mapping_row, "Comment2"),
            "Photos": self.photos,
        }

        self.run_api(
            {
                "action": "submitRequest",
                "token": self.token,
                "data": data,
            },
            self.on_request_submitted,
            message="جاري إرسال طلب تسجيل العميل...",
        )

    def on_request_submitted(self, result):
        self.stop_gps()

        self.show_message(
            "تم إرسال الطلب",
            "تم إرسال الطلب إلى النظام. راجع حالة الطلب من شاشة طلباتي.",
        )

        self.sm.current = "home"

    # -----------------------------------------------------
    # REQUESTS
    # -----------------------------------------------------

    def load_my_requests(self):
        self.load_requests(
            "myRequests",
            "طلباتي",
        )

    def load_review_requests(self):
        self.load_requests(
            "listRequests",
            "مراجعة الطلبات",
        )

    def load_requests(self, action, title):
        self.run_api(
            {
                "action": action,
                "token": self.token,
            },
            lambda result: self.display_requests(
                result,
                title,
                action,
            ),
            message="جاري تحميل الطلبات...",
        )

    def display_requests(self, result, title, action):
        data = (
            result.get("data", result)
            if isinstance(result, dict)
            else {}
        )

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
            padding=dp(14),
            spacing=dp(10),
        )

        self.add_header(
            root,
            title,
            "تابع حالة الطلبات والإجراءات المطلوبة",
        )

        root.add_widget(self.make_theme_button())

        scroll = ScrollView()

        listing = BoxLayout(
            orientation="vertical",
            spacing=dp(10),
            size_hint_y=None,
        )

        listing.bind(
            minimum_height=listing.setter("height")
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

            card = RoundedPanel(
                orientation="vertical",
                padding=dp(12),
                spacing=dp(6),
                size_hint_y=None,
                bg_color=self.colors["card"],
            )

            card.bind(
                minimum_height=card.setter("height")
            )

            card.add_widget(
                self.make_label(
                    f"طلب رقم {request_id}",
                    size=17,
                    height=dp(30),
                )
            )

            card.add_widget(
                self.make_label(
                    f"العميل: {name}",
                    size=14,
                    height=dp(30),
                )
            )

            card.add_widget(
                self.make_label(
                    f"الفئة: {customer_class}",
                    size=13,
                    height=dp(28),
                    color=self.colors["muted"],
                )
            )

            card.add_widget(
                self.make_label(
                    f"الحالة: {status}",
                    size=14,
                    height=dp(30),
                    color=self.colors["secondary"],
                )
            )

            if submitted:
                card.add_widget(
                    self.make_label(
                        f"تاريخ الطلب: {submitted}",
                        size=12,
                        height=dp(26),
                        color=self.colors["muted"],
                    )
                )

            if action == "listRequests":
                buttons = GridLayout(
                    cols=2,
                    spacing=dp(6),
                    size_hint_y=None,
                    height=dp(92),
                )

                buttons.add_widget(
                    self.make_button(
                        "موافقة",
                        lambda rid=request_id: self.review_request(
                            rid, "approve"
                        ),
                        height=42,
                        kind="secondary",
                    )
                )

                buttons.add_widget(
                    self.make_button(
                        "إرجاع للتعديل",
                        lambda rid=request_id: self.review_request(
                            rid, "return"
                        ),
                        height=42,
                        kind="neutral",
                    )
                )

                buttons.add_widget(
                    self.make_button(
                        "رفض",
                        lambda rid=request_id: self.review_request(
                            rid, "reject"
                        ),
                        height=42,
                        kind="accent",
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
                            height=42,
                        )
                    )

                card.add_widget(buttons)

            listing.add_widget(card)

        if not self.current_requests:
            listing.add_widget(
                self.make_label(
                    "لا توجد طلبات حالياً",
                    size=16,
                    height=dp(70),
                    align="center",
                )
            )

        scroll.add_widget(listing)
        root.add_widget(scroll)

        root.add_widget(
            self.make_button(
                "تحديث القائمة",
                lambda: self.load_requests(action, title),
                kind="secondary",
            )
        )

        root.add_widget(
            self.make_button(
                "رجوع للرئيسية",
                self.back_home,
                kind="neutral",
            )
        )

        self.requests_screen.add_widget(root)
        self.sm.current = "requests"

    # -----------------------------------------------------
    # REVIEW REQUESTS
    # -----------------------------------------------------

    def review_request(
        self,
        request_id,
        action_name,
        current_status="",
    ):
        if not request_id:
            self.show_message("خطأ", "رقم الطلب غير موجود.")
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
            )

        elif action_name in ("return", "reject"):
            self.open_review_dialog(
                request_id,
                action_name,
                need_notes=True,
            )

        else:
            self.open_review_dialog(
                request_id,
                action_name,
            )

    def open_review_dialog(
        self,
        request_id,
        action_name,
        need_customer_number=False,
        need_notes=False,
    ):
        content = RoundedPanel(
            orientation="vertical",
            padding=dp(14),
            spacing=dp(10),
            bg_color=self.colors["card"],
        )

        notes_input = self.make_input(
            "اكتب الملاحظات هنا",
            multiline=True,
        )

        number_input = self.make_input(
            "Customer Number"
        )

        if need_notes:
            content.add_widget(
                self.make_label("سبب الإرجاع أو الرفض")
            )
            content.add_widget(notes_input)

        if need_customer_number:
            content.add_widget(
                self.make_label("رقم العميل بعد الترميز")
            )
            content.add_widget(number_input)

        buttons = BoxLayout(
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )

        popup = Popup(
            title=arabic_display(f"طلب رقم {request_id}"),
            title_font=FONT_NAME,
            title_color=self.colors["text"],
            separator_color=self.colors["primary"],
            content=content,
            size_hint=(0.92, 0.55),
            auto_dismiss=False,
        )

        def submit_action(*_):
            notes = notes_input.text.strip()
            customer_number = number_input.text.strip()

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

            self.run_api(
                {
                    "action": "actOnRequest",
                    "token": self.token,
                    "requestId": request_id,
                    "actionName": action_name,
                    "notes": notes,
                    "customerNumber": customer_number,
                },
                self.on_review_completed,
                message="جاري تحديث الطلب...",
            )

        buttons.add_widget(
            self.make_button(
                "تنفيذ",
                submit_action,
                height=44,
                kind="secondary",
            )
        )

        buttons.add_widget(
            self.make_button(
                "إلغاء",
                popup.dismiss,
                height=44,
                kind="neutral",
            )
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


if __name__ == "__main__":
    TakweedApp().run()
