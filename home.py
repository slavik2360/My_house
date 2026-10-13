import sys
import os
import re
import json
import math
import random
import hashlib
import secrets
import sqlite3
from datetime import datetime, date, timedelta

import PyQt5
_QT5_PLUGINS_DIR = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", os.path.join(_QT5_PLUGINS_DIR, "platforms"))
os.environ.setdefault("QT_PLUGIN_PATH", _QT5_PLUGINS_DIR)

from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *


def _user_data_dir():
    """Папка для базы данных - стандартная пользовательская папка данных (как в main.py)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")

    data_dir = os.path.join(base, "SmartSolarHome")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


# Папка программы. В собранном .exe (PyInstaller) картинки планировок лежат внутри самого файла
# (sys._MEIPASS), а снимки камер и свои фото комнат - рядом с SmartHome.exe.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
    RESOURCE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR = RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))

# v2: у устройств появились модель и настройки - старая база (smart_home.db) не подходит по схеме
DB_PATH = os.path.join(_user_data_dir(), "smart_home_v2.db")

####################################
######### КОНСТАНТЫ ДОМА ###########
####################################

# Временно: вход без логина и пароля (сразу открывается дом AUTO_LOGIN_USER).
# Чтобы вернуть окно авторизации - поставить SKIP_AUTH = False.
SKIP_AUTH = False
AUTO_LOGIN_USER = "Вячеслав"

# Учётные записи, которые создаются при первом запуске
DEFAULT_USERS = ["Вячеслав", "Иван", "Николай"]
DEFAULT_PASSWORD = "1234"

# Этажи дома: код, название, короткая подпись во вкладке комнаты
FLOORS = [("floor1", "1 этаж", "1 эт."), ("floor2", "2 этаж", "2 эт."), ("site", "Участок", "участок")]
FLOOR_NAMES = {code: name for code, name, _ in FLOORS}
FLOOR_SHORT = {code: short for code, _, short in FLOORS}

# Комнаты, которые получает каждый новый пользователь (по планировке 1floor.png)
DEFAULT_ROOMS = ["Гостиная", "Спальня", "Кухня", "Прихожая", "Гараж", "Терраса"]

# Стартовый дом Вячеслава (создаётся при первом запуске): дополнительные комнаты и устройства
# (комната, модель, название, включено, настройки). Иван и Николай начинают с пустого дома.
SEED_USER = "Вячеслав"
SEED_EXTRA_ROOMS = ['Ванная']
SEED_DEVICES = [
    ('Гостиная', 'xiaomi_g10', 'Пылесос', 1, {"mode": "Эко", "plan": {"floor": "floor1", "x": 0.431, "y": 0.304}}),
    ('Гостиная', 'aqara_g3', 'Видеокамера', 1, {"night_vision": True, "recording": True, "motion_alerts": True, "plan": {"floor": "floor1", "x": 0.67, "y": 0.384}}),
    ('Гостиная', 'aqara_g4', 'Дверной звонок', 1, {"volume": 40, "motion_alerts": True, "plan": {"floor": "floor1", "x": 0.613, "y": 0.257}}),
    ('Гостиная', 'aqara_smoke', 'Датчик дыма', 1, {"battery": 97, "plan": {"floor": "floor1", "x": 0.774, "y": 0.325}}),
    ('Гостиная', 'midea_breezeless', 'Кондиционер', 1, {"target_temp": 27, "mode": "Вентиляция", "fan_speed": 3, "led": True, "plan": {"floor": "floor1", "x": 0.531, "y": 0.403}}),
    ('Гостиная', 'yeelight_w3', 'Лампочка', 1, {"brightness": 80, "color_temp": 3700, "color": "#48dbfb", "plan": {"floor": "floor1", "x": 0.739, "y": 0.555}}),
    ('Спальня', 'roborock_s8', 'Робот-пылесос', 0, {"mode": "Турбо", "vac_battery": 100.0, "plan": {"floor": "floor2", "x": 0.768, "y": 0.711}, "vac_state": "docked", "vac_progress": 0.0, "vac_return": 0.0}),
    ('Спальня', 'aqara_g3', 'Видеокамера', 1, {"night_vision": True, "recording": True, "motion_alerts": True, "plan": {"floor": "floor2", "x": 0.715, "y": 0.243}}),
    ('Кухня', 'mi_heater_s', 'Обогреватель', 1, {"target_temp": 26, "mode": "Эко", "child_lock": True}),
    ('Кухня', 'mi_kettle_2pro', 'Электрический чайник', 0, {"target_temp": 60, "keep_warm": False, "led": True, "water_ml": 1700, "water_temp": 22.0, "plan": {"floor": "floor1", "x": 0.761, "y": 0.701}}),
    ('Прихожая', 'aqara_leak', 'Датчик протечки', 1, {"battery": 93, "plan": {"floor": "floor1", "x": 0.232, "y": 0.299}}),
    ('Гараж', 'aqara_g3', 'Видеокамера', 1, {"night_vision": False, "recording": True, "motion_alerts": True, "plan": {"floor": "floor1", "x": 0.172, "y": 0.42}}),
    ('Терраса', 'crmcr_x1', 'Сейф', 1, {"locked": True, "battery": 92, "plan": {"floor": "floor1", "x": 0.7, "y": 0.09}}),
    ('Терраса', 'aqara_g3', 'Видеокамера', 1, {"night_vision": True, "recording": True, "motion_alerts": True, "plan": {"floor": "floor1", "x": 0.847, "y": 0.116}}),
    ('Ванная', 'midea_wd10', 'Стиральная машина', 0, {"mode": "Шерсть", "child_lock": True, "wash_elapsed": 0.0}),
]

# Параметры системы альтернативного питания
BATTERY_CAPACITY_WH = 30000     # ёмкость аккумулятора, Вт·ч (30 кВт·ч)
SOLAR_PEAK_W = 6000             # пиковая мощность солнечных панелей, Вт (6 кВт)
MAX_CHARGE_W = 6000             # максимальная мощность заряда аккумулятора, Вт
BASE_LOAD_W = 120               # фоновое потребление дома (без умных устройств), Вт
BATTERY_RESERVE = 0.10          # ниже этого уровня дом переключается на внешнюю сеть
GRID_VOLTAGE = 230              # для расчёта мощности зарядки электромобиля по току

# Скорости симуляции: (подпись, сколько минут модельного времени проходит за 1 секунду)
SIM_SPEEDS = [
    ("Реальное время", 1 / 60),
    ("1 мин / сек", 1),
    ("10 мин / сек", 10),
]

####################################
####### КАТАЛОГ УСТРОЙСТВ ##########
####################################

# Типы устройств по группам: (код, название, иконка)
DEVICE_GROUPS = [
    ("Бытовая техника для уборки", [
        ("washer", "Стиральная машина", "🧺"),
        ("robot_vacuum", "Робот-пылесос", "🤖"),
        ("floor_washer", "Машина для мытья полов", "🧽"),
        ("vacuum", "Пылесос", "🧹"),
    ]),
    ("Бытовая безопасность", [
        ("camera", "Видеокамера", "📹"),
        ("doorbell", "Дверной звонок", "🔔"),
        ("door_lock", "Дверной замок", "🔐"),
        ("safe", "Сейф", "🗄️"),
    ]),
    ("Датчики", [
        ("temp_sensor", "Датчик температуры", "🌡️"),
        ("presence_sensor", "Датчик присутствия", "👤"),
        ("smoke_sensor", "Датчик дыма", "🚨"),
        ("door_sensor", "Датчик окон / дверей", "🚪"),
        ("leak_sensor", "Датчик протечки", "💧"),
        ("light_sensor", "Датчик освещённости", "🔆"),
        ("motion_sensor", "Датчик движения", "🏃"),
    ]),
    ("Развлечения", [
        ("speaker", "Умная колонка", "🔊"),
        ("tv", "Телевизор", "📺"),
    ]),
    ("Климат и очистка воздуха", [
        ("humidifier", "Увлажнитель", "💨"),
        ("heater", "Обогреватель", "🔥"),
        ("aroma", "Аромараспылитель", "🌸"),
        ("air_conditioner", "Кондиционер", "❄️"),
        ("fan", "Вентилятор", "🌀"),
        ("air_purifier", "Очиститель воздуха", "🍃"),
        ("dehumidifier", "Осушитель воздуха", "♒"),
    ]),
    ("Маршрутизаторы и шлюзы", [
        ("router", "Маршрутизатор", "📶"),
        ("gateway", "Шлюз", "🛰️"),
        ("repeater", "Усилитель Wi-Fi", "📡"),
    ]),
    ("Освещение", [
        ("light_strip", "Световая лента", "🌈"),
        ("desk_lamp", "Настольная лампа", "🪔"),
        ("bedside_lamp", "Прикроватная лампа", "🛏️"),
        ("ceiling_light", "Потолочный светильник", "💡"),
        ("spot_light", "Точечный светильник", "🔦"),
        ("bulb", "Лампочка", "💡"),
        ("night_light", "Ночник", "🌙"),
    ]),
    ("Переключатели питания", [
        ("socket", "Умная розетка", "🔌"),
        ("switch", "Выключатель", "🎚️"),
        ("remote", "Беспроводной пульт", "🎛️"),
        ("panel", "Панель управления", "📟"),
    ]),
    ("Кухонная электроника", [
        ("water_dispenser", "Диспенсер для воды", "🚰"),
        ("air_fryer", "Аэрофритюрница", "🍟"),
        ("multicooker", "Мультиварка", "🍲"),
        ("fridge", "Холодильник", "🧊"),
        ("microwave", "Микроволновая печь", "♨️"),
        ("kettle", "Электрический чайник", "☕"),
        ("dishwasher", "Посудомоечная машина", "🍽️"),
    ]),
    ("Альтернативная энергетика", [
        ("inverter", "Солнечный инвертор", "☀️"),
        ("battery_bms", "Контроллер аккумулятора", "🔋"),
        ("ev_charger", "Зарядка электромобиля", "🚗"),
        ("water_heater", "Бойлер (нагрев воды)", "🛁"),
    ]),
]

DEVICE_TYPES = {
    code: {"name": name, "icon": icon, "group": group}
    for group, items in DEVICE_GROUPS
    for code, name, icon in items
}

# Группы, устройства которых должны работать постоянно: включаются сразу после добавления
# и не выключаются сценариями «выключить всё»
ALWAYS_ON_GROUPS = {"Бытовая безопасность", "Датчики", "Маршрутизаторы и шлюзы"}
ALWAYS_ON_TYPES = {"fridge", "inverter", "battery_bms"}
LIGHT_GROUP = "Освещение"

# Доля времени, которую устройство реально потребляет номинальную мощность, пока оно включено.
# Холодильник, кондиционер, обогреватель и т.п. работают циклами по термостату, чайник
# вскипает и отключается - без этого симуляция считала бы всё на полной мощности 24/7.
DUTY_CYCLE = {
    "dehumidifier": 0.5,
    "water_dispenser": 0.3,
    "air_fryer": 0.6,
    "multicooker": 0.3,
    "fridge": 0.35,
    "microwave": 0.3,
    "dishwasher": 0.3,
    "ev_charger": 0.6,
    "water_heater": 0.3,
}

# Режимы работы по типам: (название, множитель потребляемой мощности)
TYPE_MODES = {
    "washer": [("Хлопок 60°", 1.0), ("Быстрая 30 мин", 0.6), ("Деликатная", 0.5), ("Шерсть", 0.5), ("Эко 40-60", 0.4)],
    "robot_vacuum": [("Стандарт", 1.0), ("Тихий", 0.6), ("Турбо", 1.5)],
    "floor_washer": [("Стандарт", 1.0), ("Интенсивный", 1.4), ("Самоочистка", 0.7)],
    "vacuum": [("Стандарт", 1.0), ("Эко", 0.5), ("Турбо", 1.6)],
    "air_conditioner": [("Охлаждение", 1.0), ("Обогрев", 1.1), ("Осушение", 0.6), ("Вентиляция", 0.15), ("Авто", 0.9)],
    "heater": [("Комфорт", 0.75), ("Эко", 0.5), ("Максимум", 1.0)],
    "humidifier": [("Авто", 0.8), ("Сон", 0.5), ("Максимум", 1.0)],
    "air_purifier": [("Авто", 0.7), ("Сон", 0.3), ("Ручной", 1.0)],
    "fan": [("Прямой поток", 1.0), ("Естественный ветер", 0.8), ("Сон", 0.5)],
    "dehumidifier": [("Авто", 0.8), ("Сушка белья", 1.0), ("Тихий", 0.6)],
    "aroma": [("Непрерывно", 1.0), ("Интервал 30 сек", 0.5)],
    "tv": [("Smart TV", 1.0), ("HDMI 1", 1.0), ("HDMI 2", 1.0), ("Эфирное ТВ", 1.0)],
    "multicooker": [("Варка", 1.0), ("Тушение", 0.6), ("Выпечка", 0.9), ("Плов", 0.8), ("Йогурт", 0.15), ("Подогрев", 0.1)],
    "air_fryer": [("Картофель фри", 1.0), ("Курица", 1.0), ("Выпечка", 0.8), ("Разогрев", 0.5)],
    "microwave": [("Разогрев", 1.0), ("Разморозка", 0.4), ("Гриль", 1.1)],
    "dishwasher": [("Авто", 1.0), ("Эко", 0.7), ("Быстрая", 0.9), ("Интенсивная", 1.2)],
    "water_dispenser": [("Холодная вода", 1.0), ("Комнатная", 0.2), ("Горячая вода", 1.3)],
    "fridge": [("Обычный", 1.0), ("Отпуск", 0.6), ("Суперзаморозка", 1.4)],
    "water_heater": [("Комфорт", 1.0), ("Эко", 0.6), ("Турбо", 1.3)],
}

# Термостат по типам: (минимум, максимум, по умолчанию)
TYPE_TEMP = {
    "air_conditioner": (16, 30, 22),
    "heater": (5, 35, 25),
    "kettle": (40, 100, 90),
    "fridge": (1, 8, 4),
    "water_heater": (30, 75, 55),
    "air_fryer": (80, 200, 180),
}

L_BASIC = "brightness timer"
L_WHITE = "brightness color_temp timer"
L_COLOR = "brightness color_temp color timer"


def _m(code, name, power, caps="", desc="", **extra):
    return dict(code=code, name=name, power=power, caps=caps.split(), desc=desc, **extra)


# Модели устройств для каждого типа: мощность (Вт) и набор функций (caps) у каждой модели свои
CATALOG = {
    "washer": [
        _m("mijia_washer_8", "Xiaomi Mijia Smart Washer 8 кг", 2000, "mode timer", "Фронтальная загрузка, 1400 об/мин"),
        _m("haier_hw80", "Haier HW80 Smart", 2100, "mode timer child_lock", "Инверторный мотор, обработка паром"),
        _m("midea_wd10", "Midea Washer-Dryer 10/7 кг", 2200, "mode timer child_lock", "Стирка и сушка в одном корпусе"),
    ],
    "robot_vacuum": [
        _m("xiaomi_s10", "Xiaomi Robot Vacuum S10", 40, "mode timer", "Лазерная навигация, сухая уборка"),
        _m("roborock_s8", "Roborock S8", 55, "mode timer", "Сухая и влажная уборка, LiDAR"),
        _m("dreame_l10s", "Dreame L10s Ultra", 60, "mode timer", "База самоочистки, автоопорожнение"),
    ],
    "floor_washer": [
        _m("dreame_h12", "Dreame H12", 250, "mode", "Влажная и сухая уборка, сушка валика"),
        _m("tineco_s5", "Tineco Floor One S5", 220, "mode", "Датчик загрязнения iLoop"),
    ],
    "vacuum": [
        _m("xiaomi_g10", "Xiaomi Vacuum Cleaner G10", 450, "mode", "Беспроводной, до 65 минут работы"),
        _m("dreame_v12", "Dreame V12", 500, "mode", "Лазерная подсветка пыли"),
        _m("dyson_v15", "Dyson V15 Detect", 660, "mode", "Датчик частиц, LCD-экран"),
    ],
    "camera": [
        _m("xiaomi_c200", "Xiaomi Smart Camera C200", 5, "video night_vision recording motion_alerts",
           "Поворотная 360°, 1080p", ptz=True, resolution="1080p"),
        _m("xiaomi_aw300", "Xiaomi Outdoor Camera AW300", 6, "video night_vision recording motion_alerts",
           "Уличная, IP66, 2K, широкий угол", resolution="2K"),
        _m("aqara_g3", "Aqara Camera Hub G3", 6, "video night_vision recording motion_alerts",
           "Поворотная камера + Zigbee-шлюз, 2K", ptz=True, resolution="2K"),
    ],
    "doorbell": [
        _m("xiaomi_bell3", "Xiaomi Smart Doorbell 3", 3, "video volume motion_alerts",
           "Видеозвонок 2K, обнаружение людей", resolution="2K", outdoor=True),
        _m("aqara_g4", "Aqara Video Doorbell G4", 4, "video volume motion_alerts",
           "Распознавание лиц, локальное хранение", resolution="1080p", outdoor=True),
    ],
    "door_lock": [
        _m("xiaomi_e10", "Xiaomi Smart Door Lock E10", 2, "lock auto_lock", "Отпечаток пальца, код, NFC", battery="4×AA"),
        _m("aqara_u200", "Aqara Smart Lock U200", 2, "lock auto_lock", "Apple Home Key, Matter", battery="Li-ion 5000 мА·ч"),
        _m("xiaomi_x_face", "Xiaomi Face Recognition Lock X", 3, "lock auto_lock motion_alerts", "3D-распознавание лица + камера",
           battery="Li-ion 5000 мА·ч"),
    ],
    "safe": [
        _m("xiaomi_safe", "Xiaomi Smart Safe Box", 2, "lock motion_alerts", "Отпечаток пальца, датчик вскрытия", battery="4×AA"),
        _m("crmcr_x1", "Crmcr Smart Safe BGX-X1-30", 2, "lock", "Код + ключ, 30 л", battery="4×AA"),
    ],
    "temp_sensor": [
        _m("mi_th2", "Xiaomi Temperature and Humidity Monitor 2", 0.1, "", "Bluetooth, LCD-экран", battery="CR2032"),
        _m("aqara_t1", "Aqara Temperature and Humidity Sensor T1", 0.1, "", "Zigbee 3.0, давление", battery="CR2032"),
        _m("mi_th_pro", "Xiaomi Temperature Monitor Pro E-Ink", 0.2, "", "Экран E-Ink, часы", battery="2×AAA"),
    ],
    "presence_sensor": [
        _m("aqara_fp2", "Aqara Presence Sensor FP2", 2, "led", "mmWave-радар, до 5 зон, питание USB"),
        _m("xiaomi_presence", "Xiaomi Human Presence Sensor", 1.5, "led", "mmWave-радар, обнаружение дыхания"),
    ],
    "smoke_sensor": [
        _m("mi_smoke", "Xiaomi Smart Smoke Detector", 0.1, "", "Сирена 85 дБ, Bluetooth Mesh", battery="CR17450"),
        _m("aqara_smoke", "Aqara Smart Smoke Detector", 0.1, "", "Zigbee, самотестирование", battery="CR17450"),
    ],
    "door_sensor": [
        _m("mi_door2", "Xiaomi Door and Window Sensor 2", 0.1, "", "Bluetooth, датчик освещённости", battery="CR2032"),
        _m("aqara_p2", "Aqara Door and Window Sensor P2", 0.1, "", "Thread / Matter", battery="CR123A"),
    ],
    "leak_sensor": [
        _m("mi_flood", "Xiaomi Flood Detector", 0.1, "", "IP67, звуковой сигнал", battery="CR2032"),
        _m("aqara_leak", "Aqara Water Leak Sensor", 0.1, "", "Zigbee, IP67", battery="CR2032"),
    ],
    "light_sensor": [
        _m("mi_light", "Xiaomi Light Detection Sensor", 0.1, "", "Диапазон 0–83 000 лк", battery="CR2450"),
        _m("aqara_light_t1", "Aqara Light Sensor T1", 0.1, "", "Zigbee 3.0", battery="CR2450"),
    ],
    "motion_sensor": [
        _m("mi_motion2", "Xiaomi Motion Sensor 2", 0.1, "", "Угол обзора 170°, до 7 м", battery="2×AAA"),
        _m("aqara_p1", "Aqara Motion Sensor P1", 0.1, "", "Настраиваемая чувствительность", battery="2×CR2450"),
        _m("aqara_p2m", "Aqara Motion and Light Sensor P2", 0.1, "", "Thread / Matter + датчик света", battery="2×CR2450"),
    ],
    "speaker": [
        _m("yandex_mini3", "Яндекс Станция Мини 3", 10, "volume timer", "Алиса, управление умным домом"),
        _m("yandex_max", "Яндекс Станция Макс", 65, "volume timer", "Стерео 65 Вт, Zigbee-шлюз, HDMI"),
        _m("xiaomi_sound_pro", "Xiaomi Sound Pro", 30, "volume timer", "Hi-Fi звук, 360°"),
    ],
    "tv": [
        _m("xiaomi_a_pro_43", "Xiaomi TV A Pro 43\"", 80, "mode volume timer", "4K UHD, Google TV"),
        _m("xiaomi_q2_55", "Xiaomi TV Q2 55\"", 120, "mode volume timer", "QLED 4K, Dolby Vision"),
        _m("xiaomi_s_pro_65", "Xiaomi TV S Pro 65\" Mini LED", 180, "mode volume timer", "Mini LED, 144 Гц"),
    ],
    "humidifier": [
        _m("mi_hum2", "Xiaomi Smart Humidifier 2", 28, "mode timer child_lock led", "4.5 л, ультразвуковой, УФ-стерилизация"),
        _m("mi_hum2_lite", "Xiaomi Humidifier 2 Lite", 23, "mode timer", "4 л, бюджетная модель"),
        _m("deerma_f628s", "Deerma F628S", 25, "mode timer led", "5 л, верхний залив воды"),
    ],
    "heater": [
        _m("mi_heater_s", "Xiaomi Smart Space Heater S", 2200, "mode target_temp timer child_lock", "Конвектор, IPX4"),
        _m("mi_baseboard2", "Xiaomi Baseboard Heater 2", 2200, "mode target_temp timer", "Плинтусный, бесшумный"),
        _m("mi_fan_heater", "Xiaomi Fan Heater Lite", 1500, "mode timer", "Тепловентилятор, быстрый нагрев"),
    ],
    "aroma": [
        _m("mi_aroma", "Xiaomi Aroma Diffuser", 5, "mode timer led", "100 мл, подсветка"),
        _m("lofans_aroma", "Lofans Smart Aroma Diffuser", 6, "mode timer", "Ультразвуковой, 120 мл"),
    ],
    "air_conditioner": [
        _m("mijia_ac_9", "Xiaomi Mijia AC 9000 BTU", 800, "mode target_temp fan_speed timer", "До 25 м², инвертор, класс A++",
           levels=5),
        _m("mijia_ac_12", "Xiaomi Mijia AC 12000 BTU", 1100, "mode target_temp fan_speed timer led", "До 35 м², инвертор",
           levels=5),
        _m("midea_breezeless", "Midea Breezeless+ 18000 BTU", 1650, "mode target_temp fan_speed timer led",
           "До 50 м², режим «без сквозняка»", levels=7),
    ],
    "fan": [
        _m("mi_fan2", "Xiaomi Smart Standing Fan 2", 15, "mode fan_speed timer", "BLDC-мотор, 100 скоростей", levels=4),
        _m("mi_tower", "Xiaomi Smart Tower Fan", 22, "mode fan_speed timer led", "Колонный, 22 Вт", levels=4),
        _m("mi_fan2_lite", "Xiaomi Standing Fan 2 Lite", 38, "mode fan_speed timer", "Бюджетный, 3 скорости", levels=3),
    ],
    "air_purifier": [
        _m("mi_ap4_compact", "Xiaomi Air Purifier 4 Compact", 27, "mode fan_speed timer", "До 27 м², HEPA H13", levels=3),
        _m("mi_ap4", "Xiaomi Air Purifier 4", 30, "mode fan_speed timer child_lock led", "До 48 м², OLED-экран", levels=3),
        _m("mi_ap4_pro", "Xiaomi Air Purifier 4 Pro", 50, "mode fan_speed timer child_lock led", "До 60 м², датчик PM2.5",
           levels=5),
        _m("mi_ap_elite", "Xiaomi Air Purifier Elite", 66, "mode fan_speed timer child_lock led", "До 125 м², формальдегид",
           levels=5),
    ],
    "dehumidifier": [
        _m("mi_dehum_lite", "Xiaomi Smart Dehumidifier Lite", 240, "mode timer child_lock", "13 л/сутки"),
        _m("mi_dehum_22", "Xiaomi Smart Dehumidifier 22L", 370, "mode timer child_lock led", "22 л/сутки, сушка белья"),
    ],
    "router": [
        _m("mi_ax3000t", "Xiaomi Router AX3000T", 12, "guest_wifi led", "Wi-Fi 6, 3000 Мбит/с"),
        _m("mi_mesh_ax3000", "Xiaomi Mesh System AX3000", 15, "guest_wifi led", "Mesh-система, 2 модуля"),
        _m("mi_be7000", "Xiaomi Router BE7000", 30, "guest_wifi led", "Wi-Fi 7, 10G-порт"),
    ],
    "gateway": [
        _m("mi_hub2", "Xiaomi Smart Home Hub 2", 4, "led", "Zigbee 3.0 + Bluetooth Mesh"),
        _m("aqara_m2", "Aqara Hub M2", 3, "led", "Zigbee 3.0, ИК-пульт"),
        _m("aqara_m3", "Aqara Hub M3", 5, "led", "Matter-контроллер, Thread"),
    ],
    "repeater": [
        _m("mi_ext_ac1200", "Xiaomi Wi-Fi Range Extender AC1200", 6, "led", "Двухдиапазонный, Ethernet-порт"),
        _m("mi_ext_pro", "Xiaomi Wi-Fi Range Extender Pro", 4, "led", "300 Мбит/с, 2 антенны"),
    ],
    "light_strip": [
        _m("mi_strip", "Xiaomi Smart Lightstrip", 12, L_COLOR, "2 м, 16 млн цветов"),
        _m("yeelight_strip_pro", "Yeelight Lightstrip Pro", 18, L_COLOR, "Градиентные эффекты, синхронизация с музыкой"),
        _m("hue_strip", "Philips Hue Lightstrip Plus", 20, L_COLOR, "2 м, Zigbee, удлиняется"),
    ],
    "desk_lamp": [
        _m("mi_lamp_1s", "Xiaomi LED Desk Lamp 1S", 9, L_WHITE, "Без мерцания, 4 режима освещения"),
        _m("mi_lamp_pro", "Xiaomi Smart LED Desk Lamp Pro", 12, L_WHITE, "Двойной источник света, Ra 95"),
        _m("yeelight_v1_pro", "Yeelight LED Desk Lamp V1 Pro", 8, L_WHITE, "Аккумулятор, складная"),
    ],
    "bedside_lamp": [
        _m("mi_bedside2", "Xiaomi Bedside Lamp 2", 9, L_COLOR, "16 млн цветов, сенсорное управление"),
        _m("yeelight_d2", "Yeelight Bedside Lamp D2", 12, L_COLOR, "Плавный рассвет / закат"),
    ],
    "ceiling_light": [
        _m("mi_ceiling_450", "Xiaomi Ceiling Light 450 мм", 33, L_WHITE, "До 20 м², IP50"),
        _m("yeelight_arwen_450s", "Yeelight Arwen 450S", 50, L_WHITE, "До 25 м², рассеянный свет"),
        _m("yeelight_halo", "Yeelight Halo (с RGB-подсветкой)", 60, L_COLOR, "Основной свет + цветная подсветка"),
    ],
    "spot_light": [
        _m("yeelight_m2", "Yeelight Downlight M2", 5, L_WHITE, "Встраиваемый, 350 лм"),
        _m("aqara_t2", "Aqara Spotlight T2", 7, L_WHITE, "Zigbee, угол луча 24°"),
    ],
    "bulb": [
        _m("mi_bulb_warm", "Xiaomi LED Smart Bulb Warm White", 8, L_BASIC, "E27, только тёплый белый 2700 K"),
        _m("mi_bulb_essential", "Xiaomi Smart LED Bulb Essential", 9, L_WHITE, "E27, белый 1700–6500 K"),
        _m("aqara_bulb_t1", "Aqara LED Bulb T1", 9, L_WHITE, "E27, Zigbee 3.0"),
        _m("yeelight_w3", "Yeelight Smart LED Bulb W3 (цветная)", 8, L_COLOR, "E27, 16 млн цветов"),
        _m("hue_color_e27", "Philips Hue White & Color Ambiance", 9, L_COLOR, "E27, Zigbee / Bluetooth"),
    ],
    "night_light": [
        _m("mi_night2", "Xiaomi Motion-Activated Night Light 2", 1, "brightness motion_light", "Датчик движения и света",
           battery="3×AA"),
        _m("yeelight_plug_night", "Yeelight Plug-in Night Light", 1, "brightness motion_light", "В розетку, датчик освещённости"),
    ],
    "socket": [
        _m("mi_plug2", "Xiaomi Smart Plug 2", 2200, "load timer led", "До 2.2 кВт, учёт электроэнергии"),
        _m("aqara_plug_eu", "Aqara Smart Plug EU", 3680, "load timer led", "До 3.68 кВт, Zigbee"),
        _m("mi_power_strip", "Xiaomi Power Strip (6 розеток)", 2500, "load timer", "6 розеток + 3 USB"),
    ],
    "switch": [
        _m("aqara_h1_1", "Aqara Wall Switch H1 (1 клавиша)", 0.5, "keys led", "Без нейтрали", keys=1),
        _m("aqara_h1_2", "Aqara Wall Switch H1 (2 клавиши)", 0.5, "keys led", "С нейтралью", keys=2),
        _m("mi_switch_3", "Xiaomi Smart Wall Switch (3 клавиши)", 0.5, "keys led", "Bluetooth Mesh", keys=3),
    ],
    "remote": [
        _m("aqara_mini", "Aqara Wireless Mini Switch", 0.1, "scenes", "1 кнопка: клик, двойной клик, удержание",
           battery="CR2032"),
        _m("mi_wireless_sw", "Xiaomi Wireless Switch", 0.1, "scenes", "Компактная кнопка-сценарий", battery="CR2032"),
        _m("aqara_cube", "Aqara Cube T1 Pro", 0.1, "scenes", "Управление жестами: поворот, встряхивание",
           battery="CR2450"),
    ],
    "panel": [
        _m("mi_display_10", "Xiaomi Smart Home Display 10 Pro", 6, "brightness scenes", "10\" сенсорный экран"),
        _m("aqara_s1e", "Aqara Smart Panel S1 E", 4, "brightness scenes", "6\" экран + 3 клавиши"),
    ],
    "water_dispenser": [
        _m("mi_dispenser", "Xiaomi Water Dispenser", 600, "mode child_lock", "Холодная и горячая вода"),
        _m("viomi_kids", "Viomi Smart Water Dispenser", 2000, "mode child_lock", "Мгновенный нагрев, 6 температур"),
    ],
    "air_fryer": [
        _m("mi_fryer_35", "Xiaomi Smart Air Fryer 3.5L", 1500, "mode target_temp timer", "100+ рецептов в приложении"),
        _m("mi_fryer_pro_4", "Xiaomi Smart Air Fryer Pro 4L", 1600, "mode target_temp timer", "Окно просмотра"),
        _m("mi_fryer_6", "Xiaomi Smart Air Fryer 6L", 1800, "mode target_temp timer", "Большая корзина на семью"),
    ],
    "multicooker": [
        _m("mi_multicooker", "Xiaomi Smart Multifunctional Cooker 4L", 1000, "mode timer", "Индукционный нагрев"),
        _m("redmond_m226s", "Redmond SkyCooker M226S", 860, "mode timer", "Ready for Sky, 46 программ"),
    ],
    "fridge": [
        _m("mi_fridge_536", "Xiaomi Mijia Side-by-Side 536 л", 180, "mode target_temp", "Инвертор, No Frost"),
        _m("mi_fridge_450", "Xiaomi Mijia 4-Door 450 л", 160, "mode target_temp", "Отдельная зона свежести"),
        _m("haier_c2f637", "Haier C2F637CXRG", 150, "mode target_temp", "Двухкамерный, класс A+"),
    ],
    "microwave": [
        _m("mi_microwave_20", "Xiaomi Smart Microwave Oven 20L", 1100, "mode timer", "Сенсорная панель"),
        _m("midea_mw_25", "Midea Smart Microwave 25L", 1200, "mode timer child_lock", "Гриль, конвекция"),
    ],
    "kettle": [
        _m("mi_kettle2", "Xiaomi Electric Kettle 2", 1800, "target_temp", "1.7 л, нагрев до заданной температуры",
           capacity_ml=1700),
        _m("mi_kettle_pro", "Xiaomi Smart Kettle Pro", 1800, "target_temp keep_warm", "1.5 л, поддержание до 12 ч",
           capacity_ml=1500),
        _m("mi_kettle_2pro", "Xiaomi Mijia Thermostatic Kettle 2 Pro", 1800, "target_temp keep_warm led",
           "1.7 л, дисплей температуры", capacity_ml=1700),
        _m("redmond_g200s", "Redmond SkyKettle G200S", 2200, "target_temp keep_warm color",
           "1.7 л, стеклянная колба с цветной подсветкой", capacity_ml=1700),
    ],
    "dishwasher": [
        _m("mi_dish_s1", "Xiaomi Mijia Dishwasher S1 (8 комплектов)", 1800, "mode timer child_lock", "Сушка горячим воздухом"),
        _m("midea_dish_14", "Midea Smart Dishwasher (14 комплектов)", 2000, "mode timer child_lock", "Полноразмерная, 3 корзины"),
    ],
    "inverter": [
        _m("huawei_sun2000", "Huawei SUN2000-6KTL", 10, "", "Сетевой инвертор 6 кВт, 2 MPPT"),
        _m("growatt_sph6000", "Growatt SPH 6000", 12, "", "Гибридный, поддержка АКБ"),
        _m("deye_8k", "Deye SUN-8K-SG04LP3", 15, "", "Гибридный 3-фазный 8 кВт"),
    ],
    "battery_bms": [
        _m("huawei_luna", "Huawei LUNA2000 BMS", 5, "", "Модульная система хранения"),
        _m("pylontech_us5000", "Pylontech US5000 BMS", 5, "", "LiFePO4, 6000 циклов"),
    ],
    "ev_charger": [
        _m("teison_16a", "Teison Smart EV Charger 3.7 кВт", 3700, "current solar_only timer", "Однофазная, до 16 А",
           max_current=16),
        _m("wallbox_pulsar", "Wallbox Pulsar Plus 7.4 кВт", 7400, "current solar_only timer", "Однофазная, до 32 А",
           max_current=32),
    ],
    "water_heater": [
        _m("mi_heater_60", "Xiaomi Smart Water Heater 60L", 2000, "mode target_temp solar_only timer", "Эмалированный бак"),
        _m("thermex_id80", "Thermex ID 80 V Smart", 2000, "mode target_temp solar_only timer", "Wi-Fi, сухой ТЭН"),
    ],
}

for _type_code, _models in CATALOG.items():
    for _model in _models:
        _model["type"] = _type_code
MODELS = {model["code"]: model for models in CATALOG.values() for model in models}

CAP_NAMES = {
    "brightness": "яркость", "color_temp": "тёплый/холодный свет", "color": "RGB-цвет",
    "target_temp": "термостат", "mode": "режимы", "fan_speed": "скорости", "volume": "громкость",
    "current": "ток зарядки", "video": "видео онлайн", "load": "учёт нагрузки", "keys": "клавиши", "lock": "замок",
    "keep_warm": "подогрев", "child_lock": "защита от детей", "night_vision": "ночное видение",
    "recording": "запись", "motion_alerts": "оповещения", "auto_lock": "автозакрытие",
    "guest_wifi": "гостевая сеть", "led": "индикатор", "motion_light": "включение по движению",
    "timer": "таймер", "scenes": "сценарии", "solar_only": "от излишков солнца",
}

# Переключатели-настройки: ключ -> подпись в окне управления
BOOL_CAPS = {
    "keep_warm": "Поддержание температуры",
    "child_lock": "Защита от детей",
    "night_vision": "Ночное видение",
    "recording": "Непрерывная запись",
    "motion_alerts": "Уведомления о движении",
    "auto_lock": "Автозакрытие через 30 сек",
    "guest_wifi": "Гостевая сеть Wi-Fi",
    "led": "Световой индикатор",
    "motion_light": "Включение по движению",
    "solar_only": "☀️ Только от излишков солнца",
}

TIMER_OPTIONS = [("Нет", 0), ("15 минут", 15), ("30 минут", 30), ("1 час", 60), ("2 часа", 120), ("4 часа", 240)]

COLOR_PRESETS = ["#ffd27f", "#ff6b6b", "#ff9f43", "#feca57", "#1dd1a1", "#48dbfb", "#5f27cd", "#ff9ff3"]

# Сценарии для пультов и панелей управления: код -> подпись
SCENES = [
    ("room_lights_on", "💡 Включить свет в комнате"),
    ("room_off", "🌙 Выключить всё в комнате"),
    ("house_lights_off", "🏠 Выключить свет во всём доме"),
    ("house_off", "🚪 Ухожу из дома (выключить всё)"),
]


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def is_always_on(type_code):
    return type_code in ALWAYS_ON_TYPES or DEVICE_TYPES[type_code]["group"] in ALWAYS_ON_GROUPS


def default_settings(model):
    """Начальные настройки устройства сразу после добавления (зависят от функций модели)."""
    type_code = model["type"]
    caps = model["caps"]
    s = {}
    if "brightness" in caps:
        s["brightness"] = 80
    if "color_temp" in caps:
        s["color_temp"] = 4000
    if "color" in caps:
        s["color"] = None  # None = белый свет, иначе #rrggbb
    if "target_temp" in caps:
        s["target_temp"] = TYPE_TEMP[type_code][2]
    if "mode" in caps:
        s["mode"] = TYPE_MODES[type_code][0][0]
    if "fan_speed" in caps:
        s["fan_speed"] = max(1, model.get("levels", 3) // 2)
    if "volume" in caps:
        s["volume"] = 40
    if "current" in caps:
        s["current"] = min(16, model["max_current"])
    if "load" in caps:
        s["load"] = 100
    if "keys" in caps:
        s["keys"] = [False] * model.get("keys", 1)
    if "lock" in caps:
        s["locked"] = True
    for key in BOOL_CAPS:
        if key in caps:
            s[key] = key in ("night_vision", "motion_alerts", "auto_lock", "led", "motion_light", "recording")
    if type_code == "robot_vacuum":
        s.update(vac_state="docked", vac_progress=0.0, vac_battery=100.0, vac_return=0.0)
    if type_code == "washer":
        s.update(wash_elapsed=0.0)
    if model.get("battery"):
        s["battery"] = random.randint(62, 100)
    if type_code == "kettle":
        s["water_ml"] = 1000
        s["water_temp"] = 22.0
    return s


def device_power(device, ignore_solar=False):
    """Средняя потребляемая мощность устройства (Вт) с учётом его настроек, состояния и циклов работы."""
    model = MODELS.get(device["model_code"])
    if model is None:
        return 0.0
    s = device["settings"]
    caps = model["caps"]
    type_code = device["type_code"]
    power = model["power"]

    if type_code == "robot_vacuum":
        # робот потребляет и после выключения тумблера: едет на базу и заряжается
        state = s.get("vac_state", "docked")
        if state in ("cleaning", "returning"):
            return power * dict(TYPE_MODES[type_code]).get(s.get("mode"), 1.0)
        if state == "paused":
            return 3.0
        return 25.0 if s.get("vac_battery", 100) < 99.5 else 2.0

    if not device["is_on"]:
        return 0.0
    if s.get("solar_only") and not ignore_solar:
        return device.get("_solar_power", 0.0)

    if type_code == "washer":
        phase = washer_phase(washer_fraction(s))
        if phase == "Нагрев воды":
            return power * dict(TYPE_MODES[type_code]).get(s.get("mode"), 1.0)
        return {"Стирка": 150.0, "Полоскание": 120.0, "Отжим": 450.0}.get(phase, 2.0)

    if type_code == "kettle":
        if kettle_is_heating(device):
            return float(power)
        return power * 0.06 if s.get("keep_warm") else 1.0  # подогрев импульсами / дежурный режим

    if "load" in caps:
        power = s.get("load", 0)
    if "current" in caps:
        power = s.get("current", 16) * GRID_VOLTAGE
    if "brightness" in caps:
        power *= 0.1 + 0.9 * s.get("brightness", 100) / 100
    if "mode" in caps:
        power *= dict(TYPE_MODES[type_code]).get(s.get("mode"), 1.0)
    if "fan_speed" in caps:
        levels = model.get("levels", 3)
        power *= 0.3 + 0.7 * s.get("fan_speed", levels) / levels
    if type_code in ("air_conditioner", "heater") and not device.get("_climate_active", True):
        power *= 0.3  # температура достигнута - компрессор/ТЭН работают в режиме поддержания

    return power * DUTY_CYCLE.get(type_code, 1.0)


def solar_full_power(device):
    """Мощность устройства с режимом «от излишков», если бы оно работало на полную."""
    return device_power(device, ignore_solar=True) / DUTY_CYCLE.get(device["type_code"], 1.0)


# ---------- стиральная машина ----------

WASH_DURATIONS = {"Хлопок 60°": 120, "Быстрая 30 мин": 30, "Деликатная": 60, "Шерсть": 45, "Эко 40-60": 180}
WASH_PHASES = [(0.0, "Нагрев воды"), (0.2, "Стирка"), (0.6, "Полоскание"), (0.85, "Отжим")]


def washer_total(s):
    return WASH_DURATIONS.get(s.get("mode"), 90)


def washer_fraction(s):
    return min(1.0, s.get("wash_elapsed", 0.0) / washer_total(s))


def washer_phase(fraction):
    name = WASH_PHASES[0][1]
    for start, phase in WASH_PHASES:
        if fraction >= start:
            name = phase
    return name


# ---------- робот-пылесос ----------

VAC_CLEAN_MIN = 40       # минут модельного времени на полную уборку в режиме «Стандарт»
VAC_RETURN_MIN = 3       # минут на возврат к базе
VAC_DRAIN = 1.4          # % батареи в минуту уборки
VAC_CHARGE = 2.0         # % батареи в минуту на базе
VAC_LOW_BATTERY = 15


# ---------- климат в комнатах ----------

def room_baseline_temp(sim_minutes):
    """Температура, к которой комната стремится без климатической техники (зависит от времени суток)."""
    hour = (sim_minutes / 60) % 24
    return 22.0 + 3.5 * math.sin(2 * math.pi * (hour - 9) / 24)


# ---------- энергетика: эко-режим, излишки солнца, экономия ----------

DEFAULT_TARIFF_KZT = 28.0    # тариф на электроэнергию для населения, ₸ за кВт·ч (примерно, Казахстан)
CO2_KG_PER_KWH = 0.65        # выбросы CO₂ энергосистемы Казахстана (в основном угольная генерация), кг/кВт·ч
CO2_PER_TREE_KG = 22         # примерно столько CO₂ одно дерево поглощает за год
ECO_OFF_LEVEL = 0.20         # эко-режим отключает второстепенные нагрузки ниже этого заряда
ECO_RESTORE_LEVEL = 0.40     # ... и возвращает их, когда АКБ зарядится до этого уровня
ECO_SHED_TYPES = ["ev_charger", "water_heater", "heater", "dishwasher", "washer", "dehumidifier"]
SOLAR_ONLY_MIN_LEVEL = 0.50  # излишки идут устройствам, только когда АКБ заряжена хотя бы наполовину
EV_MIN_POWER = 6 * GRID_VOLTAGE  # зарядка авто не может работать на токе меньше 6 А

# ---------- история энергии для отчётов ----------

ENERGY_HISTORY_START = date(2025, 1, 1)


def synthetic_energy_history(user_id, devices_count, until):
    """
    Правдоподобная суточная история энергосистемы с ENERGY_HISTORY_START по until включительно:
    {дата: (выработка, потребление, из сети, в сеть) в Вт·ч}. Реальных измерений у учебного дома нет,
    поэтому дни моделируются: летом солнца больше, зимой - отопление, облачность меняется день ото дня,
    аккумулятор переносит заряд из дня в ночь. Ряд детерминирован - при каждом запуске он один и тот же.
    """
    rng = random.Random(f"energy-history-{user_id}")
    battery = BATTERY_CAPACITY_WH * 0.6
    reserve = BATTERY_CAPACITY_WH * BATTERY_RESERVE
    cloud = 0.3
    result = {}
    day = ENERGY_HISTORY_START
    while day <= until:
        doy = day.timetuple().tm_yday
        summer = 0.5 + 0.5 * math.cos(2 * math.pi * (doy - 172) / 365)  # 1 - середина лета, 0 - середина зимы
        cloud = min(0.95, max(0.0, 0.55 * cloud + 0.45 * rng.random() * (1.15 - 0.45 * summer)))
        sun_hours = 1.6 + 4.2 * summer                                   # пиковые солнечные часы за день
        generated = SOLAR_PEAK_W * sun_hours * (1 - 0.75 * cloud)
        base = 5500 + 180 * devices_count                                # освещение, техника, холодильник...
        heating = (1 - summer) ** 1.5 * 9000                             # обогрев зимой
        cooling = max(0.0, summer - 0.6) / 0.4 * 4000                    # кондиционер летом
        weekend = 1.12 if day.weekday() >= 5 else 1.0
        consumed = (base + heating + cooling) * weekend * rng.uniform(0.85, 1.15)
        # днём солнце питает дом напрямую, излишек - в АКБ, остальное в сеть; ночью дом живёт от АКБ
        daytime = consumed * 0.45
        direct = min(generated, daytime)
        surplus = generated - direct
        charge = min(surplus, BATTERY_CAPACITY_WH - battery)
        battery += charge
        need = (daytime - direct) + (consumed - daytime)
        from_battery = min(need, max(0.0, battery - reserve))
        battery -= from_battery
        result[day] = (generated, consumed, need - from_battery, surplus - charge)
        day += timedelta(days=1)
    return result


# Ускорение нагрева чайника относительно реального времени - чтобы на демонстрации
# литр воды закипал примерно за полминуты, а не за 3 минуты
KETTLE_SPEEDUP = 6
ROOM_TEMP = 22.0
MIN_KETTLE_WATER_ML = 150


def kettle_is_heating(device):
    s = device["settings"]
    return (bool(device["is_on"]) and s.get("water_ml", 0) >= MIN_KETTLE_WATER_ML
            and s.get("water_temp", ROOM_TEMP) < s.get("target_temp", 100) - 0.05)


def kettle_step(device, seconds=1.0):
    """
    Один шаг физики чайника. Возвращает "done", если вода нагрелась и чайник надо выключить,
    "empty" - если включили без воды, иначе None.
    Нагрев: dT = P·t / (m·c), c = 4186 Дж/(кг·°C). Остывание - по закону Ньютона.
    """
    s = device["settings"]
    model = MODELS[device["model_code"]]
    water_kg = s.get("water_ml", 0) / 1000
    temp = s.get("water_temp", ROOM_TEMP)
    target = s.get("target_temp", 100)

    if device["is_on"] and water_kg * 1000 < MIN_KETTLE_WATER_ML:
        return "empty"
    if kettle_is_heating(device):
        temp += model["power"] * seconds * KETTLE_SPEEDUP / (water_kg * 4186)
        s["water_temp"] = min(target, temp)
        if s["water_temp"] >= target - 0.05 and not s.get("keep_warm"):
            return "done"
    elif device["is_on"] and s.get("keep_warm"):
        s["water_temp"] = target
    else:
        s["water_temp"] = temp - (temp - ROOM_TEMP) * 0.004 * seconds
    return None


def sim_time_text(sim_minutes):
    return "%02d:%02d" % (int(sim_minutes // 60) % 24, int(sim_minutes % 60))


####################################
############ БАЗА ДАННЫХ ###########
####################################

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000).hex()


class Database:
    """Единая точка доступа к пользователям, комнатам и устройствам (SQLite)."""

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super(Database, cls).__new__(cls)
        return cls.instance

    def __init__(self, path=DB_PATH):
        if getattr(self, "_initialized", False):
            return
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._initialized = True
        self.create_tables()
        self.seed_data()

    def create_tables(self):
        self.conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                login_key TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                battery_wh REAL NOT NULL DEFAULT {BATTERY_CAPACITY_WH * 0.65}
            );

            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                floor TEXT NOT NULL DEFAULT 'floor1'
            );

            CREATE TABLE IF NOT EXISTS energy_days (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                day TEXT NOT NULL,
                generated_wh REAL NOT NULL,
                consumed_wh REAL NOT NULL,
                import_wh REAL NOT NULL,
                export_wh REAL NOT NULL,
                simulated INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, day)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                sim_time TEXT NOT NULL,
                category TEXT NOT NULL,
                icon TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                type_code TEXT NOT NULL,
                model_code TEXT NOT NULL,
                name TEXT NOT NULL,
                is_on INTEGER NOT NULL DEFAULT 0,
                settings TEXT NOT NULL DEFAULT '{{}}',
                created_at TEXT NOT NULL
            );
        """)
        self.conn.commit()
        self.migrate()

    USER_COLUMNS = {
        "eco_mode": "INTEGER NOT NULL DEFAULT 1",
        "tariff_kzt": f"REAL NOT NULL DEFAULT {DEFAULT_TARIFF_KZT}",
        "total_generated_wh": "REAL NOT NULL DEFAULT 0",
        "total_import_wh": "REAL NOT NULL DEFAULT 0",
        "total_export_wh": "REAL NOT NULL DEFAULT 0",
        "seed_version": "INTEGER NOT NULL DEFAULT 0",
    }

    def migrate(self):
        """Добавить новые столбцы в уже существующую базу (без потери данных)."""
        existing = {row["name"] for row in self.conn.execute("PRAGMA table_info(users)")}
        for column, ddl in self.USER_COLUMNS.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE users ADD COLUMN {column} {ddl}")
        # у комнат появился этаж: для старых комнат определяем его по названию
        room_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(rooms)")}
        if "floor" not in room_columns:
            self.conn.execute("ALTER TABLE rooms ADD COLUMN floor TEXT NOT NULL DEFAULT 'floor1'")
            for room in self.conn.execute("SELECT id, name FROM rooms").fetchall():
                self.conn.execute("UPDATE rooms SET floor = ? WHERE id = ?", (room_zone(room["name"])[0], room["id"]))
        self.conn.commit()

    SEED_VERSION = 1

    def seed_data(self):
        for username in DEFAULT_USERS:
            if self.get_user(username) is None:
                self.create_user(username, DEFAULT_PASSWORD)
        # Стартовые устройства досыпаются и в базу, созданную старой версией программы
        user = self.get_user(SEED_USER)
        if user["seed_version"] < self.SEED_VERSION:
            self._seed_home(user["id"])
            self.conn.execute("UPDATE users SET seed_version = ? WHERE id = ?", (self.SEED_VERSION, user["id"]))
            self.conn.commit()

    def _seed_home(self, user_id):
        existing_rooms = {room["name"] for room in self.get_rooms(user_id)}
        for room_name in SEED_EXTRA_ROOMS:
            if room_name not in existing_rooms:
                self.add_room(user_id, room_name)
        rooms = {room["name"]: room["id"] for room in self.get_rooms(user_id)}
        existing = {(d["room_name"], d["model_code"], d["name"]) for d in self.get_devices(user_id)}
        for room_name, model_code, name, is_on, settings in SEED_DEVICES:
            if (room_name, model_code, name) in existing or room_name not in rooms:
                continue  # уже есть (или пользователь удалил комнату) - не дублируем
            device_id = self.add_device(user_id, rooms[room_name], model_code, name)
            full = default_settings(MODELS[model_code])
            full.update(settings)
            self.save_settings(device_id, full)
            self.set_device_state(device_id, bool(is_on))

    # ---------- пользователи ----------

    def get_user(self, username):
        # login_key = имя в нижнем регистре: COLLATE NOCASE в SQLite не работает для кириллицы
        return self.conn.execute(
            "SELECT * FROM users WHERE login_key = ?", (username.strip().casefold(),)
        ).fetchone()

    def create_user(self, username, password):
        salt = secrets.token_hex(16)
        cur = self.conn.execute(
            "INSERT INTO users (username, login_key, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, username.casefold(), hash_password(password, salt), salt,
             datetime.now().isoformat(timespec="seconds")),
        )
        user_id = cur.lastrowid
        for position, room_name in enumerate(DEFAULT_ROOMS):
            self.conn.execute(
                "INSERT INTO rooms (user_id, name, position, floor) VALUES (?, ?, ?, ?)",
                (user_id, room_name, position, room_zone(room_name)[0]),
            )
        self.conn.commit()
        return user_id

    def authenticate(self, username, password):
        user = self.get_user(username)
        if user is None:
            return None
        if not secrets.compare_digest(user["password_hash"], hash_password(password, user["salt"])):
            return None
        return user

    def save_battery(self, user_id, battery_wh):
        self.conn.execute("UPDATE users SET battery_wh = ? WHERE id = ?", (battery_wh, user_id))
        self.conn.commit()

    def get_user_by_id(self, user_id):
        return self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def save_energy_totals(self, user_id, generated_wh, import_wh, export_wh):
        self.conn.execute(
            "UPDATE users SET total_generated_wh = ?, total_import_wh = ?, total_export_wh = ? WHERE id = ?",
            (generated_wh, import_wh, export_wh, user_id),
        )
        self.conn.commit()

    def set_user_option(self, user_id, column, value):
        assert column in ("eco_mode", "tariff_kzt")
        self.conn.execute(f"UPDATE users SET {column} = ? WHERE id = ?", (value, user_id))
        self.conn.commit()

    # ---------- журнал событий ----------

    def add_event(self, user_id, sim_time, category, icon, text):
        self.conn.execute(
            "INSERT INTO events (user_id, sim_time, category, icon, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, sim_time, category, icon, text, datetime.now().isoformat(timespec="seconds")),
        )
        # храним только последние 500 событий
        self.conn.execute(
            "DELETE FROM events WHERE user_id = ? AND id NOT IN "
            "(SELECT id FROM events WHERE user_id = ? ORDER BY id DESC LIMIT 500)", (user_id, user_id)
        )
        self.conn.commit()

    def get_events(self, user_id, limit=300):
        rows = self.conn.execute(
            "SELECT * FROM events WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_events(self, user_id):
        self.conn.execute("DELETE FROM events WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_battery(self, user_id):
        row = self.conn.execute("SELECT battery_wh FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["battery_wh"] if row else BATTERY_CAPACITY_WH / 2

    # ---------- комнаты ----------

    def get_rooms(self, user_id):
        return self.conn.execute(
            "SELECT * FROM rooms WHERE user_id = ? ORDER BY position, id", (user_id,)
        ).fetchall()

    def add_room(self, user_id, name, floor=None):
        row = self.conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM rooms WHERE user_id = ?", (user_id,)
        ).fetchone()
        cur = self.conn.execute(
            "INSERT INTO rooms (user_id, name, position, floor) VALUES (?, ?, ?, ?)",
            (user_id, name, row[0], floor or room_zone(name)[0]),
        )
        self.conn.commit()
        return cur.lastrowid

    def set_room_floor(self, room_id, floor):
        self.conn.execute("UPDATE rooms SET floor = ? WHERE id = ?", (floor, room_id))
        # своё место на плане у устройств этой комнаты сбрасываем - они переедут на новый этаж
        for row in self.conn.execute("SELECT id, settings FROM devices WHERE room_id = ?", (room_id,)).fetchall():
            settings = json.loads(row["settings"] or "{}")
            if settings.pop("plan", None) is not None:
                self.conn.execute("UPDATE devices SET settings = ? WHERE id = ?",
                                  (json.dumps(settings, ensure_ascii=False), row["id"]))
        self.conn.commit()

    # ---------- история энергии по дням (для отчётов) ----------

    def save_energy_day(self, user_id, day, generated_wh, consumed_wh, import_wh, export_wh):
        """День, прожитый симуляцией, - заменяет сгенерированную историю за эту дату."""
        self.conn.execute(
            "INSERT OR REPLACE INTO energy_days VALUES (?, ?, ?, ?, ?, ?, 1)",
            (user_id, day.isoformat(), generated_wh, consumed_wh, import_wh, export_wh),
        )
        self.conn.commit()

    def backfill_energy_history(self, user_id, devices_count, until):
        """Дописать недостающие прошлые дни правдоподобной историей (реальных измерений в учебном проекте нет)."""
        rows = [(user_id, d.isoformat(), *values, 0)
                for d, values in synthetic_energy_history(user_id, devices_count, until).items()]
        self.conn.executemany("INSERT OR IGNORE INTO energy_days VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        self.conn.commit()

    def get_energy_days(self, user_id, start, end):
        rows = self.conn.execute(
            "SELECT * FROM energy_days WHERE user_id = ? AND day BETWEEN ? AND ? ORDER BY day",
            (user_id, start.isoformat(), end.isoformat()),
        ).fetchall()
        return {date.fromisoformat(r["day"]): (r["generated_wh"], r["consumed_wh"], r["import_wh"], r["export_wh"])
                for r in rows}

    def delete_room(self, room_id):
        self.conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        self.conn.commit()

    # ---------- устройства ----------

    def get_devices(self, user_id):
        rows = self.conn.execute("""
            SELECT d.*, r.name AS room_name
            FROM devices d JOIN rooms r ON r.id = d.room_id
            WHERE d.user_id = ?
            ORDER BY r.position, d.id
        """, (user_id,)).fetchall()
        devices = []
        for row in rows:
            device = dict(row)
            device["settings"] = json.loads(device["settings"] or "{}")
            devices.append(device)
        return devices

    def add_device(self, user_id, room_id, model_code, name):
        model = MODELS[model_code]
        cur = self.conn.execute(
            "INSERT INTO devices (user_id, room_id, type_code, model_code, name, is_on, settings, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, room_id, model["type"], model_code, name, int(is_always_on(model["type"])),
             json.dumps(default_settings(model), ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
        self.conn.commit()
        return cur.lastrowid

    def set_device_state(self, device_id, is_on):
        self.conn.execute("UPDATE devices SET is_on = ? WHERE id = ?", (int(is_on), device_id))
        self.conn.commit()

    def save_settings(self, device_id, settings):
        self.conn.execute(
            "UPDATE devices SET settings = ? WHERE id = ?", (json.dumps(settings, ensure_ascii=False), device_id)
        )
        self.conn.commit()

    def rename_device(self, device_id, name):
        self.conn.execute("UPDATE devices SET name = ? WHERE id = ?", (name, device_id))
        self.conn.commit()

    def move_device(self, device_id, room_id):
        self.conn.execute("UPDATE devices SET room_id = ? WHERE id = ?", (room_id, device_id))
        self.conn.commit()

    def delete_device(self, device_id):
        self.conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        self.conn.commit()


####################################
###### СИМУЛЯЦИЯ ЭНЕРГОСИСТЕМЫ #####
####################################

class SolarSimulator(QObject):
    """
    Модель солнечной электростанции дома: панели -> аккумулятор -> потребители.
    Раз в секунду рассчитывается выработка (по времени суток и облачности),
    потребление включённых устройств и поток энергии в аккумулятор / из него.
    """

    updated = pyqtSignal(dict)

    def __init__(self, battery_wh, load_provider, totals=None, parent=None):
        super().__init__(parent)
        totals = totals or {}
        self.total_generated_wh = totals.get("generated", 0.0)
        self.total_import_wh = totals.get("import", 0.0)
        self.total_export_wh = totals.get("export", 0.0)
        self.import_today_wh = 0.0
        self.export_today_wh = 0.0
        self.battery_wh = max(0.0, min(BATTERY_CAPACITY_WH, battery_wh))
        self.load_provider = load_provider
        now = datetime.now()
        self.start_date = now.date()  # дата, с которой началась симуляция (день 0)
        self.sim_minutes = now.hour * 60 + now.minute + now.second / 60
        self.minutes_per_tick = SIM_SPEEDS[1][1]
        self.cloudiness = random.uniform(0.0, 0.4)
        self.generated_today_wh = 0.0
        self.consumed_today_wh = 0.0
        self.state = {}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def start(self):
        self.tick(advance=False)
        self.timer.start(1000)

    def stop(self):
        self.timer.stop()

    def set_speed(self, minutes_per_tick):
        self.minutes_per_tick = minutes_per_tick

    def solar_power(self):
        hour = (self.sim_minutes / 60) % 24
        sunrise, sunset = 6.0, 20.0
        if not sunrise < hour < sunset:
            return 0.0
        sun_height = math.sin(math.pi * (hour - sunrise) / (sunset - sunrise))
        power = SOLAR_PEAK_W * sun_height * (1 - 0.75 * self.cloudiness)
        return max(0.0, power * random.uniform(0.97, 1.03))

    def sim_date(self):
        """Текущая дата «внутри» симуляции (она уходит вперёд при ускорении времени)."""
        return self.start_date + timedelta(days=int(self.sim_minutes // 1440))

    def tick(self, advance=True):
        closed_day = None
        if advance:
            previous_day = int(self.sim_minutes // 1440)
            self.sim_minutes += self.minutes_per_tick
            if int(self.sim_minutes // 1440) != previous_day:
                # сутки закончились - отдаём их итоги для отчётов и начинаем новые
                closed_day = (self.start_date + timedelta(days=previous_day), self.generated_today_wh,
                              self.consumed_today_wh, self.import_today_wh, self.export_today_wh)
                self.generated_today_wh = 0.0
                self.consumed_today_wh = 0.0
                self.import_today_wh = 0.0
                self.export_today_wh = 0.0
            step = 0.04 * math.sqrt(self.minutes_per_tick)
            self.cloudiness = min(0.95, max(0.0, self.cloudiness + random.uniform(-step, step)))

        hours = self.minutes_per_tick / 60 if advance else 0.0
        generation = self.solar_power()
        load = BASE_LOAD_W + self.load_provider()
        balance = generation - load

        charge_w = discharge_w = grid_import_w = grid_export_w = 0.0
        reserve_wh = BATTERY_CAPACITY_WH * BATTERY_RESERVE

        if balance >= 0:
            room_wh = BATTERY_CAPACITY_WH - self.battery_wh
            charge_w = min(balance, MAX_CHARGE_W, room_wh / hours if hours else balance)
            grid_export_w = balance - charge_w
        else:
            deficit = -balance
            available_wh = max(0.0, self.battery_wh - reserve_wh)
            discharge_w = min(deficit, available_wh / hours if hours else (deficit if available_wh > 0 else 0))
            grid_import_w = deficit - discharge_w

        self.battery_wh += (charge_w - discharge_w) * hours
        self.battery_wh = max(0.0, min(BATTERY_CAPACITY_WH, self.battery_wh))
        self.generated_today_wh += generation * hours
        self.consumed_today_wh += load * hours
        self.import_today_wh += grid_import_w * hours
        self.export_today_wh += grid_export_w * hours
        self.total_generated_wh += generation * hours
        self.total_import_wh += grid_import_w * hours
        self.total_export_wh += grid_export_w * hours

        if grid_import_w > 1 and discharge_w > 1:
            source = "🔋 АКБ + 🔌 сеть"
        elif grid_import_w > 1:
            source = "🔌 Сеть"
        elif discharge_w > 1 and generation > 1:
            source = "☀️ Солнце + 🔋 АКБ"
        elif discharge_w > 1:
            source = "🔋 Аккумулятор"
        else:
            source = "☀️ Солнце"

        self.state = {
            "time": sim_time_text(self.sim_minutes),
            "sim_minutes": self.sim_minutes,
            "date": self.sim_date(),
            "closed_day": closed_day,
            "advanced": advance,  # False - пересчёт без хода времени (после переключения устройства)
            "level": self.battery_wh / BATTERY_CAPACITY_WH,
            "battery_wh": self.battery_wh,
            "generation": generation,
            "load": load,
            "charge": charge_w,
            "discharge": discharge_w,
            "grid_import": grid_import_w,
            "grid_export": grid_export_w,
            "source": source,
            "weather": self.weather_icon(generation),
            "generated_today": self.generated_today_wh,
            "consumed_today": self.consumed_today_wh,
            "import_today": self.import_today_wh,
            "export_today": self.export_today_wh,
            "total_generated": self.total_generated_wh,
            "total_import": self.total_import_wh,
            "total_export": self.total_export_wh,
        }
        self.updated.emit(self.state)

    def weather_icon(self, generation):
        if generation <= 0:
            return "🌙 Ночь"
        if self.cloudiness < 0.25:
            return "☀️ Ясно"
        if self.cloudiness < 0.6:
            return "⛅ Переменная облачность"
        return "☁️ Пасмурно"


def format_power(watts):
    if abs(watts) >= 1000:
        return f"{watts / 1000:.2f} кВт"
    if 0 < abs(watts) < 10:
        return f"{watts:.1f} Вт"
    return f"{watts:.0f} Вт"


def format_energy(wh):
    if abs(wh) >= 1000:
        return f"{wh / 1000:.2f} кВт·ч"
    return f"{wh:.0f} Вт·ч"


####################################
############### СТИЛИ ##############
####################################

ACCENT = "#00b96b"

APP_STYLE = """
    QWidget {
        font-family: 'Helvetica Neue', 'Segoe UI', Arial, sans-serif;
        font-size: 14px;
        color: #14364f;
    }

    QMainWindow, QDialog, QWidget#loginRoot {
        background-color: #eef4f9;
    }

    QLabel { background: transparent; }

    QPushButton {
        background-color: #00b96b;
        border: none;
        padding: 11px 18px;
        border-radius: 10px;
        font-size: 15px;
        font-weight: 600;
        color: white;
    }
    QPushButton:hover { background-color: #00a35e; }
    QPushButton:pressed { background-color: #008a50; }

    QPushButton#secondary {
        background-color: #ffffff;
        color: #14364f;
        border: 1px solid #cfdde8;
    }
    QPushButton#secondary:hover { background-color: #f1f6fa; }

    QPushButton#danger {
        background-color: #ffffff;
        color: #e5484d;
        border: 1px solid #f3c4c6;
    }
    QPushButton#danger:hover { background-color: #fff1f1; }

    QPushButton#segment {
        background-color: transparent;
        color: #7d93a5;
        border-radius: 0;
        border-bottom: 3px solid transparent;
        padding: 8px 4px;
        font-size: 17px;
    }
    QPushButton#segment:checked {
        color: #12293c;
        border-bottom: 3px solid #00b96b;
    }

    QPushButton#chip {
        background-color: #ffffff;
        color: #14364f;
        border: 1px solid #cfdde8;
        padding: 8px 12px;
        font-size: 14px;
        font-weight: 500;
    }
    QPushButton#chip:hover { background-color: #f1f6fa; }
    QPushButton#chip:checked { background-color: #e9f9f1; border: 1px solid #00b96b; color: #008a50; }

    QLineEdit, QComboBox {
        background-color: #ffffff;
        border: 1px solid #cfdde8;
        border-radius: 10px;
        padding: 10px 12px;
        font-size: 15px;
    }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #00b96b; }

    QLabel#title { font-size: 26px; font-weight: 700; color: #12293c; }
    QLabel#subtitle { font-size: 14px; color: #5f7a8f; }
    QLabel#error { color: #d64545; font-size: 13px; }
    QLabel#sectionTitle { font-size: 17px; font-weight: 700; color: #12293c; }
    QLabel#controlTitle { font-size: 14px; font-weight: 600; color: #12293c; }
    QLabel#controlValue { font-size: 14px; font-weight: 600; color: #00a35e; }

    QFrame#card {
        background-color: #ffffff;
        border-radius: 18px;
        border: 1px solid #dfe8ef;
    }

    QFrame#deviceCard {
        background-color: #ffffff;
        border-radius: 16px;
        border: 1px solid #dfe8ef;
    }
    QFrame#deviceCard:hover { border: 1px solid #9fb3c3; }
    QFrame#deviceCard[on="true"] {
        background-color: #e9f9f1;
        border: 1px solid #9fe0c2;
    }
    QFrame#deviceCard[on="true"]:hover { border: 1px solid #00b96b; }

    QFrame#header {
        border: none;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2d5f8f, stop:1 #6f9fc6);
    }
    QFrame#header QLabel { color: white; }

    QToolButton#headerButton {
        color: white;
        background: rgba(255, 255, 255, 0.15);
        border: none;
        border-radius: 10px;
        padding: 8px 14px;
        font-size: 15px;
        font-weight: 600;
    }
    QToolButton#headerButton:hover { background: rgba(255, 255, 255, 0.28); }
    QToolButton#headerButton::menu-indicator { image: none; }

    QTabBar { background: transparent; }
    QTabBar::tab {
        background: transparent;
        color: rgba(255, 255, 255, 0.65);
        padding: 8px 14px;
        border-bottom: 3px solid transparent;
    }
    QTabBar::tab:selected { color: white; border-bottom: 3px solid white; }
    QTabBar::tab:hover { color: white; }

    QScrollArea { border: none; background: transparent; }
    QScrollArea > QWidget > QWidget { background: transparent; }

    QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
    QScrollBar::handle:vertical { background: #c6d4dd; border-radius: 4px; min-height: 40px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

    QProgressBar {
        border: none;
        border-radius: 5px;
        background-color: #e3edf4;
        max-height: 10px;
    }
    QProgressBar::chunk { background-color: #f5b301; border-radius: 5px; }

    QSlider::groove:horizontal { height: 6px; background: #dfe8ef; border-radius: 3px; }
    QSlider::sub-page:horizontal { background: #00b96b; border-radius: 3px; }
    QSlider::handle:horizontal {
        background: white;
        border: 2px solid #00b96b;
        width: 16px;
        height: 16px;
        margin: -7px 0;
        border-radius: 10px;
    }
    QSlider#ctSlider::groove:horizontal {
        height: 8px;
        border-radius: 4px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ffb15c, stop:0.5 #fff6e5, stop:1 #b9d4ff);
    }
    QSlider#ctSlider::sub-page:horizontal { background: transparent; }

    QPushButton#navButton {
        background-color: #ffffff;
        color: #14364f;
        border: 1px solid #dfe8ef;
        padding: 9px 16px;
        font-size: 14px;
        font-weight: 600;
    }
    QPushButton#navButton:hover { background-color: #f1f6fa; }
    QPushButton#navButton:checked { background-color: #12293c; color: white; border: 1px solid #12293c; }

    QListWidget#eventsList {
        background: #ffffff;
        border: 1px solid #dfe8ef;
        border-radius: 14px;
        padding: 6px;
        font-size: 14px;
    }
    QListWidget#eventsList::item { padding: 9px 8px; border-bottom: 1px solid #eef2f5; }

    QDoubleSpinBox {
        background: #ffffff;
        border: 1px solid #cfdde8;
        border-radius: 8px;
        padding: 4px 8px;
    }

    QMenu {
        background: white;
        border: 1px solid #dfe8ef;
        border-radius: 8px;
        padding: 6px;
    }
    QMenu::item { padding: 7px 22px; border-radius: 6px; }
    QMenu::item:selected { background: #e9f9f1; color: #12293c; }
"""

# Тёмный стиль окна добавления устройства (как в мобильном приложении Xiaomi Home)
DARK_DIALOG_STYLE = """
    QDialog, QWidget#darkPage { background-color: #111214; }
    QLabel { color: #f2f2f2; background: transparent; }
    QLabel#groupTitle { color: #8a8fa3; font-size: 14px; padding-top: 14px; }
    QLabel#pageTitle { font-size: 20px; font-weight: 700; }
    QLabel#hint { color: #9a9aa2; font-size: 13px; }
    QLabel#feature {
        color: #c9f2dc;
        background: #1f3a2d;
        border-radius: 8px;
        padding: 3px 8px;
        font-size: 12px;
    }

    QFrame#darkCard { background-color: #1e1f22; border-radius: 18px; border: none; }
    QFrame#modelCard { background-color: #2c2d31; border-radius: 14px; border: 1px solid #2c2d31; }
    QFrame#modelCard:hover { border: 1px solid #00b96b; }

    QPushButton#tile {
        background-color: #2c2d31;
        color: #f2f2f2;
        text-align: left;
        padding: 16px 14px;
        border-radius: 14px;
        font-size: 15px;
        font-weight: 500;
    }
    QPushButton#tile:hover { background-color: #36373c; }

    QPushButton#ghost {
        background-color: #2c2d31;
        color: #f2f2f2;
    }
    QPushButton#ghost:hover { background-color: #36373c; }

    QPushButton#floorChip {
        background-color: #2c2d31;
        color: #f2f2f2;
        padding: 10px 14px;
        font-weight: 600;
    }
    QPushButton#floorChip:checked { background-color: #00b96b; color: white; }
    QLabel#placeHint { color: #9fe0c2; font-size: 13px; }

    QLineEdit, QComboBox {
        background-color: #2c2d31;
        color: #f2f2f2;
        border: 1px solid #3a3b40;
        border-radius: 10px;
        padding: 10px 12px;
        font-size: 15px;
    }
    QLineEdit:focus, QComboBox:focus { border: 1px solid #00b96b; }
    QComboBox QAbstractItemView { background: #2c2d31; color: #f2f2f2; selection-background-color: #00b96b; }

    QScrollArea { border: none; background: transparent; }
    QScrollArea > QWidget > QWidget { background: transparent; }

    QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
    QScrollBar::handle:vertical { background: #3a3b40; border-radius: 4px; min-height: 40px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


####################################
############# ВИДЖЕТЫ ##############
####################################

class ToggleSwitch(QCheckBox):
    """Тумблер в стиле мобильных приложений с анимированным скольжением ручки (из main.py)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(52, 28)

        self._position = 0.0  # 0.0 = выключено, 1.0 = включено
        self._off_color = QColor("#c6d4dd")
        self._on_color = QColor(ACCENT)

        self._anim = QPropertyAnimation(self, b"position", self)
        self._anim.setDuration(240)
        self._anim.setEasingCurve(QEasingCurve.OutBack)

        self.toggled.connect(self._animate_to_state)

    def set_state_silent(self, checked):
        """Выставить состояние без анимации и без сигнала toggled (при построении карточки)."""
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._anim.stop()
        self._position = 1.0 if checked else 0.0
        self.update()

    def hitButton(self, pos):
        return self.contentsRect().contains(pos)

    def _animate_to_state(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._position)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def getPosition(self):
        return self._position

    def setPosition(self, value):
        self._position = value
        self.update()

    position = pyqtProperty(float, getPosition, setPosition)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        t = max(0.0, min(1.0, self._position))
        bg = QColor(
            int(self._off_color.red() + (self._on_color.red() - self._off_color.red()) * t),
            int(self._off_color.green() + (self._on_color.green() - self._off_color.green()) * t),
            int(self._off_color.blue() + (self._on_color.blue() - self._off_color.blue()) * t),
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)

        knob = self.height() - 6
        x = 3 + (self.width() - knob - 6) * self._position
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(x, 3, knob, knob))


class BatteryGauge(QWidget):
    """Нарисованная батарея с уровнем заряда и значком молнии при зарядке."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.charging = False
        self.setMinimumSize(220, 84)

    def set_state(self, level, charging):
        self.level = max(0.0, min(1.0, level))
        self.charging = charging
        self.update()

    def level_color(self):
        if self.level > 0.5:
            return QColor(ACCENT)
        if self.level > 0.2:
            return QColor("#f5a623")
        return QColor("#e5484d")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cap_w = 10
        body = QRectF(2, 2, self.width() - cap_w - 6, self.height() - 4)
        cap = QRectF(body.right() + 2, body.center().y() - body.height() * 0.2, cap_w, body.height() * 0.4)

        painter.setPen(QPen(QColor("#9fb3c3"), 3))
        painter.setBrush(QColor("#f4f8fb"))
        painter.drawRoundedRect(body, 14, 14)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#9fb3c3"))
        painter.drawRoundedRect(cap, 3, 3)

        inner = body.adjusted(6, 6, -6, -6)
        fill = QRectF(inner.left(), inner.top(), inner.width() * self.level, inner.height())
        if fill.width() > 0:
            painter.setBrush(self.level_color())
            painter.drawRoundedRect(fill, 9, 9)

        painter.setPen(QColor("#12293c") if self.level < 0.55 else QColor("white"))
        font = QFont(self.font())
        font.setPixelSize(30)
        font.setBold(True)
        painter.setFont(font)
        text = f"{self.level * 100:.0f}%" + ("  ⚡" if self.charging else "")
        painter.drawText(body, Qt.AlignCenter, text)


class StatRow(QWidget):
    """Строка «подпись .......... значение» для панели энергосистемы."""

    def __init__(self, caption, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        caption_label = QLabel(caption)
        caption_label.setObjectName("subtitle")
        self.value_label = QLabel("—")
        self.value_label.setStyleSheet("font-weight: 600;")
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(caption_label)
        layout.addStretch()
        layout.addWidget(self.value_label)

    def set_value(self, text, color=None):
        self.value_label.setText(text)
        self.value_label.setStyleSheet(f"font-weight: 600; color: {color};" if color else "font-weight: 600;")


class SolarPanelWidget(QFrame):
    """Блок «Солнечная энергия»: заряд аккумулятора, выработка, потребление, источник питания."""

    speed_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("☀️ Солнечная энергия")
        title.setObjectName("sectionTitle")
        self.time_label = QLabel()
        self.time_label.setObjectName("subtitle")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self.time_label)
        layout.addLayout(head)

        self.weather_label = QLabel()
        self.weather_label.setObjectName("subtitle")
        layout.addWidget(self.weather_label)

        layout.addSpacing(4)
        battery_caption = QLabel(f"Аккумулятор · {BATTERY_CAPACITY_WH / 1000:.0f} кВт·ч")
        battery_caption.setStyleSheet("font-weight: 600;")
        layout.addWidget(battery_caption)

        self.gauge = BatteryGauge()
        layout.addWidget(self.gauge)

        self.flow_label = QLabel()
        self.flow_label.setAlignment(Qt.AlignCenter)
        self.flow_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(self.flow_label)

        self.stored_label = QLabel()
        self.stored_label.setObjectName("subtitle")
        self.stored_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.stored_label)

        layout.addSpacing(6)
        gen_caption = QLabel(f"Выработка панелей (пик {SOLAR_PEAK_W / 1000:.0f} кВт)")
        gen_caption.setObjectName("subtitle")
        layout.addWidget(gen_caption)
        self.generation_bar = QProgressBar()
        self.generation_bar.setRange(0, SOLAR_PEAK_W)
        self.generation_bar.setTextVisible(False)
        layout.addWidget(self.generation_bar)

        layout.addSpacing(6)
        self.row_generation = StatRow("☀️ Генерация")
        self.row_load = StatRow("🏠 Потребление дома")
        self.row_grid = StatRow("🔌 Обмен с сетью")
        self.row_source = StatRow("⚡ Источник питания")
        self.row_generated = StatRow("📈 Выработано за сутки")
        self.row_consumed = StatRow("📉 Потреблено за сутки")
        for row in (self.row_generation, self.row_load, self.row_grid, self.row_source,
                    self.row_generated, self.row_consumed):
            layout.addWidget(row)

        layout.addSpacing(8)
        speed_row = QHBoxLayout()
        speed_caption = QLabel("Скорость симуляции")
        speed_caption.setObjectName("subtitle")
        self.speed_combo = QComboBox()
        for caption, minutes in SIM_SPEEDS:
            self.speed_combo.addItem(caption, minutes)
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.currentIndexChanged.connect(
            lambda i: self.speed_changed.emit(self.speed_combo.itemData(i))
        )
        speed_row.addWidget(speed_caption)
        speed_row.addStretch()
        speed_row.addWidget(self.speed_combo)
        layout.addLayout(speed_row)

        layout.addStretch()

    def update_state(self, s):
        self.time_label.setText(f"🕒 {s['time']}")
        self.weather_label.setText(s["weather"])
        charging = s["charge"] > 1
        self.gauge.set_state(s["level"], charging)

        if charging:
            self.flow_label.setText(f"Заряжается  +{format_power(s['charge'])}")
            self.flow_label.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {ACCENT};")
        elif s["discharge"] > 1:
            self.flow_label.setText(f"Разряжается  −{format_power(s['discharge'])}")
            self.flow_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #e08a00;")
        elif s["level"] >= 0.999:
            self.flow_label.setText("Полностью заряжен")
            self.flow_label.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {ACCENT};")
        else:
            self.flow_label.setText("Резерв — питание от сети")
            self.flow_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #e5484d;")

        self.stored_label.setText(
            f"Накоплено {format_energy(s['battery_wh'])} из {format_energy(BATTERY_CAPACITY_WH)}"
        )
        self.generation_bar.setValue(int(s["generation"]))
        self.row_generation.set_value(format_power(s["generation"]), "#c98a00")
        self.row_load.set_value(format_power(s["load"]))
        if s["grid_export"] > 1:
            self.row_grid.set_value(f"→ отдача {format_power(s['grid_export'])}", ACCENT)
        elif s["grid_import"] > 1:
            self.row_grid.set_value(f"← из сети {format_power(s['grid_import'])}", "#e5484d")
        else:
            self.row_grid.set_value("нет")
        self.row_source.set_value(s["source"])
        self.row_generated.set_value(format_energy(s["generated_today"]))
        self.row_consumed.set_value(format_energy(s["consumed_today"]))


def device_status_html(device, reading=None):
    """Короткое описание состояния устройства для карточки (rich text)."""
    model = MODELS.get(device["model_code"], {"caps": []})
    caps = model["caps"]
    s = device["settings"]
    type_code = device["type_code"]
    group = DEVICE_TYPES[type_code]["group"]

    if type_code == "robot_vacuum":
        state = s.get("vac_state", "docked")
        battery = f"🔋 {s.get('vac_battery', 100):.0f}%"
        if state == "cleaning":
            return f"🧹 Уборка {s.get('vac_progress', 0) * 100:.0f}% · {battery}"
        if state == "paused":
            return f"⏸ Пауза {s.get('vac_progress', 0) * 100:.0f}% · {battery}"
        if state == "returning":
            return f"↩️ Едет на базу · {battery}"
        charging = " ⚡" if s.get("vac_battery", 100) < 99.5 else ""
        return f"🏠 На базе · {battery}{charging}"

    if type_code == "washer":
        if not device["is_on"]:
            return "✅ Стирка завершена" if s.get("wash_done") else "Выключена"
        left = washer_total(s) * (1 - washer_fraction(s))
        return f"{washer_phase(washer_fraction(s))} · осталось {int(left // 60)}:{int(left % 60):02d}"

    if s.get("solar_only") and device["is_on"]:
        power = device.get("_solar_power", 0.0)
        return f"☀️ От солнца ≈{format_power(power)}" if power > 1 else "☀️ Ждёт излишков солнца"

    if type_code == "kettle":
        water = f"{s.get('water_ml', 0) / 1000:.1f} л"
        temp = s.get("water_temp", ROOM_TEMP)
        if not device["is_on"]:
            return f"Выключен · {water} · {temp:.0f}°C"
        if s.get("water_ml", 0) < MIN_KETTLE_WATER_ML:
            return "⚠️ Нет воды"
        if kettle_is_heating(device):
            return f"🔥 Нагрев {temp:.0f}→{s.get('target_temp')}°C · {water}"
        return f"♨️ Поддержание {temp:.0f}°C · {water}"

    if not device["is_on"]:
        return "Отключён" if group == "Датчики" else "Выключено"

    parts = []
    if reading:
        parts.append(reading)
    if "lock" in caps:
        parts.append("🔒 Закрыт" if s.get("locked") else "🔓 Открыт")
    if "color" in caps and s.get("color"):
        parts.append(f"<span style='color:{s['color']}; font-size:16px;'>●</span>")
    if "brightness" in caps:
        parts.append(f"{s.get('brightness', 0)}%")
    if "color_temp" in caps and not s.get("color"):
        parts.append(f"{s.get('color_temp')} K")
    if "mode" in caps and type_code not in ("tv",):
        parts.append(s.get("mode", ""))
    if "target_temp" in caps:
        parts.append(f"{s.get('target_temp')}°C")
    if "fan_speed" in caps:
        parts.append(f"ск. {s.get('fan_speed')}")
    if "volume" in caps:
        parts.append(f"🔈 {s.get('volume')}%")
    if "current" in caps:
        parts.append(f"{s.get('current')} А")
    if "keys" in caps:
        keys = s.get("keys", [])
        parts.append(f"вкл. клавиш: {sum(keys)}/{len(keys)}")

    power = device_power(device)
    if power >= 1 and group != "Датчики":
        parts.append(f"≈{format_power(power)}")
    if not parts:
        parts.append("Включено")
    if s.get("off_at") is not None:
        parts.append(f"⏱ до {sim_time_text(s['off_at'])}")
    return " · ".join(parts)


class DeviceCard(QFrame):
    """Карточка устройства: иконка, название, модель, текущее состояние и тумблер. Клик - окно управления."""

    toggled = pyqtSignal(int, bool)
    open_requested = pyqtSignal(int)
    menu_requested = pyqtSignal(int, QPoint)

    def __init__(self, device, show_room=True, parent=None):
        super().__init__(parent)
        self.device = device
        self.show_room = show_room
        self.info = DEVICE_TYPES.get(device["type_code"], {"name": "Устройство", "icon": "📦"})
        self.model = MODELS.get(device["model_code"], {"name": "—"})
        self.setObjectName("deviceCard")
        self.setFixedSize(256, 150)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.device["id"], self.mapToGlobal(pos))
        )
        self._last_on = None
        self._last_html = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(2)

        top = QHBoxLayout()
        icon = QLabel(self.info["icon"])
        icon.setStyleSheet("font-size: 30px;")
        self.switch = ToggleSwitch()
        self.switch.set_state_silent(bool(device["is_on"]))
        self.switch.toggled.connect(lambda checked: self.toggled.emit(self.device["id"], checked))
        top.addWidget(icon)
        top.addStretch()
        top.addWidget(self.switch, alignment=Qt.AlignTop)
        layout.addLayout(top)
        layout.addSpacing(4)

        name_font = QFont(self.font())
        name_font.setPixelSize(15)
        name_font.setBold(True)
        name = QLabel(QFontMetrics(name_font).elidedText(device["name"], Qt.ElideRight, 220))
        name.setStyleSheet("font-size: 15px; font-weight: 700;")
        name.setToolTip(device["name"])
        layout.addWidget(name)

        sub_text = f"{device['room_name']} · {self.model['name']}" if show_room else self.model["name"]
        sub = QLabel(QFontMetrics(self.font()).elidedText(sub_text, Qt.ElideRight, 260))
        sub.setStyleSheet("font-size: 12px; color: #8aa0b2;")
        sub.setToolTip(sub_text)
        layout.addWidget(sub)

        self.status = QLabel()
        self.status.setTextFormat(Qt.RichText)
        self.status.setStyleSheet("font-size: 13px; color: #3f5e75;")
        layout.addWidget(self.status)

        self.refresh()

    def refresh(self, reading=None):
        on = bool(self.device["is_on"])
        if self.switch.isChecked() != on:
            self.switch.set_state_silent(on)
        html = device_status_html(self.device, reading)
        if html != self._last_html:
            self._last_html = html
            # элиде делаем по «чистому» тексту, иначе длинный статус растягивает карточку
            plain = QTextDocumentFragment.fromHtml(html).toPlainText()
            if QFontMetrics(self.status.font()).horizontalAdvance(plain) > 225:
                html = QFontMetrics(self.status.font()).elidedText(plain, Qt.ElideRight, 225)
            self.status.setText(html)
        if on != self._last_on:
            self._last_on = on
            self.setProperty("on", "true" if on else "false")
            self.style().unpolish(self)
            self.style().polish(self)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.open_requested.emit(self.device["id"])
        super().mouseReleaseEvent(event)


####################################
######## ВХОД И РЕГИСТРАЦИЯ ########
####################################

USERNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_\-]{2,32}$")


class LoginWindow(QWidget):
    logged_in = pyqtSignal(dict)

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setObjectName("loginRoot")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle("Умный дом — вход")
        self.setFixedSize(900, 560)
        self.init_ui()

    def init_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Левая панель с «брендом» приложения
        brand = QFrame()
        brand.setObjectName("header")
        brand.setFixedWidth(380)
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(40, 50, 40, 40)
        icon = QLabel("🏡☀️")
        icon.setStyleSheet("font-size: 64px;")
        name = QLabel("Умный дом")
        name.setStyleSheet("font-size: 32px; font-weight: 800;")
        desc = QLabel("Управление устройствами дома\nс альтернативными источниками питания")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 16px; color: rgba(255,255,255,0.85);")
        features = QLabel(
            f"☀️  Солнечные панели {SOLAR_PEAK_W / 1000:.0f} кВт\n\n"
            f"🔋  Аккумулятор {BATTERY_CAPACITY_WH / 1000:.0f} кВт·ч\n\n"
            "💡  Освещение, климат, безопасность\n\n"
            "📱  Все устройства в одном окне"
        )
        features.setStyleSheet("font-size: 15px; color: rgba(255,255,255,0.92);")
        brand_layout.addWidget(icon)
        brand_layout.addSpacing(10)
        brand_layout.addWidget(name)
        brand_layout.addWidget(desc)
        brand_layout.addSpacing(30)
        brand_layout.addWidget(features)
        brand_layout.addStretch()
        root.addWidget(brand)

        # Правая панель с формами
        form_side = QVBoxLayout()
        form_side.setContentsMargins(56, 50, 56, 40)
        form_side.setSpacing(10)

        segments = QHBoxLayout()
        segments.setSpacing(24)
        self.login_tab = QPushButton("Вход")
        self.register_tab = QPushButton("Регистрация")
        group = QButtonGroup(self)
        for i, btn in enumerate((self.login_tab, self.register_tab)):
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            group.addButton(btn, i)
            segments.addWidget(btn)
        segments.addStretch()
        self.login_tab.setChecked(True)
        group.idClicked.connect(self.switch_page)
        form_side.addLayout(segments)
        form_side.addSpacing(16)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_login_page())
        self.stack.addWidget(self._build_register_page())
        form_side.addWidget(self.stack)

        root.addLayout(form_side)

    def _build_login_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("С возвращением!")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("Войдите, чтобы управлять своим домом")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        self.login_user = QLineEdit()
        self.login_user.setPlaceholderText("Имя пользователя")
        self.login_pass = QLineEdit()
        self.login_pass.setPlaceholderText("Пароль")
        self.login_pass.setEchoMode(QLineEdit.Password)
        self.login_user.returnPressed.connect(self.login_pass.setFocus)
        self.login_pass.returnPressed.connect(self.do_login)
        layout.addWidget(self.login_user)
        layout.addWidget(self.login_pass)

        self.login_error = QLabel()
        self.login_error.setObjectName("error")
        layout.addWidget(self.login_error)

        login_btn = QPushButton("Войти")
        login_btn.setCursor(Qt.PointingHandCursor)
        login_btn.clicked.connect(self.do_login)
        layout.addWidget(login_btn)

        layout.addStretch()
        return page

    def _build_register_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = QLabel("Новый аккаунт")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("Для нового дома будут созданы стандартные комнаты")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        self.reg_user = QLineEdit()
        self.reg_user.setPlaceholderText("Имя пользователя (2–32 символа)")
        self.reg_pass = QLineEdit()
        self.reg_pass.setPlaceholderText("Пароль (не менее 4 символов)")
        self.reg_pass.setEchoMode(QLineEdit.Password)
        self.reg_pass2 = QLineEdit()
        self.reg_pass2.setPlaceholderText("Повторите пароль")
        self.reg_pass2.setEchoMode(QLineEdit.Password)
        self.reg_user.returnPressed.connect(self.reg_pass.setFocus)
        self.reg_pass.returnPressed.connect(self.reg_pass2.setFocus)
        self.reg_pass2.returnPressed.connect(self.do_register)
        for edit in (self.reg_user, self.reg_pass, self.reg_pass2):
            layout.addWidget(edit)

        self.reg_error = QLabel()
        self.reg_error.setObjectName("error")
        self.reg_error.setWordWrap(True)
        layout.addWidget(self.reg_error)

        reg_btn = QPushButton("Зарегистрироваться")
        reg_btn.setCursor(Qt.PointingHandCursor)
        reg_btn.clicked.connect(self.do_register)
        layout.addWidget(reg_btn)
        layout.addStretch()
        return page

    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        self.login_error.clear()
        self.reg_error.clear()

    def reset(self):
        self.login_pass.clear()
        self.login_error.clear()
        self.login_tab.setChecked(True)
        self.switch_page(0)

    def do_login(self):
        username = self.login_user.text().strip()
        password = self.login_pass.text()
        if not username or not password:
            self.login_error.setText("Введите имя пользователя и пароль")
            return
        user = self.db.authenticate(username, password)
        if user is None:
            self.login_error.setText("Неверное имя пользователя или пароль")
            self.login_pass.clear()
            return
        self.login_error.clear()
        self.logged_in.emit(dict(user))

    def do_register(self):
        username = self.reg_user.text().strip()
        password = self.reg_pass.text()
        if not USERNAME_RE.match(username):
            self.reg_error.setText("Имя: 2–32 символа, буквы, цифры, «_» или «-»")
            return
        if len(password) < 4:
            self.reg_error.setText("Пароль должен содержать не менее 4 символов")
            return
        if password != self.reg_pass2.text():
            self.reg_error.setText("Пароли не совпадают")
            return
        if self.db.get_user(username) is not None:
            self.reg_error.setText("Пользователь с таким именем уже существует")
            return

        self.db.create_user(username, password)
        for edit in (self.reg_user, self.reg_pass, self.reg_pass2):
            edit.clear()
        self.reg_error.clear()
        self.login_user.setText(username)
        self.logged_in.emit(dict(self.db.get_user(username)))


####################################
####### ДОБАВЛЕНИЕ УСТРОЙСТВА ######
####################################

class AddDeviceDialog(QDialog):
    """
    Добавление устройства в три шага (как в Xiaomi Home):
    тип устройства -> конкретная модель из каталога -> название и комната.
    """

    PAGE_TYPES, PAGE_MODELS, PAGE_FORM = range(3)

    def __init__(self, db: Database, user_id, rooms, default_room_id=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.user_id = user_id
        self.rooms = [dict(r) for r in rooms]
        self.default_room_id = default_room_id
        self.selected_type = None
        self.selected_model = None
        self.rooms_changed = False
        self.setWindowTitle("Добавить устройство")
        self.setStyleSheet(DARK_DIALOG_STYLE)
        self.resize(660, 760)

        self.stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.stack.addWidget(self._build_types_page())
        self.stack.addWidget(self._build_models_page())
        self.stack.addWidget(self._build_form_page())

    # ---------- шаг 1: тип устройства ----------

    def _build_types_page(self):
        page = QWidget()
        page.setObjectName("darkPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 18, 20, 12)
        outer.setSpacing(12)

        title = QLabel("Добавить устройство")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignCenter)
        outer.addWidget(title)

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Поиск по типу или модели (например, «Yeelight» или «чайник»)")
        self.search.textChanged.connect(self.filter_tiles)
        outer.addWidget(self.search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Блок «Обнаружение устройств поблизости»
        nearby = QFrame()
        nearby.setObjectName("darkCard")
        nearby_layout = QVBoxLayout(nearby)
        nearby_layout.setContentsMargins(20, 16, 20, 16)
        nearby_title = QLabel("Обнаружение устройств поблизости")
        nearby_title.setStyleSheet("font-size: 17px; font-weight: 700;")
        self.nearby_hint = QLabel("Разместите устройство как можно ближе к шлюзу и включите режим сопряжения.")
        self.nearby_hint.setObjectName("hint")
        self.nearby_hint.setWordWrap(True)
        self.scan_btn = QPushButton("📡  Начать поиск")
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.clicked.connect(self.start_scan)
        nearby_layout.addWidget(nearby_title)
        nearby_layout.addWidget(self.nearby_hint)
        nearby_layout.addWidget(self.scan_btn)
        content_layout.addWidget(nearby)

        # Ручное добавление по категориям
        manual = QFrame()
        manual.setObjectName("darkCard")
        manual_layout = QVBoxLayout(manual)
        manual_layout.setContentsMargins(16, 16, 16, 16)
        manual_layout.setSpacing(6)
        manual_title = QLabel("Добавление устройства вручную")
        manual_title.setStyleSheet("font-size: 17px; font-weight: 700;")
        manual_layout.addWidget(manual_title)

        self.sections = []  # [(заголовок, [(кнопка, код типа)], сетка)]
        for group, items in DEVICE_GROUPS:
            group_label = QLabel(group)
            group_label.setObjectName("groupTitle")
            manual_layout.addWidget(group_label)
            grid = QGridLayout()
            grid.setSpacing(10)
            tiles = []
            for i, (code, name, icon) in enumerate(items):
                count = len(CATALOG[code])
                tile = QPushButton(f"{icon}   {name}")
                tile.setObjectName("tile")
                tile.setToolTip(f"{count} {plural(count, 'модель', 'модели', 'моделей')} в каталоге")
                tile.setCursor(Qt.PointingHandCursor)
                tile.clicked.connect(lambda _, c=code: self.open_models(c))
                grid.addWidget(tile, i // 2, i % 2)
                tiles.append((tile, code))
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            manual_layout.addLayout(grid)
            self.sections.append((group_label, tiles, grid))
        content_layout.addWidget(manual)
        content_layout.addStretch()

        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self._scan_step)
        return page

    def filter_tiles(self, text):
        query = text.strip().lower()

        def matches(code):
            if query in DEVICE_TYPES[code]["name"].lower():
                return True
            return any(query in model["name"].lower() for model in CATALOG[code])

        for group_label, tiles, grid in self.sections:
            visible = [(t, c) for t, c in tiles if matches(c)]
            for tile, _ in tiles:
                grid.removeWidget(tile)
                tile.hide()
            for i, (tile, _) in enumerate(visible):
                grid.addWidget(tile, i // 2, i % 2)
                tile.show()
            group_label.setVisible(bool(visible))

    def start_scan(self):
        self._scan_ticks = 0
        self.scan_btn.setEnabled(False)
        self.scan_timer.start(400)

    def _scan_step(self):
        self._scan_ticks += 1
        self.nearby_hint.setText("Идёт поиск устройств" + "." * (self._scan_ticks % 4))
        if self._scan_ticks >= 8:
            self.scan_timer.stop()
            self.scan_btn.setEnabled(True)
            self.scan_btn.setText("📡  Повторить поиск")
            self.nearby_hint.setText("Устройств поблизости не найдено. Выберите устройство вручную ниже.")

    # ---------- шаг 2: модель ----------

    def _build_models_page(self):
        page = QWidget()
        page.setObjectName("darkPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)

        head = QHBoxLayout()
        back_btn = QPushButton("←")
        back_btn.setObjectName("ghost")
        back_btn.setFixedWidth(52)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(self.PAGE_TYPES))
        self.models_title = QLabel()
        self.models_title.setObjectName("pageTitle")
        head.addWidget(back_btn)
        head.addSpacing(8)
        head.addWidget(self.models_title, 1)
        outer.addLayout(head)

        self.models_hint = QLabel()
        self.models_hint.setObjectName("hint")
        outer.addWidget(self.models_hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.models_layout = QVBoxLayout(host)
        self.models_layout.setContentsMargins(0, 0, 6, 0)
        self.models_layout.setSpacing(10)
        scroll.setWidget(host)
        outer.addWidget(scroll)
        return page

    def open_models(self, type_code):
        self.selected_type = type_code
        info = DEVICE_TYPES[type_code]
        models = CATALOG[type_code]
        self.models_title.setText(f"{info['icon']}  {info['name']}")
        self.models_hint.setText(
            f"Выберите модель — {len(models)} {plural(len(models), 'вариант', 'варианта', 'вариантов')}. "
            "Модели отличаются мощностью и возможностями управления."
        )

        while self.models_layout.count():
            item = self.models_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        query = self.search.text().strip().lower()
        for model in models:
            self.models_layout.addWidget(self._model_card(model, highlight=bool(query) and query in model["name"].lower()))
        self.models_layout.addStretch()
        self.stack.setCurrentIndex(self.PAGE_MODELS)

    def _model_card(self, model, highlight=False):
        card = QFrame()
        card.setObjectName("modelCard")
        if highlight:
            card.setStyleSheet("QFrame#modelCard { border: 1px solid #00b96b; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        name = QLabel(model["name"])
        name.setStyleSheet("font-size: 16px; font-weight: 700;")
        name.setWordWrap(True)
        choose = QPushButton("Выбрать")
        choose.setCursor(Qt.PointingHandCursor)
        choose.setFixedWidth(120)
        choose.clicked.connect(lambda: self.open_form(model["code"]))
        top.addWidget(name, 1)
        top.addWidget(choose, alignment=Qt.AlignTop)
        layout.addLayout(top)

        desc = QLabel(model["desc"])
        desc.setObjectName("hint")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        specs = [f"⚡ {model_power_text(model)}"]
        if model.get("battery"):
            specs.append(f"🔋 питание от батареек {model['battery']}")
        spec_label = QLabel("   ".join(specs))
        spec_label.setStyleSheet("color: #d0d0d6; font-size: 13px;")
        layout.addWidget(spec_label)

        if model["caps"]:
            features = QHBoxLayout()
            features.setSpacing(6)
            for cap in model["caps"]:
                chip = QLabel(CAP_NAMES.get(cap, cap))
                chip.setObjectName("feature")
                features.addWidget(chip)
            features.addStretch()
            layout.addLayout(features)
        else:
            basic = QLabel("Только включение / выключение")
            basic.setObjectName("hint")
            layout.addWidget(basic)
        return card

    # ---------- шаг 3: название и комната ----------

    def _build_form_page(self):
        page = QWidget()
        page.setObjectName("darkPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(12)

        self.form_icon = QLabel()
        self.form_icon.setAlignment(Qt.AlignCenter)
        self.form_icon.setStyleSheet("font-size: 72px;")
        self.form_type = QLabel()
        self.form_type.setObjectName("pageTitle")
        self.form_type.setAlignment(Qt.AlignCenter)
        self.form_type.setWordWrap(True)
        self.form_power = QLabel()
        self.form_power.setObjectName("hint")
        self.form_power.setAlignment(Qt.AlignCenter)
        self.form_power.setWordWrap(True)
        layout.addStretch()
        layout.addWidget(self.form_icon)
        layout.addWidget(self.form_type)
        layout.addWidget(self.form_power)
        layout.addSpacing(20)

        name_caption = QLabel("Название устройства")
        name_caption.setObjectName("hint")
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(40)
        floor_caption = QLabel("Этаж")
        floor_caption.setObjectName("hint")
        floor_row = QHBoxLayout()
        floor_row.setSpacing(8)
        self.floor_group = QButtonGroup(self)
        self.floor_buttons = {}
        for code, caption, _ in FLOORS:
            btn = QPushButton(caption)
            btn.setObjectName("floorChip")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self.select_floor(c))
            self.floor_group.addButton(btn)
            self.floor_buttons[code] = btn
            floor_row.addWidget(btn)
        room_caption = QLabel("Комната на этом этаже")
        room_caption.setObjectName("hint")
        room_row = QHBoxLayout()
        self.room_combo = QComboBox()
        self.room_combo.currentIndexChanged.connect(self.update_place_hint)
        new_room_btn = QPushButton("+ Новая комната")
        new_room_btn.setObjectName("ghost")
        new_room_btn.setCursor(Qt.PointingHandCursor)
        new_room_btn.clicked.connect(self.create_room)
        room_row.addWidget(self.room_combo, 1)
        room_row.addWidget(new_room_btn)
        self.place_hint = QLabel()
        self.place_hint.setObjectName("placeHint")
        self.place_hint.setWordWrap(True)
        layout.addWidget(name_caption)
        layout.addWidget(self.name_edit)
        layout.addWidget(floor_caption)
        layout.addLayout(floor_row)
        layout.addWidget(room_caption)
        layout.addLayout(room_row)
        layout.addWidget(self.place_hint)

        self.form_error = QLabel()
        self.form_error.setStyleSheet("color: #ff6b6b;")
        layout.addWidget(self.form_error)

        buttons = QHBoxLayout()
        back_btn = QPushButton("Назад")
        back_btn.setObjectName("ghost")
        back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(self.PAGE_MODELS))
        add_btn = QPushButton("Добавить устройство")
        add_btn.clicked.connect(self.save_device)
        self.name_edit.returnPressed.connect(self.save_device)
        buttons.addWidget(back_btn)
        buttons.addWidget(add_btn, 2)
        layout.addLayout(buttons)
        layout.addStretch()
        return page

    def open_form(self, model_code):
        self.selected_model = model_code
        model = MODELS[model_code]
        info = DEVICE_TYPES[model["type"]]
        self.form_icon.setText(info["icon"])
        self.form_type.setText(model["name"])
        self.form_power.setText(f"{info['name']} · {model_power_text(model)}")
        self.name_edit.setText(info["name"])
        self.name_edit.selectAll()
        default = next((r for r in self.rooms if r["id"] == self.default_room_id), None)
        self.select_floor(default["floor"] if default else (self.rooms[0]["floor"] if self.rooms else "floor1"),
                          room_id=default["id"] if default else None)
        self.form_error.clear()
        self.stack.setCurrentIndex(self.PAGE_FORM)
        self.name_edit.setFocus()

    def select_floor(self, floor, room_id=None):
        """Выбран этаж - в списке остаются только его комнаты."""
        self.current_floor = floor
        self.floor_buttons[floor].setChecked(True)
        self.room_combo.blockSignals(True)
        self.room_combo.clear()
        for room in self.rooms:
            if room["floor"] == floor:
                self.room_combo.addItem(room["name"], room["id"])
        if room_id is not None and self.room_combo.findData(room_id) >= 0:
            self.room_combo.setCurrentIndex(self.room_combo.findData(room_id))
        self.room_combo.blockSignals(False)
        self.update_place_hint()

    def update_place_hint(self, *_):
        room_name = self.room_combo.currentText()
        if room_name:
            self.place_hint.setText(f"📍 Устройство появится на плане «{FLOOR_NAMES[self.current_floor]}» "
                                    f"в комнате «{room_name}»")
        else:
            self.place_hint.setText(f"На этаже «{FLOOR_NAMES[self.current_floor]}» пока нет комнат — "
                                    f"создайте её кнопкой «+ Новая комната»")

    def create_room(self):
        name, ok = QInputDialog.getText(self, "Новая комната",
                                        f"Название комнаты ({FLOOR_NAMES[self.current_floor]}):")
        name = name.strip()[:30]
        if not ok or not name:
            return
        if any(r["name"].lower() == name.lower() for r in self.rooms):
            self.form_error.setText("Комната с таким названием уже есть")
            return
        room_id = self.db.add_room(self.user_id, name, self.current_floor)
        self.rooms.append({"id": room_id, "name": name, "floor": self.current_floor})
        self.rooms_changed = True
        self.select_floor(self.current_floor, room_id=room_id)

    def save_device(self):
        name = self.name_edit.text().strip()
        if not name:
            self.form_error.setText("Введите название устройства")
            return
        if self.room_combo.currentData() is None:
            self.form_error.setText("На этом этаже нет комнат — создайте комнату")
            return
        self.db.add_device(self.user_id, self.room_combo.currentData(), self.selected_model, name)
        self.accept()


def model_power_text(model):
    if "load" in model["caps"]:
        return f"нагрузка до {format_power(model['power'])}"
    if "current" in model["caps"]:
        return f"до {format_power(model['power'])} ({model['max_current']} А)"
    duty = DUTY_CYCLE.get(model["type"], 1.0)
    if duty < 1:
        return f"{format_power(model['power'])} (в среднем ≈{format_power(model['power'] * duty)})"
    return format_power(model["power"])


####################################
###### ВИЗУАЛИЗАЦИЯ УСТРОЙСТВ ######
####################################

def _color(value, alpha=255):
    c = QColor(value)
    c.setAlpha(alpha)
    return c


def _lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
    )


def color_temp_to_qcolor(kelvin):
    """Примерный цвет белого света по цветовой температуре (2700 K - тёплый, 6500 K - холодный)."""
    t = (kelvin - 2700) / (6500 - 2700)
    warm, neutral, cold = QColor(255, 177, 92), QColor(255, 246, 229), QColor(185, 212, 255)
    return _lerp_color(warm, neutral, t * 2) if t < 0.5 else _lerp_color(neutral, cold, (t - 0.5) * 2)


def light_color(device):
    s = device["settings"]
    if s.get("color"):
        return QColor(s["color"])
    if "color_temp" in s:
        return color_temp_to_qcolor(s["color_temp"])
    return color_temp_to_qcolor(2700)


class LightPreview(QWidget):
    """Превью свечения светильника: цвет и размер ореола зависят от цвета/температуры и яркости."""

    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.device = device
        self.setFixedHeight(150)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        bg.setColorAt(0, QColor("#1c2733"))
        bg.setColorAt(1, QColor("#121a23"))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, 16, 16)

        center = QPointF(rect.center().x(), rect.center().y() - 6)
        on = bool(self.device["is_on"])
        brightness = self.device["settings"].get("brightness", 100) / 100
        color = light_color(self.device)

        if on:
            radius = 40 + 80 * brightness
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0, _color(color.name(), int(120 + 135 * brightness)))
            glow.setColorAt(0.45, _color(color.name(), int(60 * brightness + 20)))
            glow.setColorAt(1, _color(color.name(), 0))
            p.setBrush(glow)
            p.drawEllipse(center, radius, radius)

        bulb = QColor(color) if on else QColor("#4a5562")
        if on:
            bulb = _lerp_color(QColor("#ffffff"), color, 0.55)
        p.setBrush(bulb)
        p.setPen(QPen(QColor("#ffffff") if on else QColor("#6b7785"), 2))
        p.drawEllipse(center, 30, 30)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#9aa5b1"))
        p.drawRoundedRect(QRectF(center.x() - 14, center.y() + 26, 28, 22), 5, 5)

        p.setPen(QColor("#c8d3dd"))
        font = QFont(self.font())
        font.setPixelSize(12)
        p.setFont(font)
        caption = f"Яркость {int(brightness * 100)}%" if on else "Свет выключен"
        p.drawText(rect.adjusted(0, 0, 0, -8), Qt.AlignHCenter | Qt.AlignBottom, caption)


class KettleWidget(QWidget):
    """
    Анимированный чайник: стеклянная колба с уровнем воды и волнами, цвет воды зависит от
    температуры (синий -> оранжевый), при нагреве поднимаются пузырьки, над носиком идёт пар.
    """

    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.device = device
        self.model = MODELS[device["model_code"]]
        self.capacity = self.model.get("capacity_ml", 1700)
        s = device["settings"]
        self.shown_temp = s.get("water_temp", ROOM_TEMP)
        self.shown_level = s.get("water_ml", 0) / self.capacity
        self.phase = 0.0
        self.bubbles = []
        self.steam = []
        self.setFixedHeight(330)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def geometry_info(self):
        cx = self.width() / 2 - 12
        y0 = 78
        bh = 205
        return cx, y0, bh

    def water_top(self):
        cx, y0, bh = self.geometry_info()
        return y0 + bh - 8 - self.shown_level * (bh - 22)

    def _tick(self):
        s = self.device["settings"]
        self.shown_temp += (s.get("water_temp", ROOM_TEMP) - self.shown_temp) * 0.1
        level = min(1.0, s.get("water_ml", 0) / self.capacity)
        self.shown_level += (level - self.shown_level) * 0.12
        heating = kettle_is_heating(self.device)
        self.phase += 0.09 + (0.12 + 0.2 * max(0, self.shown_temp - 60) / 40 if heating else 0)

        cx, y0, bh = self.geometry_info()
        top = self.water_top()
        # пузырьки - чем горячее вода, тем их больше
        if heating and self.shown_level > 0.05 and self.shown_temp > 40:
            intensity = (self.shown_temp - 40) / 60
            for _ in range(3):
                if random.random() < intensity * 0.8:
                    self.bubbles.append([cx + random.uniform(-75, 75), y0 + bh - 10,
                                         random.uniform(2, 3 + 4 * intensity), random.uniform(1.5, 2.5 + 3 * intensity)])
        for b in self.bubbles:
            b[1] -= b[3]
            b[0] += math.sin(b[1] / 9) * 0.6
        self.bubbles = [b for b in self.bubbles if b[1] > top + 4]

        # пар над носиком
        if self.shown_temp > 75 and self.shown_level > 0.05 and random.random() < (self.shown_temp - 75) / 25 * 0.6:
            self.steam.append([cx - 108 + random.uniform(-6, 6), y0 - 10, random.uniform(6, 10), 150.0])
        for puff in self.steam:
            puff[1] -= 1.4
            puff[0] -= 0.4 + random.uniform(-0.4, 0.4)
            puff[2] += 0.35
            puff[3] -= 2.4
        self.steam = [puff for puff in self.steam if puff[3] > 0]
        self.update()

    def body_path(self):
        cx, y0, bh = self.geometry_info()
        tw, bw = 70, 94  # полуширина колбы сверху и снизу
        path = QPainterPath()
        path.moveTo(cx - tw + 14, y0)
        path.lineTo(cx + tw - 14, y0)
        path.quadTo(cx + tw, y0, cx + tw + 2, y0 + 16)
        path.lineTo(cx + bw - 2, y0 + bh - 18)
        path.quadTo(cx + bw, y0 + bh, cx + bw - 18, y0 + bh)
        path.lineTo(cx - bw + 18, y0 + bh)
        path.quadTo(cx - bw, y0 + bh, cx - bw + 2, y0 + bh - 18)
        path.lineTo(cx - tw - 2, y0 + 16)
        path.quadTo(cx - tw, y0, cx - tw + 14, y0)
        return path

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.device["settings"]
        cx, y0, bh = self.geometry_info()
        on = bool(self.device["is_on"])
        heating = kettle_is_heating(self.device)
        keeping = on and not heating and s.get("keep_warm")

        # подставка с LED-подсветкой
        if s.get("color") and on:
            led = QColor(s["color"])
        elif heating:
            led = QColor("#ff6b3d")
        elif keeping:
            led = QColor("#f5a623")
        else:
            led = QColor("#59636e")
        if heating or keeping:
            glow = QRadialGradient(QPointF(cx, y0 + bh + 14), 150)
            glow.setColorAt(0, _color(led.name(), 120))
            glow.setColorAt(1, _color(led.name(), 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(cx, y0 + bh + 14), 150, 50)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2f3640"))
        p.drawRoundedRect(QRectF(cx - 114, y0 + bh - 4, 228, 32), 12, 12)
        p.setBrush(led)
        p.drawRoundedRect(QRectF(cx - 80, y0 + bh + 10, 160, 6), 3, 3)

        # ручка
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#2f3640"), 16, Qt.SolidLine, Qt.RoundCap))
        handle = QPainterPath()
        handle.moveTo(cx + 74, y0 + 26)
        handle.cubicTo(cx + 150, y0 + 22, cx + 150, y0 + 170, cx + 92, y0 + 176)
        p.drawPath(handle)

        # носик
        spout = QPolygonF([QPointF(cx - 66, y0 + 6), QPointF(cx - 112, y0 - 8),
                           QPointF(cx - 106, y0 + 14), QPointF(cx - 72, y0 + 44)])
        p.setPen(QPen(QColor("#9fb3c3"), 3))
        p.setBrush(_color("#e1f0fa", 130))
        p.drawPolygon(spout)

        # стеклянная колба
        body = self.body_path()
        p.setBrush(_color("#e1f0fa", 110))
        p.setPen(Qt.NoPen)
        p.drawPath(body)

        # вода с волнами
        if self.shown_level > 0.01:
            p.save()
            p.setClipPath(body)
            t = (self.shown_temp - 20) / 80
            water = _lerp_color(QColor("#3d9df5"), QColor("#ff7a45"), t)
            top = self.water_top()
            amp = 3 + (5 * max(0, self.shown_temp - 60) / 40 if heating else 0)
            for layer, (alpha, shift) in enumerate(((110, 1.7), (200, 0.0))):
                wave = QPainterPath()
                wave.moveTo(cx - 120, y0 + bh + 5)
                x = cx - 120
                while x <= cx + 120:
                    y = top + amp * math.sin(x / 19 + self.phase + shift) + amp * 0.4 * math.sin(x / 7 - self.phase * 1.6)
                    wave.lineTo(x, y + layer * 3)
                    x += 4
                wave.lineTo(cx + 120, y0 + bh + 5)
                wave.closeSubpath()
                grad = QLinearGradient(0, top, 0, y0 + bh)
                grad.setColorAt(0, _color(water.lighter(125).name(), alpha))
                grad.setColorAt(1, _color(water.darker(115).name(), alpha))
                p.setBrush(grad)
                p.drawPath(wave)
            p.setBrush(_color("#ffffff", 170))
            for bx, by, br, _ in self.bubbles:
                p.drawEllipse(QPointF(bx, by), br, br)
            p.restore()

        # блик на стекле и контур
        p.setPen(Qt.NoPen)
        p.setBrush(_color("#ffffff", 70))
        p.drawRoundedRect(QRectF(cx - 60, y0 + 22, 14, bh - 60), 7, 7)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#9fb3c3"), 3))
        p.drawPath(body)

        # шкала объёма
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        marks = [ml for ml in (500, 1000, 1500) if ml < self.capacity] + [self.capacity]
        for ml in marks:
            y = y0 + bh - 8 - ml / self.capacity * (bh - 22)
            p.setPen(QPen(_color("#5f7a8f", 200), 2))
            p.drawLine(QPointF(cx + 42, y), QPointF(cx + 60, y))
            p.setPen(_color("#5f7a8f", 230))
            label = "MAX" if ml == self.capacity else f"{ml / 1000:.1f}"
            p.drawText(QRectF(cx + 4, y - 8, 34, 16), Qt.AlignRight | Qt.AlignVCenter, label)

        # крышка
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2f3640"))
        p.drawRoundedRect(QRectF(cx - 62, y0 - 16, 124, 18), 8, 8)
        p.drawRoundedRect(QRectF(cx - 15, y0 - 28, 30, 14), 6, 6)

        # пар
        for px, py, pr, pa in self.steam:
            p.setBrush(_color("#c9d6df", int(max(0, pa))))
            p.drawEllipse(QPointF(px, py), pr, pr * 0.8)

        # температура
        temp_font = QFont(self.font())
        temp_font.setPixelSize(40)
        temp_font.setBold(True)
        p.setFont(temp_font)
        text_rect = QRectF(cx - 90, y0 + 40, 150, 56)
        p.setPen(_color("#000000", 70))
        p.drawText(text_rect.translated(2, 2), Qt.AlignCenter, f"{self.shown_temp:.0f}°")
        p.setPen(QColor("#12293c") if self.shown_level < 0.55 else QColor("white"))
        p.drawText(text_rect, Qt.AlignCenter, f"{self.shown_temp:.0f}°")

        small = QFont(self.font())
        small.setPixelSize(13)
        small.setBold(True)
        p.setFont(small)
        if s.get("water_ml", 0) < MIN_KETTLE_WATER_ML:
            caption, color = "Налейте воду", QColor("#e5484d")
        elif heating:
            caption, color = f"нагрев до {s.get('target_temp')}°", QColor("#e0662f")
        elif keeping:
            caption, color = "поддержание", QColor("#c98a00")
        else:
            caption, color = f"цель {s.get('target_temp')}°", QColor("#5f7a8f")
        p.setPen(color)
        p.drawText(QRectF(cx - 90, y0 + 92, 150, 20), Qt.AlignCenter, caption)


# ---------- сцены для камер ----------

SCENE_W, SCENE_H = 2400, 900   # нарисованная «панорама» комнаты
VIEW_W = 1600                  # ширина кадра камеры внутри панорамы (поворотные камеры двигают кадр)
CAMERA_PHOTOS_DIR = os.path.join(APP_DIR, "cameras")
SNAPSHOTS_DIR = os.path.join(APP_DIR, "snapshots")    # снимки с камер сохраняются рядом с программой


def _vgrad(y1, y2, c1, c2):
    g = QLinearGradient(0, y1, 0, y2)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    return QBrush(g)


def _box(p, x, y, w, h, brush, radius=0, pen=None):
    p.setPen(pen if pen is not None else Qt.NoPen)
    p.setBrush(QColor(brush) if isinstance(brush, str) else brush)
    if radius:
        p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)
    else:
        p.drawRect(QRectF(x, y, w, h))


def _sky(p, x, y, w, h, night):
    p.fillRect(QRectF(x, y, w, h), _vgrad(y, y + h, "#0b1430", "#2a3d66") if night else _vgrad(y, y + h, "#5aa9e6", "#d9f0fd"))
    rng = random.Random(int(x * 7 + w))
    p.setPen(Qt.NoPen)
    if night:
        for _ in range(int(w * h / 6000)):
            p.setBrush(_color("#ffffff", rng.randint(90, 230)))
            p.drawEllipse(QPointF(x + rng.random() * w, y + rng.random() * h * 0.8), 1.8, 1.8)
    else:
        for _ in range(max(1, int(w / 330))):
            cx, cy = x + rng.random() * w, y + rng.uniform(0.12, 0.45) * h
            p.setBrush(_color("#ffffff", 215))
            for dx, dy, r in ((0, 0, 34), (36, 6, 28), (-36, 8, 26), (14, -16, 26)):
                p.drawEllipse(QPointF(cx + dx, cy + dy), r * 1.4, r)


def _trees_line(p, x, y, w, seed, night):
    rng = random.Random(seed)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#2f5d34") if night else QColor("#4f8f4a"))
    p.drawEllipse(QRectF(x - w * 0.1, y - 40, w * 1.2, 120))
    for _ in range(int(w / 70)):
        r = rng.uniform(30, 60)
        p.setBrush(QColor("#2a5530" if night else rng.choice(["#3f7f3f", "#4c9a4c", "#5aa652"])))
        p.drawEllipse(QPointF(x + rng.random() * w, y - r * 0.6), r, r)


def _window(p, x, y, w, h, night):
    p.save()
    p.setClipRect(QRectF(x, y, w, h))
    _sky(p, x, y, w, h, night)
    _trees_line(p, x, y + h * 0.82, w, int(x), night)
    p.restore()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("#f5f5f5"), 16))
    p.drawRect(QRectF(x, y, w, h))
    p.setPen(QPen(QColor("#f5f5f5"), 10))
    p.drawLine(QPointF(x + w / 2, y), QPointF(x + w / 2, y + h))
    p.drawLine(QPointF(x, y + h * 0.4), QPointF(x + w, y + h * 0.4))
    _box(p, x - 24, y + h + 4, w + 48, 18, "#f0f0f0", 4)


def _wood_floor(p, y0, w, h, c1, c2):
    p.fillRect(QRectF(0, y0, w, h - y0), _vgrad(y0, h, c1, c2))
    p.setPen(QPen(_color("#000000", 32), 2))
    for i in range(1, 9):
        y = y0 + (h - y0) * (i / 8) ** 1.7
        p.drawLine(QPointF(0, y), QPointF(w, y))
    vx = w / 2
    for k in range(-16, 17):
        p.drawLine(QPointF(vx + k * 70, y0), QPointF(vx + k * 270, h))


def _tile_floor(p, y0, w, h, c1, c2):
    p.fillRect(QRectF(0, y0, w, h - y0), QColor(c1))
    rows = 6
    vx = w / 2
    p.setPen(Qt.NoPen)
    for r in range(rows):
        ya = y0 + (h - y0) * (r / rows) ** 1.4
        yb = y0 + (h - y0) * ((r + 1) / rows) ** 1.4
        ka = 1 + (ya - y0) / (h - y0) * 2.2
        kb = 1 + (yb - y0) / (h - y0) * 2.2
        for k in range(-14, 14):
            if (k + r) % 2:
                continue
            quad = QPolygonF([QPointF(vx + k * 110 * ka, ya), QPointF(vx + (k + 1) * 110 * ka, ya),
                              QPointF(vx + (k + 1) * 110 * kb, yb), QPointF(vx + k * 110 * kb, yb)])
            p.setBrush(QColor(c2))
            p.drawPolygon(quad)


def _plant(p, x, base_y, s=1.0):
    pot = QPolygonF([QPointF(x - 46 * s, base_y - 80 * s), QPointF(x + 46 * s, base_y - 80 * s),
                     QPointF(x + 34 * s, base_y), QPointF(x - 34 * s, base_y)])
    p.setPen(Qt.NoPen)
    for dx, dy, rot, col in ((-30, -10, -35, "#3f8f4f"), (30, -10, 35, "#3f8f4f"), (0, -30, 0, "#4fa860"),
                             (-18, -20, -15, "#5bb86b"), (18, -22, 18, "#46995a")):
        p.save()
        p.translate(x + dx * s, base_y - 80 * s + dy * s)
        p.rotate(rot)
        p.setBrush(QColor(col))
        p.drawEllipse(QRectF(-20 * s, -95 * s, 40 * s, 110 * s))
        p.restore()
    p.setBrush(QColor("#c0703a"))
    p.drawPolygon(pot)


def _lamp_glow(p, x, y, radius, night):
    if not night:
        return
    g = QRadialGradient(QPointF(x, y), radius)
    g.setColorAt(0, _color("#ffd38a", 170))
    g.setColorAt(1, _color("#ffd38a", 0))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(x, y), radius, radius)


def _scene_living(p, w, h, night):
    y0 = h * 0.68
    p.fillRect(QRectF(0, 0, w, y0), _vgrad(0, y0, "#e4eaef", "#d3dde5"))
    _wood_floor(p, y0, w, h, "#c08f61", "#946640")
    _box(p, 0, y0 - 14, w, 14, "#f7f7f7")
    _window(p, 170, 110, 520, 380, night)
    _box(p, 110, 86, 70, 480, "#c9d6df", 12)
    _box(p, 680, 86, 70, 480, "#c9d6df", 12)
    _box(p, 960, 130, 560, 320, "#111418", 10)
    _box(p, 975, 145, 530, 290, _vgrad(145, 435, "#24303f", "#0d1117"), 4)
    _box(p, 900, 470, 680, 110, "#5b4636", 10)
    _box(p, 920, 490, 300, 70, "#6a5342", 6)
    _box(p, 1260, 490, 300, 70, "#6a5342", 6)
    p.setBrush(QColor("#d9c7b0"))
    p.drawEllipse(QRectF(860, 690, 1000, 180))
    _box(p, 1700, 360, 560, 190, "#7b8794", 34)
    _box(p, 1680, 500, 600, 150, "#6b7684", 26)
    _box(p, 1650, 440, 80, 230, "#5f6977", 26)
    _box(p, 2240, 440, 80, 230, "#5f6977", 26)
    _box(p, 1760, 410, 130, 110, "#e0a458", 22)
    _box(p, 2090, 410, 130, 110, "#5fa8a0", 22)
    _box(p, 1150, 650, 420, 36, "#3e3b39", 12)
    _box(p, 1180, 686, 16, 80, "#3e3b39")
    _box(p, 1524, 686, 16, 80, "#3e3b39")
    _box(p, 1860, 140, 290, 180, "#ffffff", 6)
    for i, col in enumerate(("#e07a5f", "#3d405b", "#81b29a", "#f2cc8f")):
        p.setBrush(QColor(col))
        p.drawEllipse(QPointF(1910 + i * 62, 230 + (i % 2) * 20), 34, 34)
    _box(p, 2361, 230, 8, 420, "#333333")
    shade = QPolygonF([QPointF(2310, 150), QPointF(2420, 150), QPointF(2440, 240), QPointF(2290, 240)])
    p.setBrush(QColor("#f1e3c8"))
    p.drawPolygon(shade)
    _lamp_glow(p, 2365, 220, 220, night)
    _plant(p, 820, 640, 1.3)


def _scene_kitchen(p, w, h, night):
    p.fillRect(QRectF(0, 0, w, h), QColor("#eef1f3"))
    _box(p, 60, 340, 1760, 220, "#fafafa")
    p.setPen(QPen(_color("#c9d1d8"), 2))
    for x in range(60, 1820, 60):
        p.drawLine(QPointF(x, 340), QPointF(x, 560))
    for y in range(340, 561, 55):
        p.drawLine(QPointF(60, y), QPointF(1820, y))
    _window(p, 730, 90, 420, 230, night)
    for x0, x1 in ((60, 690), (1190, 1820)):
        for x in range(x0, x1, 210):
            _box(p, x, 60, 200, 260, "#ffffff", 8, QPen(QColor("#d5dbe0"), 2))
            _box(p, x + 90, 250, 20, 46, "#9aa5b1", 6)
    _box(p, 40, 560, 1800, 40, "#3a3f47", 6)
    for x in range(60, 1820, 220):
        _box(p, x, 600, 210, 260, "#f4f4f4", 8, QPen(QColor("#d5dbe0"), 2))
        _box(p, x + 80, 620, 50, 12, "#9aa5b1", 6)
    _box(p, 300, 545, 320, 18, "#1f2329", 4)
    p.setBrush(QColor("#3b4048"))
    for bx in (360, 450, 540):
        p.drawEllipse(QPointF(bx, 554), 34, 7)
    _box(p, 820, 548, 260, 16, "#aeb6bd", 6)
    p.setPen(QPen(QColor("#8d969e"), 10, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(950, 548), QPointF(950, 480))
    p.drawLine(QPointF(950, 480), QPointF(1000, 480))
    _box(p, 1300, 470, 110, 90, "#e8e8e8", 22)
    _box(p, 1310, 455, 90, 20, "#2f3640", 8)
    p.setBrush(QColor("#d84b4b"))
    p.drawEllipse(QPointF(1560, 535), 24, 24)
    p.setBrush(QColor("#f2c14e"))
    p.drawEllipse(QPointF(1600, 528), 26, 26)
    p.setBrush(QColor("#6ab04c"))
    p.drawEllipse(QPointF(1640, 538), 22, 22)
    _box(p, 1880, 70, 440, 800, _vgrad(70, 870, "#e2e6ea", "#b5bcc3"), 18)
    p.setPen(QPen(QColor("#9aa3ab"), 3))
    p.drawLine(QPointF(1880, 380), QPointF(2320, 380))
    _box(p, 1910, 180, 14, 150, "#8d969e", 6)
    _box(p, 1910, 420, 14, 200, "#8d969e", 6)
    _box(p, 0, 860, w, h - 860, "#cfd5da")
    p.setPen(QPen(QColor("#555"), 3))
    p.drawLine(QPointF(1200, 0), QPointF(1200, 0))
    _lamp_glow(p, 940, 330, 260, night)


def _scene_bedroom(p, w, h, night):
    y0 = h * 0.7
    p.fillRect(QRectF(0, 0, w, y0), _vgrad(0, y0, "#ece6f4", "#ddd4ea"))
    _wood_floor(p, y0, w, h, "#d2ab84", "#ad845c")
    _window(p, 140, 120, 480, 380, night)
    _box(p, 90, 90, 80, 480, "#8e7cc3", 14)
    _box(p, 590, 90, 80, 480, "#8e7cc3", 14)
    p.setBrush(QColor("#cbbfe0"))
    p.drawEllipse(QRectF(760, 700, 1060, 170))
    _box(p, 860, 250, 780, 300, "#6c5b7b", 30)
    _box(p, 820, 470, 860, 170, "#fbfbfb", 24)
    _box(p, 820, 540, 860, 230, "#8fb3d9", 22)
    p.setPen(QPen(_color("#6d93bb"), 3))
    p.drawLine(QPointF(830, 600), QPointF(1670, 600))
    _box(p, 900, 410, 300, 110, "#ffffff", 34)
    _box(p, 1300, 410, 300, 110, "#ffffff", 34)
    for nx in (640, 1700):
        _box(p, nx, 560, 160, 170, "#a77b55", 10)
        _box(p, nx + 60, 500, 40, 60, "#d9d9d9", 6)
        shade = QPolygonF([QPointF(nx + 40, 430), QPointF(nx + 120, 430), QPointF(nx + 140, 500), QPointF(nx + 20, 500)])
        p.setBrush(QColor("#f6e7c8"))
        p.drawPolygon(shade)
        _lamp_glow(p, nx + 80, 470, 170, night)
    _box(p, 1080, 110, 340, 120, "#ffffff", 6)
    p.setBrush(QColor("#a7c4a0"))
    p.drawEllipse(QRectF(1110, 130, 280, 80))
    _box(p, 2000, 120, 360, 700, "#a77b55", 12)
    p.setPen(QPen(QColor("#8a6342"), 4))
    p.drawLine(QPointF(2180, 130), QPointF(2180, 810))
    _box(p, 2150, 430, 12, 70, "#e0c38c", 4)
    _box(p, 2198, 430, 12, 70, "#e0c38c", 4)


def _scene_hallway(p, w, h, night):
    y0 = h * 0.72
    p.fillRect(QRectF(0, 0, w, y0), _vgrad(0, y0, "#eee4d3", "#e2d5bf"))
    _tile_floor(p, y0, w, h, "#d8d3cc", "#bfb8ae")
    _box(p, 1010, 100, 380, y0 - 100, "#ffffff", 6)
    _box(p, 1040, 125, 320, y0 - 125, "#7a5232", 6)
    for (px, py, pw, ph) in ((1070, 160, 120, 180), (1210, 160, 120, 180), (1070, 380, 120, 220), (1210, 380, 120, 220)):
        _box(p, px, py, pw, ph, "#6a4628", 6)
    _box(p, 1180, 140, 40, 14, "#b0b9c2", 4)
    p.setBrush(QColor("#d4af37"))
    p.drawEllipse(QPointF(1330, 400), 13, 13)
    _box(p, 1300, 395, 40, 10, "#d4af37", 5)
    p.setBrush(QColor("#9c8a72"))
    p.drawEllipse(QRectF(980, 690, 440, 110))
    _box(p, 200, 170, 440, 34, "#8a6342", 6)
    for hx in range(240, 640, 80):
        _box(p, hx, 200, 10, 30, "#444444", 4)
    _box(p, 220, 220, 130, 320, "#34495e", 26)
    _box(p, 370, 220, 120, 280, "#b5523b", 26)
    _box(p, 510, 220, 90, 230, "#c9a227", 22)
    _box(p, 190, 570, 470, 30, "#8a6342", 6)
    _box(p, 200, 600, 20, 70, "#8a6342")
    _box(p, 630, 600, 20, 70, "#8a6342")
    p.setBrush(QColor("#333333"))
    for sx in (250, 330, 450, 530):
        p.drawEllipse(QRectF(sx, 660, 64, 26))
    _box(p, 1650, 130, 320, 460, "#c7a77b", 40)
    _box(p, 1670, 150, 280, 420, _vgrad(150, 570, "#e9f1f6", "#b8c8d4"), 30)
    _plant(p, 2180, 660, 1.3)
    p.setBrush(QColor("#f6e7c8"))
    p.drawEllipse(QPointF(1200, 30), 70, 22)
    _lamp_glow(p, 1200, 60, 320, night)


def _scene_garage(p, w, h, night):
    y0 = h * 0.7
    p.fillRect(QRectF(0, 0, w, y0), QColor("#b9bec4"))
    p.setPen(QPen(_color("#9ea4ab"), 2))
    for row, y in enumerate(range(0, int(y0), 60)):
        p.drawLine(QPointF(0, y), QPointF(w, y))
        offset = 60 if row % 2 else 0
        for x in range(offset, w, 120):
            p.drawLine(QPointF(x, y), QPointF(x, y + 60))
    p.fillRect(QRectF(0, y0, w, h - y0), _vgrad(y0, h, "#91969c", "#6e7378"))
    p.setPen(Qt.NoPen)
    p.setBrush(_color("#2b2f33", 70))
    p.drawEllipse(QRectF(900, 760, 380, 70))
    # стеллаж
    _box(p, 60, 130, 18, 520, "#5d6670")
    _box(p, 340, 130, 18, 520, "#5d6670")
    for i, y in enumerate((200, 330, 460, 590)):
        _box(p, 60, y, 298, 14, "#7a838d")
        for j, col in enumerate(("#c58b4e", "#4f7cac", "#8fbc8f")[: 2 + i % 2]):
            _box(p, 80 + j * 90, y - 70, 80, 70, col, 6)
    # зарядная станция
    _box(p, 430, 250, 110, 170, "#f4f6f8", 18)
    _box(p, 455, 280, 60, 36, "#1f2a36", 6)
    _box(p, 455, 335, 60, 8, "#00d27a", 4)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor("#222"), 12, Qt.SolidLine, Qt.RoundCap))
    cable = QPainterPath()
    cable.moveTo(485, 420)
    cable.cubicTo(480, 640, 640, 640, 700, 520)
    p.drawPath(cable)
    # автомобиль
    _box(p, 620, 450, 880, 160, "#c0392b", 50)
    cabin = QPolygonF([QPointF(760, 460), QPointF(880, 340), QPointF(1240, 340), QPointF(1390, 460)])
    p.setBrush(QColor("#c0392b"))
    p.drawPolygon(cabin)
    p.setBrush(QColor("#9ecbe6"))
    p.drawPolygon(QPolygonF([QPointF(795, 455), QPointF(895, 360), QPointF(1050, 360), QPointF(1050, 455)]))
    p.drawPolygon(QPolygonF([QPointF(1070, 360), QPointF(1228, 360), QPointF(1345, 455), QPointF(1070, 455)]))
    p.setPen(QPen(_color("#8e2a20"), 3))
    p.drawLine(QPointF(1060, 460), QPointF(1060, 600))
    p.setPen(Qt.NoPen)
    _box(p, 1475, 490, 28, 34, "#ffe08a", 6)
    for wx in (790, 1340):
        p.setBrush(QColor("#1d1f22"))
        p.drawEllipse(QPointF(wx, 610), 72, 72)
        p.setBrush(QColor("#b4bcc4"))
        p.drawEllipse(QPointF(wx, 610), 34, 34)
    # гаражные ворота
    _box(p, 1600, 110, 740, 530, "#4b535c", 6)
    _box(p, 1620, 130, 700, 510, "#dfe3e7")
    p.setPen(QPen(_color("#b9c0c7"), 4))
    for y in range(215, 640, 85):
        p.drawLine(QPointF(1620, y), QPointF(2320, y))
    p.setPen(Qt.NoPen)
    for x in range(1660, 2300, 160):
        _box(p, x, 150, 120, 45, "#8fb5cf", 6)
    _lamp_glow(p, 1100, 40, 380, night)


def _scene_terrace(p, w, h, night):
    _sky(p, 0, 0, w, h * 0.6, night)
    if night:
        p.setBrush(QColor("#f4f1d0"))
        p.drawEllipse(QPointF(1900, 210), 46, 46)
    else:
        g = QRadialGradient(QPointF(1900, 210), 140)
        g.setColorAt(0, _color("#fff6c2", 255))
        g.setColorAt(0.4, _color("#ffe066", 200))
        g.setColorAt(1, _color("#ffe066", 0))
        p.setBrush(g)
        p.drawEllipse(QPointF(1900, 210), 140, 140)
    _trees_line(p, 0, h * 0.52, w, 3, night)
    p.fillRect(QRectF(0, h * 0.52, w, h * 0.2), QColor("#3e6b35" if night else "#7cbf5a"))
    _wood_floor(p, h * 0.7, w, h, "#a8774f", "#7d5130")
    # перила
    _box(p, 0, h * 0.57, w, 18, "#6b4a2f")
    _box(p, 0, h * 0.69, w, 14, "#6b4a2f")
    for x in range(20, w, 70):
        _box(p, x, h * 0.57, 14, h * 0.13, "#7b5638")
    # навес с солнечными панелями
    _box(p, 0, 0, w, 40, "#5d4029")
    for i in range(8):
        x = 50 + i * 292
        _box(p, x, 40, 272, 112, _vgrad(40, 152, "#1d3d6e", "#2f5f9e"), 4)
        p.setPen(QPen(_color("#ffffff", 70), 2))
        for k in range(1, 4):
            p.drawLine(QPointF(x + k * 68, 40), QPointF(x + k * 68, 152))
        p.drawLine(QPointF(x, 96), QPointF(x + 272, 96))
    _box(p, 30, 0, 44, h * 0.72, "#5d4029")
    _box(p, w - 74, 0, 44, h * 0.72, "#5d4029")
    # гирлянда
    for x in range(100, w, 110):
        y = 200 + 26 * math.sin(x / 240)
        if night:
            _lamp_glow(p, x, y, 40, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffd86b") if night else QColor("#f1e6c3"))
        p.drawEllipse(QPointF(x, y), 9, 9)
    # стол и стулья
    p.setBrush(QColor("#ece3d5"))
    p.drawEllipse(QRectF(1020, 640, 420, 60))
    _box(p, 1220, 690, 22, 130, "#6b4a2f")
    for cx, flip in ((900, -1), (1560, 1)):
        _box(p, cx - 70, 690, 140, 26, "#7b5638", 8)
        _box(p, cx + flip * 60 - 10, 560, 20, 140, "#7b5638", 6)
        _box(p, cx - 60, 716, 14, 110, "#7b5638")
        _box(p, cx + 46, 716, 14, 110, "#7b5638")
    _plant(p, 320, 860, 1.6)
    _plant(p, 2080, 860, 1.6)


def _scene_porch(p, w, h, night):
    """Вид с дверного звонка: двор, дорожка к калитке, забор."""
    _sky(p, 0, 0, w, h * 0.5, night)
    _trees_line(p, 0, h * 0.45, w, 11, night)
    p.fillRect(QRectF(0, h * 0.5, w, h * 0.5), QColor("#3e6b35" if night else "#7cbf5a"))
    for x in range(0, w, 46):
        if w / 2 - 170 < x < w / 2 + 130:
            continue
        pick = QPolygonF([QPointF(x, h * 0.46), QPointF(x + 16, h * 0.43), QPointF(x + 32, h * 0.46),
                          QPointF(x + 32, h * 0.6), QPointF(x, h * 0.6)])
        p.setBrush(QColor("#d6d6d6" if night else "#f7f7f7"))
        p.drawPolygon(pick)
    _box(p, 0, h * 0.5, w / 2 - 170, 12, "#e2e2e2")
    _box(p, w / 2 + 160, h * 0.5, w / 2, 12, "#e2e2e2")
    path = QPolygonF([QPointF(w / 2 - 150, h * 0.6), QPointF(w / 2 + 150, h * 0.6),
                      QPointF(w / 2 + 560, h), QPointF(w / 2 - 560, h)])
    p.setBrush(QColor("#c9c3b8"))
    p.drawPolygon(path)
    p.setPen(QPen(_color("#a39c90"), 3))
    for i in range(1, 8):
        t = (i / 8) ** 1.5
        y = h * 0.6 + (h * 0.4) * t
        half = 150 + 410 * t
        p.drawLine(QPointF(w / 2 - half, y), QPointF(w / 2 + half, y))
    p.setPen(Qt.NoPen)
    _box(p, 1620, 520, 18, 220, "#555")
    _box(p, 1580, 470, 100, 70, "#2f5f9e", 12)
    _box(p, 560, 200, 16, 480, "#3a3f47")
    _box(p, 520, 180, 96, 34, "#3a3f47", 10)
    p.setBrush(QColor("#ffe7a3") if night else QColor("#e9edf0"))
    p.drawEllipse(QPointF(568, 222), 26, 16)
    _lamp_glow(p, 568, 230, 260, night)
    for bx in (300, 820, 1700, 2150):
        p.setBrush(QColor("#2d5a2f" if night else "#4c9a4c"))
        p.drawEllipse(QPointF(bx, h * 0.6), 90, 60)
    _box(p, w / 2 - 620, h - 60, 1240, 60, "#b0a79a")


SCENE_PAINTERS = {
    "living": _scene_living, "kitchen": _scene_kitchen, "bedroom": _scene_bedroom,
    "hallway": _scene_hallway, "garage": _scene_garage, "terrace": _scene_terrace, "porch": _scene_porch,
}


def scene_kind(room_name, model):
    if model.get("outdoor"):
        return "porch"
    name = room_name.lower()
    for keys, kind in ((("террас", "терас", "балкон", "двор", "сад", "улиц"), "terrace"),
                       (("прихож", "коридор", "холл", "вход"), "hallway"),
                       (("гараж",), "garage"), (("кух",), "kitchen"),
                       (("спальн", "детск"), "bedroom")):
        if any(k in name for k in keys):
            return kind
    return "living"


def find_room_photo(room_name):
    """Своя фотография комнаты для камеры: cameras/<Название комнаты>.jpg|png рядом с home.py."""
    if not os.path.isdir(CAMERA_PHOTOS_DIR):
        return None
    wanted = room_name.strip().lower()
    for file_name in os.listdir(CAMERA_PHOTOS_DIR):
        stem, ext = os.path.splitext(file_name)
        if stem.strip().lower() == wanted and ext.lower() in (".jpg", ".jpeg", ".png"):
            pix = QPixmap(os.path.join(CAMERA_PHOTOS_DIR, file_name))
            if pix.isNull():
                return None
            pix = pix.scaled(SCENE_W, SCENE_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            return pix.copy((pix.width() - SCENE_W) // 2, (pix.height() - SCENE_H) // 2, SCENE_W, SCENE_H)
    return None


def _draw_person(p, x, foot_y, height, phase, body_color):
    s = height / 180
    swing = math.sin(phase) * 14 * s
    p.setPen(QPen(QColor("#2b2f36"), 17 * s, Qt.SolidLine, Qt.RoundCap))
    hip = QPointF(x, foot_y - 86 * s)
    p.drawLine(hip, QPointF(x + swing, foot_y))
    p.drawLine(hip, QPointF(x - swing, foot_y))
    p.setPen(QPen(QColor(body_color).darker(115), 13 * s, Qt.SolidLine, Qt.RoundCap))
    shoulder = QPointF(x, foot_y - 140 * s)
    p.drawLine(shoulder, QPointF(x - swing * 0.9, foot_y - 82 * s))
    p.drawLine(shoulder, QPointF(x + swing * 0.9, foot_y - 82 * s))
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(body_color))
    p.drawRoundedRect(QRectF(x - 24 * s, foot_y - 152 * s, 48 * s, 74 * s), 16 * s, 16 * s)
    p.setBrush(QColor("#e2b48c"))
    p.drawEllipse(QPointF(x, foot_y - 170 * s), 17 * s, 18 * s)
    p.setBrush(QColor("#3b2a20"))
    p.drawChord(QRectF(x - 18 * s, foot_y - 190 * s, 36 * s, 30 * s), 0, 180 * 16)


class CameraView(QWidget):
    """
    «Живое видео» с камеры: нарисованная сцена комнаты (или своё фото из папки cameras/),
    ночью - темнота / ИК-режим / свет от включённых в комнате ламп, проходящие люди
    с рамкой детекции движения, метка времени по часам дома, индикатор записи и шум матрицы.
    """

    def __init__(self, main, device, parent=None):
        super().__init__(parent)
        self.main = main
        self.device = device
        self.model = MODELS[device["model_code"]]
        self.ptz = bool(self.model.get("ptz"))
        self.pan = 0.5
        self.pan_target = 0.5
        self.cache = {}
        self.person = None
        self.frame = 0
        self.setMinimumSize(560, 315)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(335)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)

    def kind(self):
        return scene_kind(self.device["room_name"], self.model)

    def scene(self, variant):
        key = (self.device["room_name"], variant)
        if key in self.cache:
            return self.cache[key]
        if variant == "ir":
            # ИК-картинка: ночная сцена в оттенках серого, подсвеченная ИК-прожектором камеры
            image = self.scene("night").toImage().convertToFormat(QImage.Format_Grayscale8)
            pix = QPixmap.fromImage(image)
            painter = QPainter(pix)
            painter.fillRect(pix.rect(), QColor(255, 255, 255, 45))
            painter.end()
        else:
            pix = find_room_photo(self.device["room_name"])
            if pix is None:
                pix = QPixmap(SCENE_W, SCENE_H)
                pix.fill(Qt.black)
                painter = QPainter(pix)
                painter.setRenderHint(QPainter.Antialiasing)
                SCENE_PAINTERS[self.kind()](painter, SCENE_W, SCENE_H, variant == "night")
                painter.end()
        self.cache[key] = pix
        return pix

    def pan_by(self, delta):
        self.pan_target = max(0.0, min(1.0, self.pan_target + delta))

    def _tick(self):
        self.frame += 1
        self.pan += (self.pan_target - self.pan) * 0.12
        if self.person is None:
            if self.device["is_on"] and random.random() < 0.006:
                direction = random.choice((-1, 1))
                self.person = {
                    "x": -150 if direction > 0 else SCENE_W + 150, "dir": direction,
                    "speed": random.uniform(7, 11), "phase": 0.0,
                    "color": random.choice(["#3d6fb6", "#b5523b", "#4f9a6a", "#7b5ea7", "#333d4a"]),
                }
        else:
            self.person["x"] += self.person["dir"] * self.person["speed"]
            self.person["phase"] += 0.32
            if not -200 <= self.person["x"] <= SCENE_W + 200:
                self.person = None
        self.update()

    def source_x(self):
        return self.pan * (SCENE_W - VIEW_W) if self.ptz else (SCENE_W - VIEW_W) / 2

    def person_in_view(self):
        if self.person is None:
            return False
        sx = self.source_x()
        return sx - 60 < self.person["x"] < sx + VIEW_W + 60

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, 14, 14)
        p.setClipPath(clip)
        s = self.device["settings"]

        if not self.device["is_on"]:
            p.fillRect(r, QColor("#0d1117"))
            p.setPen(QColor("#6b7785"))
            font = QFont(self.font())
            font.setPixelSize(16)
            p.setFont(font)
            p.drawText(r, Qt.AlignCenter, "📷  Камера выключена")
            return

        state = self.main.simulator.state or {}
        sim_minutes = state.get("sim_minutes", 12 * 60)
        hour = (sim_minutes / 60) % 24
        night = not 6.5 <= hour < 19.5
        lights_on = any(
            d["is_on"] and d["room_id"] == self.device["room_id"] and DEVICE_TYPES[d["type_code"]]["group"] == LIGHT_GROUP
            for d in self.main.devices
        )
        outdoor = self.kind() in ("terrace", "porch")
        lit = lights_on and not outdoor
        ir = night and not lit and s.get("night_vision")
        variant = "day" if not night else ("ir" if ir else "night")

        sx = self.source_x()
        p.drawPixmap(r, self.scene(variant), QRectF(sx, 0, VIEW_W, SCENE_H))

        kx, ky = r.width() / VIEW_W, r.height() / SCENE_H
        if self.person is not None:
            p.save()
            p.scale(kx, ky)
            p.translate(-sx, 0)
            foot, height = (SCENE_H * 0.86, SCENE_H * 0.42) if self.kind() == "porch" else (SCENE_H * 0.95, SCENE_H * 0.62)
            _draw_person(p, self.person["x"], foot, height, self.person["phase"],
                         "#9a9a9a" if ir else self.person["color"])
            p.restore()

        if night and not ir:
            p.fillRect(r, QColor(255, 170, 70, 30) if lit else QColor(5, 10, 25, 185))
        if ir:
            p.fillRect(r, QColor(30, 60, 30, 45))

        if self.person_in_view() and s.get("motion_alerts", True):
            foot, height = (SCENE_H * 0.86, SCENE_H * 0.42) if self.kind() == "porch" else (SCENE_H * 0.95, SCENE_H * 0.62)
            bx = (self.person["x"] - sx - height * 0.22) * kx
            by = (foot - height * 1.12) * ky
            box = QRectF(bx, by, height * 0.44 * kx, height * 1.14 * ky)
            p.setPen(QPen(QColor("#00e676"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(box)
            font = QFont(self.font())
            font.setPixelSize(11)
            font.setBold(True)
            p.setFont(font)
            label = QRectF(box.left(), box.top() - 18, 118, 18)
            p.fillRect(label, QColor("#00a85a"))
            p.setPen(Qt.white)
            p.drawText(label, Qt.AlignCenter, f"Человек {88 + self.frame // 7 % 10}%")

        # шум матрицы
        rng = random.Random(self.frame)
        for _ in range(260 if night else 120):
            p.setPen(QColor(255, 255, 255, rng.randint(12, 55)))
            p.drawPoint(QPointF(rng.random() * r.width(), rng.random() * r.height()))

        vignette = QRadialGradient(r.center(), r.width() * 0.7)
        vignette.setColorAt(0.55, QColor(0, 0, 0, 0))
        vignette.setColorAt(1, QColor(0, 0, 0, 150))
        p.fillRect(r, vignette)

        # служебная информация
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)

        def tag(text, x, y, align_right=False, bg=QColor(0, 0, 0, 130), fg=Qt.white):
            w = fm.horizontalAdvance(text) + 16
            rect = QRectF(x - w if align_right else x, y, w, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(rect, 6, 6)
            p.setPen(fg)
            p.drawText(rect, Qt.AlignCenter, text)

        tag(f"{self.device['name']} · {self.device['room_name']}", 10, 10)
        stamp = datetime.now().strftime("%d.%m.%Y") + f"  {sim_time_text(sim_minutes)}:{datetime.now().second:02d}"
        tag(stamp, r.width() - 10, 10, align_right=True)
        tag(f"LIVE · {self.model.get('resolution', '1080p')}", 10, r.height() - 32)
        x_right = r.width() - 10
        if s.get("recording") and (self.frame // 12) % 2 == 0:
            tag("● REC", x_right, r.height() - 32, align_right=True, bg=QColor(200, 30, 30, 200))
            x_right -= 72
        if ir:
            tag("IR · ночное видение", x_right, r.height() - 32, align_right=True)
        elif night and lit:
            tag("💡 свет в комнате", x_right, r.height() - 32, align_right=True)
        elif night:
            tag("ночь · ИК выключен", x_right, r.height() - 32, align_right=True)

    def snapshot(self):
        folder = SNAPSHOTS_DIR
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{self.device['name']}_{datetime.now():%Y%m%d_%H%M%S}.png".replace(" ", "_"))
        self.grab().save(path)
        return path


# ---------- климат: термостат, кондиционер, обогреватель ----------

def climate_status(device, room_temp):
    """Текстовый статус кондиционера/обогревателя и цвет для подсветки."""
    s = device["settings"]
    if not device["is_on"]:
        return "Выключен", QColor("#8aa0b2")
    target = s.get("target_temp", 22)
    active = device.get("_climate_active", True)
    if device["type_code"] == "heater":
        return ("🔥 Нагревает комнату", QColor("#e0662f")) if active else ("✅ Температура достигнута", QColor(ACCENT))
    mode = s.get("mode", "Охлаждение")
    if mode == "Вентиляция":
        return "🌀 Вентиляция", QColor("#5f7a8f")
    if mode == "Осушение":
        return "💧 Осушение воздуха", QColor("#3d9df5")
    if not active:
        return "✅ Температура достигнута", QColor(ACCENT)
    if mode == "Обогрев" or (mode == "Авто" and room_temp < target):
        return "🔥 Обогревает комнату", QColor("#e0662f")
    return "❄️ Охлаждает комнату", QColor("#2f8de4")


class ThermostatDial(QWidget):
    """Круглый регулятор температуры: дуга 270°, ручка перетаскивается мышью или колесом."""

    valueChanged = pyqtSignal(int)

    def __init__(self, lo, hi, value, info_provider, parent=None):
        super().__init__(parent)
        self.lo, self.hi = lo, hi
        self.value = value
        self.info_provider = info_provider  # -> (температура в комнате, текст статуса, цвет)
        self.setFixedSize(250, 250)
        self.setCursor(Qt.PointingHandCursor)
        self._dragging = False

    def set_value(self, value, emit=True):
        value = int(max(self.lo, min(self.hi, round(value))))
        if value != self.value:
            self.value = value
            if emit:
                self.valueChanged.emit(value)
        self.update()

    def _geometry(self):
        side = min(self.width(), self.height()) - 24
        c = QPointF(self.width() / 2, self.height() / 2)
        return c, side / 2

    def _angle_for(self, value):
        t = (value - self.lo) / (self.hi - self.lo)
        return 225 - 270 * t

    def _value_from_pos(self, pos):
        c, _ = self._geometry()
        a = math.degrees(math.atan2(-(pos.y() - c.y()), pos.x() - c.x()))
        if a < -90:
            a += 360
        t = (225 - a) / 270
        if t < 0 or t > 1:
            t = 0 if abs(t) < abs(t - 1) else 1
        return self.lo + t * (self.hi - self.lo)

    def mousePressEvent(self, e):
        self._dragging = True
        self.set_value(self._value_from_pos(e.pos()))

    def mouseMoveEvent(self, e):
        if self._dragging:
            self.set_value(self._value_from_pos(e.pos()))

    def mouseReleaseEvent(self, e):
        self._dragging = False

    def wheelEvent(self, e):
        self.set_value(self.value + (1 if e.angleDelta().y() > 0 else -1))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, R = self._geometry()
        room_temp, status, color = self.info_provider()

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 18))
        p.drawEllipse(c + QPointF(0, 4), R, R)
        face = QRadialGradient(c, R)
        face.setColorAt(0, QColor("#ffffff"))
        face.setColorAt(1, QColor("#eef3f7"))
        p.setBrush(face)
        p.drawEllipse(c, R, R)

        arc_r = R - 18
        arc_rect = QRectF(c.x() - arc_r, c.y() - arc_r, arc_r * 2, arc_r * 2)
        p.setPen(QPen(QColor("#e3edf4"), 14, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc_rect, 225 * 16, -270 * 16)
        t = (self.value - self.lo) / (self.hi - self.lo)
        p.setPen(QPen(color, 14, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc_rect, 225 * 16, int(-270 * t * 16))

        # деления
        p.setPen(QPen(QColor("#b9c7d2"), 2))
        for v in range(self.lo, self.hi + 1):
            a = math.radians(self._angle_for(v))
            r1, r2 = arc_r - 16, arc_r - (24 if v % 5 == 0 else 20)
            p.drawLine(QPointF(c.x() + r1 * math.cos(a), c.y() - r1 * math.sin(a)),
                       QPointF(c.x() + r2 * math.cos(a), c.y() - r2 * math.sin(a)))

        # отметка текущей температуры в комнате
        if room_temp is not None:
            rt = max(self.lo, min(self.hi, room_temp))
            a = math.radians(self._angle_for(rt))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#12293c"))
            p.drawEllipse(QPointF(c.x() + arc_r * math.cos(a), c.y() - arc_r * math.sin(a)), 4, 4)

        # ручка
        a = math.radians(self._angle_for(self.value))
        knob = QPointF(c.x() + arc_r * math.cos(a), c.y() - arc_r * math.sin(a))
        p.setBrush(QColor("white"))
        p.setPen(QPen(color, 4))
        p.drawEllipse(knob, 11, 11)

        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#8aa0b2"))
        p.drawText(QRectF(c.x() - 60, c.y() - 62, 120, 16), Qt.AlignCenter, "ЦЕЛЬ")
        font.setPixelSize(48)
        p.setFont(font)
        p.setPen(QColor("#12293c"))
        p.drawText(QRectF(c.x() - 80, c.y() - 48, 160, 60), Qt.AlignCenter, f"{self.value}°")
        font.setPixelSize(13)
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor("#5f7a8f"))
        if room_temp is not None:
            p.drawText(QRectF(c.x() - 80, c.y() + 14, 160, 18), Qt.AlignCenter, f"в комнате {room_temp:.1f}°")
        font.setBold(True)
        font.setPixelSize(12)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QRectF(c.x() - 90, c.y() + 36, 180, 18), Qt.AlignCenter, status)


class ClimateWidget(QWidget):
    """
    Кондиционер: внутренний блок с качающейся шторкой и поток воздуха из него -
    снежинки при охлаждении, волны тепла при обогреве, капли при осушении.
    Фон «комнаты» меняет оттенок вместе с её температурой.
    """

    def __init__(self, main, device, parent=None):
        super().__init__(parent)
        self.main = main
        self.device = device
        self.model = MODELS[device["model_code"]]
        self.particles = []
        self.phase = 0.0
        self.setFixedHeight(230)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def room_temp(self):
        return self.main.room_temps.get(self.device["room_id"], ROOM_TEMP)

    def flow_kind(self):
        s = self.device["settings"]
        mode = s.get("mode", "Охлаждение")
        if mode == "Вентиляция":
            return "air"
        if mode == "Осушение":
            return "drop"
        if mode == "Обогрев" or (mode == "Авто" and self.room_temp() < s.get("target_temp", 22)):
            return "heat"
        return "snow"

    def unit_rect(self):
        w = min(440, self.width() - 80)
        return QRectF((self.width() - w) / 2, 16, w, 78)

    def _tick(self):
        self.phase += 0.05
        on = bool(self.device["is_on"])
        s = self.device["settings"]
        levels = self.model.get("levels", 3)
        fan = s.get("fan_speed", 2) / levels
        active = self.device.get("_climate_active", True)
        unit = self.unit_rect()
        if on:
            rate = (0.6 + 2.2 * fan) * (1.0 if active else 0.35)
            while rate > 0:
                if random.random() < min(1.0, rate):
                    x = random.uniform(unit.left() + 30, unit.right() - 30)
                    self.particles.append({
                        "x": x, "y": unit.bottom() + 6,
                        "vx": (x - unit.center().x()) * 0.004 + random.uniform(-0.4, 0.4),
                        "vy": 1.0 + 2.2 * fan + random.uniform(0, 0.8),
                        "life": 1.0, "rot": random.uniform(0, 360), "kind": self.flow_kind(),
                    })
                rate -= 1
        for pt in self.particles:
            pt["x"] += pt["vx"]
            pt["y"] += pt["vy"]
            pt["vy"] *= 0.995
            pt["rot"] += 3
            pt["life"] -= 0.012
        self.particles = [pt for pt in self.particles if pt["life"] > 0 and pt["y"] < self.height() + 10]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        temp = self.room_temp()
        t = (temp - 16) / 14
        bg = QLinearGradient(r.topLeft(), r.bottomLeft())
        bg.setColorAt(0, _lerp_color(QColor("#d7e9ff"), QColor("#ffe2cf"), t))
        bg.setColorAt(1, _lerp_color(QColor("#eef6ff"), QColor("#fff3ea"), t))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 16, 16)

        s = self.device["settings"]
        on = bool(self.device["is_on"])
        unit = self.unit_rect()

        # частицы потока
        for pt in self.particles:
            alpha = int(220 * pt["life"])
            if pt["kind"] == "snow":
                p.save()
                p.translate(pt["x"], pt["y"])
                p.rotate(pt["rot"])
                p.setPen(QPen(QColor(61, 157, 245, alpha), 2))
                for k in range(3):
                    p.drawLine(QPointF(-6, 0), QPointF(6, 0))
                    p.rotate(60)
                p.restore()
            elif pt["kind"] == "heat":
                p.setPen(QPen(QColor(255, 122, 69, alpha), 2.5))
                path = QPainterPath(QPointF(pt["x"] - 10, pt["y"]))
                for i in range(1, 6):
                    path.lineTo(pt["x"] - 10 + i * 4, pt["y"] + 3 * math.sin(i * 1.4 + self.phase * 4))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
            elif pt["kind"] == "drop":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(61, 157, 245, alpha))
                p.drawEllipse(QPointF(pt["x"], pt["y"]), 3, 4.5)
            else:
                p.setPen(QPen(QColor(120, 140, 160, alpha), 2))
                p.drawLine(QPointF(pt["x"], pt["y"]), QPointF(pt["x"] - pt["vx"] * 4, pt["y"] - 10))

        # внутренний блок
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 25))
        p.drawRoundedRect(unit.translated(0, 4), 20, 20)
        body = QLinearGradient(unit.topLeft(), unit.bottomLeft())
        body.setColorAt(0, QColor("#ffffff"))
        body.setColorAt(1, QColor("#e8edf1"))
        p.setBrush(body)
        p.setPen(QPen(QColor("#d3dce3"), 2))
        p.drawRoundedRect(unit, 20, 20)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#cfd8df"))
        p.drawRoundedRect(QRectF(unit.left() + 24, unit.bottom() - 18, unit.width() - 48, 8), 4, 4)

        display = QRectF(unit.right() - 104, unit.top() + 16, 80, 32)
        p.setBrush(QColor("#1b2430"))
        p.drawRoundedRect(display, 8, 8)
        font = QFont(self.font())
        font.setPixelSize(18)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#5fd1ff") if on else QColor("#3a4654"))
        p.drawText(display, Qt.AlignCenter, f"{s.get('target_temp', 22)}°C" if on else "--")
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#00d27a") if on else QColor("#9aa5b1"))
        p.drawEllipse(QPointF(unit.left() + 30, unit.top() + 22), 4, 4)
        font.setPixelSize(11)
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor("#9aa5b1"))
        p.drawText(QRectF(unit.left() + 40, unit.top() + 14, 200, 16), Qt.AlignLeft | Qt.AlignVCenter, "inverter")

        # шторка: при работе приоткрыта и плавно качается вверх-вниз
        opening = (10 + 6 * math.sin(self.phase * 1.2)) if on else 2
        y = unit.bottom() - 6
        flap = QPolygonF([QPointF(unit.left() + 26, y), QPointF(unit.right() - 26, y),
                          QPointF(unit.right() - 34, y + opening), QPointF(unit.left() + 34, y + opening)])
        p.setBrush(QColor("#f4f6f8"))
        p.setPen(QPen(QColor("#c5ced6"), 1.5))
        p.drawPolygon(flap)

        # подпись внизу
        status, color = climate_status(self.device, temp)
        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        tag_rect = QRectF(14, r.bottom() - 36, 230, 26)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawRoundedRect(tag_rect, 8, 8)
        p.setPen(QColor("#12293c"))
        p.drawText(tag_rect, Qt.AlignCenter, f"🌡 В комнате {temp:.1f}°C")
        tag2 = QRectF(r.right() - 244, r.bottom() - 36, 230, 26)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(tag2, 8, 8)
        p.setPen(color)
        p.drawText(tag2, Qt.AlignCenter, status)


class HeaterWidget(QWidget):
    """Обогреватель: раскаляющиеся рёбра, волны тепла и термометр комнаты."""

    def __init__(self, main, device, parent=None):
        super().__init__(parent)
        self.main = main
        self.device = device
        self.phase = 0.0
        self.setFixedHeight(240)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def room_temp(self):
        return self.main.room_temps.get(self.device["room_id"], ROOM_TEMP)

    def intensity(self):
        if not self.device["is_on"]:
            return 0.0
        mode_factor = dict(TYPE_MODES["heater"]).get(self.device["settings"].get("mode"), 0.75)
        base = mode_factor if self.device.get("_climate_active", True) else 0.3
        return base * (0.9 + 0.1 * math.sin(self.phase * 3))

    def _tick(self):
        self.phase += 0.05
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        temp = self.room_temp()
        t = (temp - 10) / 22
        bg = QLinearGradient(r.topLeft(), r.bottomLeft())
        bg.setColorAt(0, _lerp_color(QColor("#dbe8f5"), QColor("#ffd9c2"), t))
        bg.setColorAt(1, _lerp_color(QColor("#f1f6fb"), QColor("#fff1e8"), t))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 16, 16)

        k = self.intensity()
        heater = QRectF(r.center().x() - 210, r.bottom() - 120, 340, 100)

        # волны тепла
        if k > 0:
            for i in range(7):
                x0 = heater.left() + 30 + i * (heater.width() - 60) / 6
                path = QPainterPath(QPointF(x0, heater.top() - 4))
                for step in range(1, 26):
                    y = heater.top() - 4 - step * 6
                    x = x0 + 7 * math.sin(step * 0.45 - self.phase * 4 + i)
                    path.lineTo(x, y)
                grad = QLinearGradient(0, heater.top(), 0, heater.top() - 150)
                grad.setColorAt(0, QColor(255, 110, 50, int(200 * k)))
                grad.setColorAt(1, QColor(255, 110, 50, 0))
                p.setPen(QPen(QBrush(grad), 3, Qt.SolidLine, Qt.RoundCap))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
            glow = QRadialGradient(QPointF(heater.center().x(), heater.top() + 10), 220)
            glow.setColorAt(0, QColor(255, 120, 60, int(110 * k)))
            glow.setColorAt(1, QColor(255, 120, 60, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(heater.center().x(), heater.top() + 10), 220, 90)

        # корпус
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#9aa5b1"))
        p.drawRoundedRect(QRectF(heater.left() + 30, heater.bottom() - 4, 14, 20), 4, 4)
        p.drawRoundedRect(QRectF(heater.right() - 44, heater.bottom() - 4, 14, 20), 4, 4)
        p.setBrush(QColor("#f5f6f8"))
        p.setPen(QPen(QColor("#d3dce3"), 2))
        p.drawRoundedRect(heater, 16, 16)
        grille = QRectF(heater.left() + 16, heater.top() + 12, heater.width() - 32, 30)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#3a4350"))
        p.drawRoundedRect(grille, 8, 8)
        fin = _lerp_color(QColor("#6b7682"), QColor("#ff5a1f"), k)
        p.setBrush(fin)
        x = grille.left() + 10
        while x < grille.right() - 10:
            p.drawRoundedRect(QRectF(x, grille.top() + 5, 7, grille.height() - 10), 3, 3)
            x += 14
        display = QRectF(heater.right() - 110, heater.bottom() - 42, 90, 28)
        p.setBrush(QColor("#1b2430"))
        p.drawRoundedRect(display, 7, 7)
        font = QFont(self.font())
        font.setPixelSize(15)
        font.setBold(True)
        p.setFont(font)
        on = bool(self.device["is_on"])
        p.setPen(QColor("#ff9a5c") if on else QColor("#3a4654"))
        p.drawText(display, Qt.AlignCenter, f"{self.device['settings'].get('target_temp', 25)}°C" if on else "--")

        # термометр комнаты
        tube = QRectF(r.right() - 74, r.top() + 22, 16, r.height() - 76)
        bulb_c = QPointF(tube.center().x(), tube.bottom() + 12)
        level = max(0.0, min(1.0, (temp - 10) / 22))
        liquid = _lerp_color(QColor("#3d9df5"), QColor("#ff4d1a"), level)
        p.setPen(QPen(QColor("#c5ced6"), 2))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(tube.adjusted(-3, -3, 3, 3), 10, 10)
        p.drawEllipse(bulb_c, 17, 17)
        p.setPen(Qt.NoPen)
        p.setBrush(liquid)
        p.drawEllipse(bulb_c, 12, 12)
        fill_h = tube.height() * level
        p.drawRoundedRect(QRectF(tube.left() + 3, tube.bottom() - fill_h, tube.width() - 6, fill_h + 6), 4, 4)
        font.setPixelSize(10)
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor("#5f7a8f"))
        for v in (10, 15, 20, 25, 30):
            y = tube.bottom() - tube.height() * (v - 10) / 22
            p.drawLine(QPointF(tube.left() - 8, y), QPointF(tube.left() - 3, y))
            p.drawText(QRectF(tube.left() - 34, y - 7, 24, 14), Qt.AlignRight | Qt.AlignVCenter, str(v))

        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        status, color = climate_status(self.device, temp)
        tag = QRectF(14, 14, 250, 26)
        p.setBrush(QColor(255, 255, 255, 200))
        p.drawRoundedRect(tag, 8, 8)
        p.setPen(color)
        p.drawText(tag, Qt.AlignCenter, status)
        tag2 = QRectF(14, 46, 250, 26)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(tag2, 8, 8)
        p.setPen(QColor("#12293c"))
        p.drawText(tag2, Qt.AlignCenter, f"🌡 В комнате {temp:.1f}°C")


# ---------- робот-пылесос ----------

class RobotVacuumWidget(QWidget):
    """Карта комнаты: робот едет «змейкой», за ним остаётся чистая полоса, затем возвращается на базу."""

    ROWS = 9

    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.device = device
        s = device["settings"]
        self.shown_progress = s.get("vac_progress", 0.0)
        self.shown_return = s.get("vac_return", 0.0)
        self.phase = 0.0
        rng = random.Random(device["id"])
        self.dust = [(rng.uniform(0.03, 0.97), rng.uniform(0.05, 0.95), rng.uniform(1, 2.6)) for _ in range(320)]
        self.path = []
        y_values = [0.9 - i * 0.8 / (self.ROWS - 1) for i in range(self.ROWS)]
        for i, y in enumerate(y_values):
            xs = (0.08, 0.92) if i % 2 == 0 else (0.92, 0.08)
            self.path.append((xs[0], y))
            self.path.append((xs[1], y))
        self.dock = (0.04, 0.97)
        self.setFixedHeight(320)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def map_rect(self):
        return QRectF(14, 46, self.width() - 28, self.height() - 60)

    def to_px(self, pt):
        m = self.map_rect()
        return QPointF(m.left() + pt[0] * m.width(), m.top() + pt[1] * m.height())

    def _lengths(self):
        pts = [self.to_px(pt) for pt in self.path]
        lengths = [0.0]
        for a, b in zip(pts, pts[1:]):
            lengths.append(lengths[-1] + math.hypot(b.x() - a.x(), b.y() - a.y()))
        return pts, lengths

    def position_at(self, progress):
        pts, lengths = self._lengths()
        target = max(0.0, min(1.0, progress)) * lengths[-1]
        for i in range(1, len(pts)):
            if lengths[i] >= target:
                seg = lengths[i] - lengths[i - 1] or 1
                k = (target - lengths[i - 1]) / seg
                a, b = pts[i - 1], pts[i]
                return QPointF(a.x() + (b.x() - a.x()) * k, a.y() + (b.y() - a.y()) * k), \
                    math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x())), i
        return pts[-1], 0.0, len(pts) - 1

    def _tick(self):
        s = self.device["settings"]
        self.shown_progress += (s.get("vac_progress", 0.0) - self.shown_progress) * 0.08
        self.shown_return += (s.get("vac_return", 0.0) - self.shown_return) * 0.08
        self.phase += 0.35
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.device["settings"]
        state = s.get("vac_state", "docked")
        m = self.map_rect()

        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 16, 16)

        # пол с пылью
        p.setBrush(QColor("#e6dccb"))
        p.setPen(QPen(QColor("#5d6670"), 5))
        p.drawRoundedRect(m, 10, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#d9c7b0"))
        p.drawEllipse(QRectF(m.center().x() - m.width() * 0.18, m.center().y() - m.height() * 0.18,
                             m.width() * 0.36, m.height() * 0.36))
        for x, y, size in self.dust:
            p.setBrush(QColor(110, 90, 70, 150))
            p.drawEllipse(QPointF(m.left() + x * m.width(), m.top() + y * m.height()), size, size)

        # убранная полоса
        progress = self.shown_progress if state != "docked" or s.get("vac_progress", 0) > 0 else 0.0
        if progress > 0.001:
            pos, _, idx = self.position_at(progress)
            pts, _ = self._lengths()
            trail = QPainterPath(pts[0])
            for pt in pts[1:idx]:
                trail.lineTo(pt)
            trail.lineTo(pos)
            row_px = m.height() * 0.8 / (self.ROWS - 1)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#f8f4ec"), row_px + 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(trail)
            p.setPen(QPen(QColor(0, 0, 0, 14), 2))
            p.drawPath(trail)

        # база
        dock = self.to_px(self.dock)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2f3640"))
        p.drawRoundedRect(QRectF(dock.x() - 16, dock.y() - 8, 32, 14), 4, 4)
        p.setBrush(QColor("#00d27a"))
        p.drawEllipse(QPointF(dock.x(), dock.y() - 1), 3, 3)

        # положение робота
        if state in ("cleaning", "paused"):
            robot, angle, _ = self.position_at(self.shown_progress)
        elif state == "returning":
            start, _, _ = self.position_at(s.get("vac_progress", 0.0))
            k = self.shown_return
            robot = QPointF(start.x() + (dock.x() - start.x()) * k, start.y() + (dock.y() - 22 - start.y()) * k)
            angle = math.degrees(math.atan2(dock.y() - start.y(), dock.x() - start.x()))
            p.setPen(QPen(QColor(0, 168, 90, 160), 2, Qt.DashLine))
            p.drawLine(robot, QPointF(dock.x(), dock.y() - 20))
        else:
            robot, angle = QPointF(dock.x(), dock.y() - 22), -90.0

        p.save()
        p.translate(robot)
        p.rotate(angle)
        if state == "cleaning":
            p.setPen(QPen(QColor("#5d6670"), 1.5))
            for k in range(3):
                a = math.radians(self.phase * 40 + k * 120)
                p.drawLine(QPointF(10, 10), QPointF(10 + 7 * math.cos(a), 10 + 7 * math.sin(a)))
        p.setPen(QPen(QColor("#2f3640"), 2))
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(0, 0), 14, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2f3640"))
        p.drawEllipse(QPointF(-2, 0), 5, 5)
        p.setPen(QPen(QColor("#00b96b") if state == "cleaning" else QColor("#9aa5b1"), 3))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(-14, -14, 28, 28), -50 * 16, 100 * 16)
        p.restore()

        # верхняя строка
        font = QFont(self.font())
        font.setPixelSize(13)
        font.setBold(True)
        p.setFont(font)
        status = {
            "cleaning": f"🧹 Уборка · {s.get('vac_progress', 0) * 100:.0f}% · ≈{s.get('vac_progress', 0) * 18:.0f} м²",
            "paused": f"⏸ Пауза · {s.get('vac_progress', 0) * 100:.0f}%",
            "returning": "↩️ Возвращается на базу",
            "docked": "🏠 На базе" + (" · заряжается ⚡" if s.get("vac_battery", 100) < 99.5 else ""),
        }[state]
        p.setPen(QColor("#12293c"))
        p.drawText(QRectF(18, 10, self.width() - 200, 26), Qt.AlignLeft | Qt.AlignVCenter, status)

        battery = s.get("vac_battery", 100)
        bar = QRectF(self.width() - 150, 16, 110, 14)
        p.setPen(QPen(QColor("#9fb3c3"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(bar, 4, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ACCENT) if battery > 40 else (QColor("#f5a623") if battery > 15 else QColor("#e5484d")))
        p.drawRoundedRect(QRectF(bar.left() + 2, bar.top() + 2, (bar.width() - 4) * battery / 100, bar.height() - 4), 3, 3)
        p.setPen(QColor("#12293c"))
        p.drawText(QRectF(bar.right() + 4, bar.top() - 4, 40, 22), Qt.AlignLeft | Qt.AlignVCenter, f"{battery:.0f}%")


# ---------- стиральная машина ----------

class WasherWidget(QWidget):
    """Стиральная машина: вращающийся барабан с бельём и водой, этапы программы и оставшееся время."""

    CLOTHES = ["#e07a5f", "#3d405b", "#81b29a", "#f2cc8f", "#5fa8d3"]

    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.device = device
        self.rot = 0.0
        self.tick_n = 0
        self.setFixedHeight(330)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def phase(self):
        if not self.device["is_on"]:
            return None
        return washer_phase(washer_fraction(self.device["settings"]))

    def _tick(self):
        self.tick_n += 1
        phase = self.phase()
        direction = 1 if math.sin(self.tick_n / 45) >= 0 else -1
        speed = {None: 0.0, "Нагрев воды": 0.03 * direction, "Стирка": 0.09 * direction,
                 "Полоскание": 0.11 * direction, "Отжим": 0.55}[phase]
        self.rot += speed
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = self.device["settings"]
        phase = self.phase()
        frac = washer_fraction(s) if self.device["is_on"] else (1.0 if s.get("wash_done") else 0.0)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 16, 16)

        shake = QPointF(random.uniform(-1.5, 1.5), random.uniform(-1.2, 1.2)) if phase == "Отжим" else QPointF(0, 0)
        body = QRectF(24, 16, 250, 296).translated(shake)
        p.setBrush(QColor(0, 0, 0, 22))
        p.drawRoundedRect(body.translated(0, 5), 20, 20)
        p.setBrush(QColor("#f7f8fa"))
        p.setPen(QPen(QColor("#d3dce3"), 2))
        p.drawRoundedRect(body, 20, 20)
        p.setPen(QPen(QColor("#e1e7ec"), 2))
        p.drawLine(QPointF(body.left(), body.top() + 56), QPointF(body.right(), body.top() + 56))

        display = QRectF(body.left() + 18, body.top() + 14, 96, 30)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1b2430"))
        p.drawRoundedRect(display, 6, 6)
        left = washer_total(s) * (1 - washer_fraction(s))
        font = QFont(self.font())
        font.setPixelSize(17)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#5fe3a1") if phase else QColor("#3a4654"))
        p.drawText(display, Qt.AlignCenter, f"{int(left // 60)}:{int(left % 60):02d}" if phase else ("End" if s.get("wash_done") else "--:--"))
        p.setPen(QPen(QColor("#c5ced6"), 2))
        p.setBrush(QColor("#eef2f5"))
        knob_c = QPointF(body.right() - 34, body.top() + 29)
        p.drawEllipse(knob_c, 15, 15)
        a = math.radians(-60 + 40 * list(WASH_DURATIONS).index(s.get("mode", "Хлопок 60°")) if s.get("mode") in WASH_DURATIONS else 0)
        p.drawLine(knob_c, QPointF(knob_c.x() + 11 * math.cos(a), knob_c.y() + 11 * math.sin(a)))

        # дверца
        c = QPointF(body.center().x(), body.top() + 56 + (body.height() - 56) / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#c9d1d8"))
        p.drawEllipse(c, 98, 98)
        p.setBrush(QColor("#e9eef2"))
        p.drawEllipse(c, 88, 88)
        glass = QPainterPath()
        glass.addEllipse(c, 76, 76)
        p.save()
        p.setClipPath(glass)
        g = QRadialGradient(c, 76)
        g.setColorAt(0, QColor("#4b5b6b"))
        g.setColorAt(1, QColor("#26313c"))
        p.setBrush(g)
        p.drawEllipse(c, 76, 76)
        # отверстия барабана
        p.setBrush(QColor(255, 255, 255, 25))
        for ring in (40, 60):
            for k in range(14):
                a = self.rot + k * 2 * math.pi / 14
                p.drawEllipse(QPointF(c.x() + ring * math.cos(a), c.y() + ring * math.sin(a)), 3, 3)
        # вода
        if phase in ("Нагрев воды", "Стирка", "Полоскание"):
            level = c.y() + (22 if phase != "Полоскание" else 30)
            wave = QPainterPath(QPointF(c.x() - 80, c.y() + 80))
            x = c.x() - 80
            while x <= c.x() + 80:
                wave.lineTo(x, level + 4 * math.sin(x / 12 + self.rot * 3))
                x += 4
            wave.lineTo(c.x() + 80, c.y() + 80)
            wave.closeSubpath()
            water = QColor("#5fa8d3") if phase != "Нагрев воды" else _lerp_color(QColor("#5fa8d3"), QColor("#f2a65a"),
                                                                                   washer_fraction(s) / 0.2)
            water.setAlpha(170)
            p.setBrush(water)
            p.drawPath(wave)
            if phase == "Стирка":
                p.setBrush(QColor(255, 255, 255, 200))
                for k in range(12):
                    bx = c.x() - 60 + (k * 37 + self.tick_n * 2) % 120
                    p.drawEllipse(QPointF(bx, level - 2 + 3 * math.sin(k + self.tick_n / 6)), 4 + k % 3, 4 + k % 3)
        # бельё
        for i, color in enumerate(self.CLOTHES):
            offset = i * 2 * math.pi / len(self.CLOTHES)
            if phase == "Отжим":
                radius, a = 58, self.rot + offset
            elif phase:
                a = self.rot * 1.3 + offset
                radius = 26 + 26 * abs(math.sin(self.rot * 0.8 + offset * 1.7))
            else:
                a, radius = math.pi / 2 + (i - 2) * 0.35, 52
            p.setBrush(QColor(color))
            p.save()
            p.translate(c.x() + radius * math.cos(a), c.y() + radius * math.sin(a))
            p.rotate(math.degrees(a) + 90)
            p.drawRoundedRect(QRectF(-16, -9, 32, 18), 8, 8)
            p.restore()
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 90), 6, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(c.x() - 62, c.y() - 62, 124, 124), 110 * 16, 50 * 16)

        # этапы программы справа
        x0 = body.right() + 30
        font.setPixelSize(16)
        p.setFont(font)
        p.setPen(QColor("#12293c"))
        p.drawText(QRectF(x0, 22, self.width() - x0 - 16, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   s.get("mode", "Программа"))
        font.setPixelSize(13)
        font.setBold(False)
        p.setFont(font)
        p.setPen(QColor("#5f7a8f"))
        p.drawText(QRectF(x0, 46, self.width() - x0 - 16, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   f"Длительность {washer_total(s) // 60}:{washer_total(s) % 60:02d} ч")
        steps = [name for _, name in WASH_PHASES] + ["Готово"]
        current = steps.index(phase) if phase else (len(steps) - 1 if s.get("wash_done") else -1)
        for i, name in enumerate(steps):
            y = 86 + i * 40
            done = i < current or (s.get("wash_done") and not phase)
            active = i == current and phase is not None
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT) if done else (QColor("#2f8de4") if active else QColor("#dfe8ef")))
            p.drawEllipse(QPointF(x0 + 12, y + 12), 12, 12)
            font.setBold(True)
            font.setPixelSize(12)
            p.setFont(font)
            p.setPen(Qt.white)
            p.drawText(QRectF(x0, y, 24, 24), Qt.AlignCenter, "✓" if done else str(i + 1))
            font.setPixelSize(14)
            font.setBold(active)
            p.setFont(font)
            p.setPen(QColor("#12293c") if (active or done) else QColor("#8aa0b2"))
            p.drawText(QRectF(x0 + 34, y, 200, 24), Qt.AlignLeft | Qt.AlignVCenter, name)
            if i < len(steps) - 1:
                p.setPen(QPen(QColor(ACCENT) if done else QColor("#dfe8ef"), 3))
                p.drawLine(QPointF(x0 + 12, y + 25), QPointF(x0 + 12, y + 39))
        bar = QRectF(x0, 296, self.width() - x0 - 24, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e3edf4"))
        p.drawRoundedRect(bar, 5, 5)
        p.setBrush(QColor(ACCENT))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * frac, bar.height()), 5, 5)


####################################
###### УПРАВЛЕНИЕ УСТРОЙСТВОМ ######
####################################

class DeviceControlDialog(QDialog):
    """
    Окно управления конкретным устройством. Набор элементов строится по функциям модели:
    яркость, цвет, термостат, режимы, скорость, громкость, таймер, сценарии и т.д.
    Каждое изменение сразу сохраняется и влияет на потребление в симуляции.
    """

    def __init__(self, main, device):
        super().__init__(main)
        self.main = main
        self.device = device
        self.s = device["settings"]
        self.model = MODELS[device["model_code"]]
        self.caps = self.model["caps"]
        self.type_info = DEVICE_TYPES[device["type_code"]]
        self.setAttribute(Qt.WA_DeleteOnClose)  # иначе таймеры анимации камеры/чайника жили бы после закрытия
        self.setWindowTitle(device["name"])
        if "video" in self.caps:
            self.resize(680, 880)
        elif device["type_code"] in ("kettle", "air_conditioner", "heater", "robot_vacuum", "washer"):
            self.resize(600, 900)
        else:
            self.resize(500, 720)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(14)

        # Шапка: иконка, имя, модель, питание
        header = QFrame()
        header.setObjectName("card")
        h = QHBoxLayout(header)
        h.setContentsMargins(18, 16, 18, 16)
        icon = QLabel(self.type_info["icon"])
        icon.setStyleSheet("font-size: 44px;")
        h.addWidget(icon)
        h.addSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.name_label = QLabel(device["name"])
        self.name_label.setStyleSheet("font-size: 19px; font-weight: 700;")
        self.name_label.setWordWrap(True)
        model_label = QLabel(self.model["name"])
        model_label.setObjectName("subtitle")
        self.room_label = QLabel(f"📍 {device['room_name']}")
        self.room_label.setObjectName("subtitle")
        texts.addWidget(self.name_label)
        texts.addWidget(model_label)
        texts.addWidget(self.room_label)
        h.addLayout(texts, 1)
        self.power_switch = ToggleSwitch()
        self.power_switch.set_state_silent(bool(device["is_on"]))
        self.power_switch.toggled.connect(self.on_power_toggled)
        h.addWidget(self.power_switch, alignment=Qt.AlignTop)
        outer.addWidget(header)

        self.live_label = QLabel()
        self.live_label.setTextFormat(Qt.RichText)
        self.live_label.setWordWrap(True)
        self.live_label.setStyleSheet(
            "background: #ffffff; border: 1px solid #dfe8ef; border-radius: 12px; padding: 10px 14px; font-size: 14px;"
        )
        outer.addWidget(self.live_label)

        # Элементы управления
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.controls = QVBoxLayout(host)
        self.controls.setContentsMargins(2, 0, 8, 0)
        self.controls.setSpacing(16)
        scroll.setWidget(host)
        outer.addWidget(scroll, 1)
        self.build_controls()
        self.controls.addStretch()

        # Нижние кнопки
        buttons = QHBoxLayout()
        rename_btn = QPushButton("Переименовать")
        rename_btn.setObjectName("secondary")
        rename_btn.clicked.connect(self.rename)
        delete_btn = QPushButton("Удалить")
        delete_btn.setObjectName("danger")
        delete_btn.clicked.connect(self.delete)
        close_btn = QPushButton("Готово")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(rename_btn)
        buttons.addWidget(delete_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        outer.addLayout(buttons)

        self.refresh_live()

    # ---------- построение элементов ----------

    def _section(self, title, value_label=None):
        box = QVBoxLayout()
        box.setSpacing(8)
        head = QHBoxLayout()
        caption = QLabel(title)
        caption.setObjectName("controlTitle")
        head.addWidget(caption)
        head.addStretch()
        if value_label is not None:
            value_label.setObjectName("controlValue")
            head.addWidget(value_label)
        box.addLayout(head)
        self.controls.addLayout(box)
        return box

    def _slider(self, title, key, lo, hi, fmt, step=1, object_name=None):
        value_label = QLabel()
        box = self._section(title, value_label)
        slider = QSlider(Qt.Horizontal)
        if object_name:
            slider.setObjectName(object_name)
        slider.setRange(lo // step, hi // step)
        slider.setValue(int(self.s.get(key, lo)) // step)
        slider.setCursor(Qt.PointingHandCursor)
        value_label.setText(fmt(slider.value() * step))

        def changed(v):
            self.s[key] = v * step
            value_label.setText(fmt(v * step))
            self.changed()

        slider.valueChanged.connect(changed)
        box.addWidget(slider)
        return slider

    def _toggle_row(self, title, checked, on_change):
        row = QHBoxLayout()
        caption = QLabel(title)
        caption.setObjectName("controlTitle")
        switch = ToggleSwitch()
        switch.set_state_silent(checked)
        switch.toggled.connect(on_change)
        row.addWidget(caption)
        row.addStretch()
        row.addWidget(switch)
        self.controls.addLayout(row)
        return switch

    def build_controls(self):
        caps = self.caps
        type_code = self.device["type_code"]

        if "video" in caps:
            self.build_camera_controls()
        if type_code == "kettle":
            self.build_kettle_controls()
        if type_code in ("air_conditioner", "heater"):
            self.build_climate_controls()
        if type_code == "robot_vacuum":
            self.build_vacuum_controls()
        if type_code == "washer":
            self.build_washer_controls()
        if self.type_info["group"] == LIGHT_GROUP:
            self.light_preview = LightPreview(self.device)
            self.controls.addWidget(self.light_preview)

        if "lock" in caps:
            box = self._section("Замок")
            self.lock_btn = QPushButton()
            self.lock_btn.setCursor(Qt.PointingHandCursor)
            self.lock_btn.clicked.connect(self.toggle_lock)
            box.addWidget(self.lock_btn)
            self._update_lock_button()

        if "mode" in caps:
            modes = TYPE_MODES[type_code]
            title = "Источник сигнала" if type_code == "tv" else "Режим работы"
            box = self._section(title)
            grid = QGridLayout()
            grid.setSpacing(8)
            group = QButtonGroup(self)
            for i, (mode_name, _) in enumerate(modes):
                chip = QPushButton(mode_name)
                chip.setObjectName("chip")
                chip.setCheckable(True)
                chip.setCursor(Qt.PointingHandCursor)
                chip.setChecked(self.s.get("mode") == mode_name)
                chip.clicked.connect(lambda _, m=mode_name: self._set("mode", m))
                group.addButton(chip)
                grid.addWidget(chip, i // 3, i % 3)
            box.addLayout(grid)

        if "target_temp" in caps and type_code not in ("kettle", "air_conditioner", "heater"):
            lo, hi, _ = TYPE_TEMP[type_code]
            title = "Температура воды" if type_code in ("kettle", "water_heater") else "Температура"
            self._slider(title, "target_temp", lo, hi, lambda v: f"{v} °C")

        if "brightness" in caps:
            title = "Яркость экрана" if type_code == "panel" else "Яркость"
            self._slider(title, "brightness", 1, 100, lambda v: f"{v}%")

        if "color_temp" in caps:
            self.ct_slider = self._slider("Цветовая температура", "color_temp", 2700, 6500,
                                          self._ct_text, step=100, object_name="ctSlider")
            if "color" in caps:
                # двигая цветовую температуру, пользователь возвращается к белому свету
                self.ct_slider.valueChanged.connect(lambda _: self.s.get("color") and self._set("color", None))

        if "color" in caps:
            box = self._section("Цвет подсветки")
            row = QHBoxLayout()
            row.setSpacing(8)
            white = QPushButton("Белый")
            white.setObjectName("chip")
            white.setCursor(Qt.PointingHandCursor)
            white.clicked.connect(lambda: self._set("color", None))
            row.addWidget(white)
            for color in COLOR_PRESETS:
                swatch = QPushButton()
                swatch.setFixedSize(32, 32)
                swatch.setCursor(Qt.PointingHandCursor)
                swatch.setStyleSheet(
                    f"QPushButton {{ background: {color}; border-radius: 16px; border: 2px solid white; padding: 0; }}"
                    f"QPushButton:hover {{ border: 2px solid #12293c; }}"
                )
                swatch.clicked.connect(lambda _, c=color: self._set("color", c))
                row.addWidget(swatch)
            other = QPushButton("…")
            other.setObjectName("chip")
            other.setToolTip("Выбрать любой цвет")
            other.setCursor(Qt.PointingHandCursor)
            other.clicked.connect(self.pick_color)
            row.addWidget(other)
            row.addStretch()
            box.addLayout(row)

        if "fan_speed" in caps:
            levels = self.model.get("levels", 3)
            self._slider("Скорость вентилятора", "fan_speed", 1, levels, lambda v: f"{v} из {levels}")

        if "volume" in caps:
            self._slider("Громкость", "volume", 0, 100, lambda v: f"{v}%")

        if "current" in caps:
            self._slider("Ток зарядки", "current", 6, self.model["max_current"],
                         lambda v: f"{v} А · {v * GRID_VOLTAGE / 1000:.1f} кВт")

        if "load" in caps:
            self._slider("Подключённая нагрузка", "load", 0, int(self.model["power"]), format_power, step=10)

        if "keys" in caps:
            keys = self.s.setdefault("keys", [False] * self.model.get("keys", 1))
            for i in range(len(keys)):
                self._toggle_row(f"Клавиша {i + 1}", keys[i], lambda checked, i=i: self._set_key(i, checked))

        for key, title in BOOL_CAPS.items():
            if key in caps:
                self._toggle_row(title, bool(self.s.get(key)), lambda checked, k=key: self._set(k, checked))

        if "timer" in caps:
            box = self._section("Таймер выключения")
            self.timer_combo = QComboBox()
            for caption, minutes in TIMER_OPTIONS:
                self.timer_combo.addItem(caption, minutes)
            current = self.s.get("timer_min", 0) if self.s.get("off_at") is not None else 0
            self.timer_combo.setCurrentIndex(max(0, self.timer_combo.findData(current)))
            self.timer_combo.currentIndexChanged.connect(self.on_timer_changed)
            box.addWidget(self.timer_combo)
            self.timer_hint = QLabel()
            self.timer_hint.setObjectName("subtitle")
            box.addWidget(self.timer_hint)

        if "scenes" in caps:
            box = self._section("Сценарии (по нажатию кнопки)")
            for code, caption in SCENES:
                btn = QPushButton(caption)
                btn.setObjectName("secondary")
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda _, c=code: self.run_scene(c))
                box.addWidget(btn)

        if self.model.get("battery"):
            box = self._section("Питание", QLabel(f"🔋 {self.s.get('battery', 100)}%"))
            hint = QLabel(f"Батарейка {self.model['battery']}")
            hint.setObjectName("subtitle")
            box.addWidget(hint)

        if not any(c in caps for c in CAP_NAMES) and not self.model.get("battery"):
            hint = QLabel("У этой модели нет дополнительных настроек — только включение и выключение.")
            hint.setObjectName("subtitle")
            hint.setWordWrap(True)
            self.controls.addWidget(hint)

        about = QLabel(f"ℹ️  {self.model['desc']}  ·  {model_power_text(self.model)}")
        about.setObjectName("subtitle")
        about.setWordWrap(True)
        self.controls.addWidget(about)

    # ---------- камера ----------

    def build_camera_controls(self):
        self.camera_view = CameraView(self.main, self.device)
        self.controls.addWidget(self.camera_view)
        row = QHBoxLayout()
        row.setSpacing(8)
        if self.camera_view.ptz:
            for text, delta in (("◀  Повернуть", -0.25), ("Повернуть  ▶", 0.25)):
                btn = QPushButton(text)
                btn.setObjectName("secondary")
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda _, d=delta: self.camera_view.pan_by(d))
                row.addWidget(btn)
        shot = QPushButton("📸  Снимок")
        shot.setObjectName("secondary")
        shot.setCursor(Qt.PointingHandCursor)
        shot.clicked.connect(self.take_snapshot)
        row.addWidget(shot)
        row.addStretch()
        self.controls.addLayout(row)
        self.snapshot_label = QLabel()
        self.snapshot_label.setObjectName("subtitle")
        self.snapshot_label.setWordWrap(True)
        self.snapshot_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.controls.addWidget(self.snapshot_label)

    def take_snapshot(self):
        path = self.camera_view.snapshot()
        self.snapshot_label.setText(f"Снимок сохранён: {path}")

    # ---------- кондиционер / обогреватель ----------

    def build_climate_controls(self):
        type_code = self.device["type_code"]
        if type_code == "air_conditioner":
            self.climate_view = ClimateWidget(self.main, self.device)
        else:
            self.climate_view = HeaterWidget(self.main, self.device)
        self.controls.addWidget(self.climate_view)

        lo, hi, _ = TYPE_TEMP[type_code]

        def info():
            temp = self.main.room_temps.get(self.device["room_id"], ROOM_TEMP)
            status, color = climate_status(self.device, temp)
            return temp, status, color

        row = QHBoxLayout()
        minus = QPushButton("−")
        plus = QPushButton("+")
        self.dial = ThermostatDial(lo, hi, int(self.s.get("target_temp", TYPE_TEMP[type_code][2])), info)
        for btn, delta in ((minus, -1), (plus, 1)):
            btn.setObjectName("secondary")
            btn.setFixedSize(56, 56)
            btn.setStyleSheet("font-size: 24px; border-radius: 28px;")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, dl=delta: self.dial.set_value(self.dial.value + dl))
        row.addStretch()
        row.addWidget(minus)
        row.addSpacing(10)
        row.addWidget(self.dial)
        row.addSpacing(10)
        row.addWidget(plus)
        row.addStretch()
        self.controls.addLayout(row)

        def changed(value):
            self.s["target_temp"] = value
            self.device["_climate_active"] = True  # пересчитаем на следующем шаге симуляции
            self.changed()

        self.dial.valueChanged.connect(changed)

    # ---------- робот-пылесос ----------

    def build_vacuum_controls(self):
        self.vacuum_view = RobotVacuumWidget(self.device)
        self.controls.addWidget(self.vacuum_view)
        row = QHBoxLayout()
        self.vac_main_btn = QPushButton()
        self.vac_main_btn.setCursor(Qt.PointingHandCursor)
        self.vac_main_btn.setMinimumHeight(46)
        self.vac_main_btn.clicked.connect(self.vacuum_main_action)
        self.vac_home_btn = QPushButton("🏠  На базу")
        self.vac_home_btn.setObjectName("secondary")
        self.vac_home_btn.setMinimumHeight(46)
        self.vac_home_btn.setCursor(Qt.PointingHandCursor)
        self.vac_home_btn.clicked.connect(lambda: self.power_switch.setChecked(False) if self.device["is_on"]
                                          else self.vacuum_go_home())
        row.addWidget(self.vac_main_btn, 2)
        row.addWidget(self.vac_home_btn, 1)
        self.controls.addLayout(row)

    def vacuum_main_action(self):
        s = self.s
        state = s.get("vac_state", "docked")
        if state == "cleaning":
            s["vac_state"] = "paused"
            self.main.log_event("device", "⏸", f"{self.device['name']}: пауза")
            self.changed()
        elif state == "paused":
            s["vac_state"] = "cleaning"
            self.changed()
        else:
            self.power_switch.setChecked(True)

    def vacuum_go_home(self):
        if self.s.get("vac_state") in ("cleaning", "paused"):
            self.s.update(vac_state="returning", vac_return=0.0)
            self.changed()

    def _refresh_vacuum(self):
        state = self.s.get("vac_state", "docked")
        text = {"cleaning": "⏸  Пауза", "paused": "▶  Продолжить уборку", "returning": "↩️  Едет на базу…",
                "docked": "▶  Начать уборку"}[state]
        self.vac_main_btn.setText(text)
        self.vac_main_btn.setEnabled(state != "returning")
        self.vac_home_btn.setEnabled(state in ("cleaning", "paused"))

    # ---------- стиральная машина ----------

    def build_washer_controls(self):
        self.washer_view = WasherWidget(self.device)
        self.controls.addWidget(self.washer_view)
        self.wash_btn = QPushButton()
        self.wash_btn.setMinimumHeight(48)
        self.wash_btn.setCursor(Qt.PointingHandCursor)
        self.wash_btn.clicked.connect(lambda: self.power_switch.setChecked(not self.device["is_on"]))
        self.controls.addWidget(self.wash_btn)
        hint = QLabel("Программу можно выбрать ниже. Время стирки идёт по часам дома (скорость симуляции).")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        self.controls.addWidget(hint)

    def _refresh_washer(self):
        if self.device["is_on"]:
            self.wash_btn.setText("⏹  Остановить стирку")
            self.wash_btn.setStyleSheet("background-color: #e0662f;")
        else:
            self.wash_btn.setText(f"▶  Запустить «{self.s.get('mode', 'Хлопок 60°')}»")
            self.wash_btn.setStyleSheet("")

    # ---------- чайник ----------

    KETTLE_PRESETS = [(40, "детская смесь"), (60, "белый чай"), (70, "зелёный чай"),
                      (80, "улун"), (90, "кофе"), (100, "кипяток")]

    def build_kettle_controls(self):
        self.kettle_view = KettleWidget(self.device)
        self.controls.addWidget(self.kettle_view)

        self.boil_btn = QPushButton()
        self.boil_btn.setCursor(Qt.PointingHandCursor)
        self.boil_btn.setMinimumHeight(48)
        self.boil_btn.clicked.connect(lambda: self.power_switch.setChecked(not self.device["is_on"]))
        self.controls.addWidget(self.boil_btn)

        # температура: пресеты + ползунок
        temp_value = QLabel()
        box = self._section("Температура нагрева", temp_value)
        grid = QGridLayout()
        grid.setSpacing(8)
        self.preset_group = QButtonGroup(self)
        self.preset_buttons = {}
        for i, (temp, caption) in enumerate(self.KETTLE_PRESETS):
            chip = QPushButton(f"{temp}°  {caption}")
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _, t=temp: self.temp_slider.setValue(t))
            self.preset_group.addButton(chip)
            self.preset_buttons[temp] = chip
            grid.addWidget(chip, i // 3, i % 3)
        box.addLayout(grid)
        lo, hi, _ = TYPE_TEMP["kettle"]
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setRange(lo, hi)
        self.temp_slider.setCursor(Qt.PointingHandCursor)
        self.temp_slider.setValue(int(self.s.get("target_temp", 90)))

        def temp_changed(v):
            self.s["target_temp"] = v
            temp_value.setText(f"{v} °C")
            self._sync_presets()
            self.changed()

        temp_value.setText(f"{self.temp_slider.value()} °C")
        self.temp_slider.valueChanged.connect(temp_changed)
        box.addWidget(self.temp_slider)
        self._sync_presets()

        # объём воды
        capacity = self.model.get("capacity_ml", 1700)
        self.water_value = QLabel()
        box = self._section("Воды в чайнике", self.water_value)
        self.water_slider = QSlider(Qt.Horizontal)
        self.water_slider.setRange(0, capacity // 50)
        self.water_slider.setValue(int(self.s.get("water_ml", 0)) // 50)
        self.water_slider.setCursor(Qt.PointingHandCursor)
        self.water_slider.valueChanged.connect(lambda v: self.set_water(v * 50))
        box.addWidget(self.water_slider)
        row = QHBoxLayout()
        for caption, action in (("💧 Налить до MAX", lambda: capacity), ("+ 250 мл", lambda: self.s.get("water_ml", 0) + 250),
                                ("Вылить", lambda: 0)):
            btn = QPushButton(caption)
            btn.setObjectName("secondary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, a=action: self.water_slider.setValue(min(capacity, a()) // 50))
            row.addWidget(btn)
        box.addLayout(row)
        self._update_water_label()

    def _sync_presets(self):
        current = self.s.get("target_temp")
        self.preset_group.setExclusive(False)
        for temp, chip in self.preset_buttons.items():
            chip.setChecked(temp == current)
        self.preset_group.setExclusive(True)

    def set_water(self, ml):
        old = self.s.get("water_ml", 0)
        if ml > old:
            # долили холодной воды - температура смешивается
            temp = self.s.get("water_temp", ROOM_TEMP)
            self.s["water_temp"] = (old * temp + (ml - old) * ROOM_TEMP) / ml
        elif ml == 0:
            self.s["water_temp"] = ROOM_TEMP
        self.s["water_ml"] = ml
        self._update_water_label()
        self.changed()

    def _update_water_label(self):
        capacity = self.model.get("capacity_ml", 1700)
        ml = self.s.get("water_ml", 0)
        self.water_value.setText(f"{ml / 1000:.2f} л из {capacity / 1000:.1f} л")

    def _refresh_kettle(self):
        s = self.s
        if s.get("water_ml", 0) < MIN_KETTLE_WATER_ML:
            text, style = "💧 Налейте воду (минимум 150 мл)", "background-color: #9aa5b1;"
        elif kettle_is_heating(self.device):
            left = (s["target_temp"] - s["water_temp"]) * s["water_ml"] / 1000 * 4186 / (
                self.model["power"] * KETTLE_SPEEDUP)
            text, style = f"⏹  Остановить нагрев  ·  осталось ≈{left:.0f} сек", "background-color: #e0662f;"
        elif self.device["is_on"]:
            text, style = "⏹  Выключить поддержание температуры", "background-color: #f5a623;"
        else:
            target = s.get("target_temp", 100)
            text = "🔥  Вскипятить" if target >= 100 else f"🔥  Нагреть до {target} °C"
            style = ""
        self.boil_btn.setText(text)
        self.boil_btn.setStyleSheet(style)

    @staticmethod
    def _ct_text(v):
        if v <= 3300:
            return f"{v} K · тёплый"
        if v >= 5300:
            return f"{v} K · холодный"
        return f"{v} K · нейтральный"

    # ---------- изменения ----------

    def _set(self, key, value, save=True):
        self.s[key] = value
        if save:
            self.changed()

    def _set_key(self, index, checked):
        self.s["keys"][index] = checked
        self.changed()

    def changed(self):
        self.main.on_device_changed(self.device)
        self.refresh_live()

    def on_power_toggled(self, checked):
        self.main.set_device_on(self.device, checked)
        self.refresh_live()

    def toggle_lock(self):
        self.s["locked"] = not self.s.get("locked", True)
        self._update_lock_button()
        self.changed()

    def _update_lock_button(self):
        if self.s.get("locked", True):
            self.lock_btn.setText("🔒  Закрыт — нажмите, чтобы открыть")
            self.lock_btn.setStyleSheet("")
        else:
            self.lock_btn.setText("🔓  Открыт — нажмите, чтобы закрыть")
            self.lock_btn.setStyleSheet("background-color: #f5a623;")

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.s.get("color") or "#ffffff"), self, "Цвет подсветки")
        if color.isValid():
            self._set("color", color.name())

    def on_timer_changed(self, index):
        minutes = self.timer_combo.itemData(index)
        if minutes:
            self.s["timer_min"] = minutes
            self.s["off_at"] = self.main.simulator.sim_minutes + minutes
            if not self.device["is_on"]:
                self.power_switch.setChecked(True)
        else:
            self.s.pop("timer_min", None)
            self.s.pop("off_at", None)
        self.changed()

    def run_scene(self, code):
        count = self.main.run_scene(code, self.device["room_id"])
        self.live_label.setText(f"✅ Сценарий выполнен, изменено устройств: {count}")

    def refresh_live(self):
        """Обновить строку с текущим состоянием (вызывается и из главного окна каждую секунду)."""
        if self.power_switch.isChecked() != bool(self.device["is_on"]):
            self.power_switch.set_state_silent(bool(self.device["is_on"]))
        if hasattr(self, "boil_btn"):
            self._refresh_kettle()
        if hasattr(self, "vac_main_btn"):
            self._refresh_vacuum()
        if hasattr(self, "wash_btn"):
            self._refresh_washer()
        if hasattr(self, "dial"):
            self.dial.update()
        if hasattr(self, "light_preview"):
            self.light_preview.update()
        power = device_power(self.device)
        reading = self.main.readings.get(self.device["id"])
        parts = []
        if not self.device["is_on"]:
            parts.append("<b>Выключено</b>")
        else:
            if reading:
                parts.append(f"<b>{reading}</b>")
            parts.append(f"Потребление сейчас: <b>≈{format_power(power)}</b>")
        self.live_label.setText("  ·  ".join(parts))

        if hasattr(self, "timer_hint"):
            if self.s.get("off_at") is not None:
                self.timer_hint.setText(f"Выключится в {sim_time_text(self.s['off_at'])} (по времени дома)")
            else:
                self.timer_hint.setText("Таймер не установлен")
                if self.timer_combo.currentData():
                    self.timer_combo.blockSignals(True)
                    self.timer_combo.setCurrentIndex(0)
                    self.timer_combo.blockSignals(False)

    def rename(self):
        name, ok = QInputDialog.getText(self, "Переименовать", "Новое название:", text=self.device["name"])
        if ok and name.strip():
            self.device["name"] = name.strip()[:40]
            self.main.db.rename_device(self.device["id"], self.device["name"])
            self.name_label.setText(self.device["name"])
            self.setWindowTitle(self.device["name"])
            self.main.refresh_grid()

    def delete(self):
        if self.main.delete_device(self.device):
            self.reject()


####################################
###### СТРАНИЦЫ ГЛАВНОГО ОКНА ######
####################################

def format_money(value):
    return f"{value:,.0f}".replace(",", " ") + " ₸"


EVENT_CATEGORIES = [("all", "Все"), ("energy", "⚡ Энергия"), ("device", "📱 Устройства"), ("security", "🛡 Безопасность")]


# ---------- всплывающие уведомления ----------

class Toast(QFrame):
    def __init__(self, icon, text, color, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setStyleSheet(
            f"QFrame#toast {{ background: #ffffff; border: 1px solid #dfe8ef; border-left: 5px solid {color};"
            f" border-radius: 12px; }}"
        )
        self.setFixedWidth(360)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 22px;")
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        layout.addWidget(icon_label, alignment=Qt.AlignTop)
        layout.addWidget(text_label, 1)
        self.effect = QGraphicsOpacityEffect(self)
        self.effect.setOpacity(0.0)
        self.setGraphicsEffect(self.effect)


class ToastManager(QObject):
    """Короткие уведомления в правом нижнем углу окна, исчезают сами через несколько секунд."""

    MAX_VISIBLE = 4

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.toasts = []

    def show(self, icon, text, color=ACCENT):
        toast = Toast(icon, text, color, self.host)
        toast.adjustSize()
        toast.show()
        toast.raise_()
        self.toasts.append(toast)
        while len(self.toasts) > self.MAX_VISIBLE:
            self._remove(self.toasts[0])
        self.relayout()
        anim = QPropertyAnimation(toast.effect, b"opacity", toast)
        anim.setDuration(250)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        QTimer.singleShot(5000, lambda: self._fade_out(toast))

    def _fade_out(self, toast):
        if toast not in self.toasts:
            return
        anim = QPropertyAnimation(toast.effect, b"opacity", toast)
        anim.setDuration(400)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(lambda: self._remove(toast))
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _remove(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
            toast.hide()
            toast.deleteLater()
            self.relayout()

    def relayout(self):
        y = self.host.height() - 24
        for toast in reversed(self.toasts):
            toast.adjustSize()
            y -= toast.height()
            toast.move(self.host.width() - toast.width() - 24, y)
            y -= 10


# ---------- план дома ----------

def plan_image_path(file_name):
    """Своя картинка рядом с программой имеет приоритет над встроенной в .exe."""
    local = os.path.join(APP_DIR, file_name)
    return local if os.path.exists(local) else os.path.join(RESOURCE_DIR, file_name)
PLAN_FLOORS = [("floor1", "1 этаж", "1floor.png"), ("floor2", "2 этаж", "2floor.png"), ("site", "Участок", "3Region.png")]
# где на планировке находятся комнаты (доли ширины/высоты картинки)
ROOM_ZONES = [
    (("гост", "зал"), "floor1", 0.59, 0.36),
    (("кух",), "floor1", 0.72, 0.68),
    (("прихож", "коридор", "холл", "вход"), "floor1", 0.55, 0.74),
    (("гараж",), "floor1", 0.27, 0.6),
    (("террас", "терас", "балкон"), "floor1", 0.76, 0.15),
    (("спальн", "детск", "кабинет"), "floor2", 0.59, 0.36),
    (("двор", "сад", "участ", "улиц"), "site", 0.5, 0.85),
    (("ванн", "санузел", "туалет"), "floor1", 0.47, 0.6),
]
FLOOR_DEFAULT_POS = {"floor1": (0.45, 0.45), "floor2": (0.5, 0.45), "site": (0.5, 0.8)}


def room_zone(room_name):
    name = room_name.lower()
    for keys, floor, x, y in ROOM_ZONES:
        if any(k in name for k in keys):
            return floor, x, y
    return "floor1", 0.45, 0.45


def room_plan_position(room_id, room_name, floor):
    """Где на плане этажа стоят устройства комнаты (своя зона по названию или место по умолчанию)."""
    name = room_name.lower()
    for keys, zone_floor, x, y in ROOM_ZONES:
        if zone_floor == floor and any(k in name for k in keys):
            return x, y
    x, y = FLOOR_DEFAULT_POS.get(floor, (0.5, 0.5))
    return x + ((room_id * 37) % 5 - 2) * 0.07, y + ((room_id * 17) % 3 - 1) * 0.08


def plan_glow_color(device):
    """Цвет свечения значка на плане (None - устройство неактивно)."""
    t = device["type_code"]
    s = device["settings"]
    if t == "robot_vacuum":
        return QColor(ACCENT) if s.get("vac_state") in ("cleaning", "returning") else None
    if not device["is_on"]:
        return None
    if DEVICE_TYPES[t]["group"] == LIGHT_GROUP:
        return light_color(device)
    if t == "air_conditioner":
        return QColor("#ff7a45") if s.get("mode") == "Обогрев" else QColor("#3d9df5")
    if t in ("heater", "water_heater") or (t == "kettle" and kettle_is_heating(device)):
        return QColor("#ff6b3d")
    if t == "camera":
        return QColor("#e5484d")
    return QColor(ACCENT)


class FloorPlanView(QWidget):
    """
    Планировка с устройствами. Включённые устройства светятся (лампы - своим цветом),
    значки можно перетаскивать мышью, клик открывает управление, ПКМ - меню.
    """

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.floor = "floor1"
        self.highlight_room = None
        self.pixmaps = {}
        self.phase = 0.0
        self.hovered = None
        self._press = None
        self._dragging = False
        self.setMouseTracking(True)
        self.setMinimumHeight(420)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(60)

    def _tick(self):
        if self.isVisible():
            self.phase += 0.15
            self.update()

    def pixmap(self):
        if self.floor not in self.pixmaps:
            file_name = dict((code, f) for code, _, f in PLAN_FLOORS)[self.floor]
            self.pixmaps[self.floor] = QPixmap(plan_image_path(file_name))
        return self.pixmaps[self.floor]

    def image_rect(self):
        pix = self.pixmap()
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        if pix.isNull():
            return area
        scale = min(area.width() / pix.width(), area.height() / pix.height())
        w, h = pix.width() * scale, pix.height() * scale
        return QRectF(area.center().x() - w / 2, area.center().y() - h / 2, w, h)

    def device_positions(self):
        """[(устройство, QPointF)] для устройств текущего этажа."""
        img = self.image_rect()
        counters = {}
        result = []
        for d in self.main.devices:
            plan = d["settings"].get("plan")
            index = counters.get(d["room_id"], 0)
            counters[d["room_id"]] = index + 1
            if plan:
                floor, x, y = plan["floor"], plan["x"], plan["y"]
            else:
                floor = self.main.room_floor(d["room_id"])
                x, y = room_plan_position(d["room_id"], d["room_name"], floor)
                x += ((index % 4) - 1.5) * 0.045
                y += (index // 4) * 0.06 - 0.03
            if floor == self.floor:
                result.append((d, QPointF(img.left() + x * img.width(), img.top() + y * img.height())))
        return result

    def device_at(self, pos):
        for d, pt in reversed(self.device_positions()):
            if math.hypot(pt.x() - pos.x(), pt.y() - pos.y()) <= 20:
                return d
        return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 16, 16)
        pix = self.pixmap()
        img = self.image_rect()
        if pix.isNull():
            p.setPen(QColor("#8aa0b2"))
            p.drawText(img, Qt.AlignCenter, "Файл планировки не найден рядом с home.py")
        else:
            p.drawPixmap(img, pix, QRectF(pix.rect()))

        font = QFont(self.font())
        for d, pt in self.device_positions():
            dim = self.highlight_room is not None and d["room_id"] != self.highlight_room
            p.setOpacity(0.28 if dim else 1.0)
            glow = plan_glow_color(d)
            if glow is not None:
                pulse = 34 + 5 * math.sin(self.phase + d["id"])
                g = QRadialGradient(pt, pulse)
                g.setColorAt(0, _color(glow.name(), 200))
                g.setColorAt(1, _color(glow.name(), 0))
                p.setPen(Qt.NoPen)
                p.setBrush(g)
                p.drawEllipse(pt, pulse, pulse)
            p.setBrush(QColor("#ffffff"))
            p.setPen(QPen(glow if glow is not None else QColor("#b9c7d2"), 3))
            p.drawEllipse(pt, 18, 18)
            font.setPixelSize(17)
            p.setFont(font)
            p.setPen(QColor("#12293c"))
            p.drawText(QRectF(pt.x() - 18, pt.y() - 18, 36, 36), Qt.AlignCenter, DEVICE_TYPES[d["type_code"]]["icon"])
            if self.hovered is d and not self._dragging:
                font.setPixelSize(12)
                font.setBold(True)
                p.setFont(font)
                text = f"{d['name']} · {QTextDocumentFragment.fromHtml(device_status_html(d, self.main.readings.get(d['id']))).toPlainText()}"
                w = QFontMetrics(font).horizontalAdvance(text) + 20
                bubble = QRectF(pt.x() - w / 2, pt.y() + 24, w, 24)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(18, 41, 60, 225))
                p.drawRoundedRect(bubble, 8, 8)
                p.setPen(Qt.white)
                p.drawText(bubble, Qt.AlignCenter, text)
                font.setBold(False)
        p.setOpacity(1.0)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = (self.device_at(e.pos()), e.pos())
            self._dragging = False

    def mouseMoveEvent(self, e):
        if self._press and self._press[0] is not None and e.buttons() & Qt.LeftButton:
            if not self._dragging and (e.pos() - self._press[1]).manhattanLength() > 6:
                self._dragging = True
            if self._dragging:
                img = self.image_rect()
                x = min(0.99, max(0.01, (e.pos().x() - img.left()) / img.width()))
                y = min(0.99, max(0.01, (e.pos().y() - img.top()) / img.height()))
                self._press[0]["settings"]["plan"] = {"floor": self.floor, "x": x, "y": y}
                self.update()
            return
        device = self.device_at(e.pos())
        if device is not self.hovered:
            self.hovered = device
            self.setCursor(Qt.PointingHandCursor if device else Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, e):
        if not self._press:
            return
        device, _ = self._press
        self._press = None
        if device is None:
            return
        if self._dragging:
            self._dragging = False
            self.main.db.save_settings(device["id"], device["settings"])
        else:
            self.main.open_device(device["id"])

    def contextMenuEvent(self, e):
        device = self.device_at(e.pos())
        if device is not None:
            self.main.show_device_menu(device["id"], e.globalPos())

    def leaveEvent(self, e):
        self.hovered = None
        self.update()


class FloorPlanPage(QWidget):
    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.floor_group = QButtonGroup(self)
        self.floor_buttons = {}
        for code, caption, _ in PLAN_FLOORS:
            btn = QPushButton(caption)
            btn.setObjectName("chip")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self.set_floor(c))
            self.floor_group.addButton(btn)
            self.floor_buttons[code] = btn
            row.addWidget(btn)
        row.addStretch()
        legend = QLabel("Светится — включено  ·  перетащите значок, чтобы переставить  ·  клик — управление")
        legend.setStyleSheet("font-size: 12px; color: #8aa0b2;")
        row.addWidget(legend)
        layout.addLayout(row)
        self.view = FloorPlanView(main)
        layout.addWidget(self.view, 1)
        self.set_floor("floor1")

    def set_floor(self, code):
        self.view.floor = code
        self.floor_buttons[code].setChecked(True)
        self.view.update()

    def set_room(self, room_id, floor=None):
        self.view.highlight_room = room_id
        if floor:
            self.set_floor(floor)
        self.view.update()


# ---------- энергия ----------

class StatTile(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(2)
        caption = QLabel(title)
        caption.setObjectName("subtitle")
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 22px; font-weight: 800; color: #12293c;")
        self.sub = QLabel()
        self.sub.setStyleSheet("font-size: 12px; color: #8aa0b2;")
        layout.addWidget(caption)
        layout.addWidget(self.value)
        layout.addWidget(self.sub)

    def set(self, value, sub="", color="#12293c"):
        self.value.setText(value)
        self.value.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
        self.sub.setText(sub)


class EnergyChart(QWidget):
    """Суточный график: выработка панелей (жёлтая область), потребление дома, заряд АКБ, прогноз ясного неба."""

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.hover_x = None
        self.setMouseTracking(True)
        self.setMinimumHeight(290)

    def plot_rect(self):
        return QRectF(56, 40, self.width() - 56 - 52, self.height() - 40 - 34)

    def mouseMoveEvent(self, e):
        self.hover_x = e.pos().x() if self.plot_rect().contains(QPointF(e.pos())) else None
        self.update()

    def leaveEvent(self, e):
        self.hover_x = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.plot_rect()
        history = self.main.energy_history
        max_kw = max([SOLAR_PEAK_W / 1000] + [h[2] / 1000 for h in history]) * 1.1
        max_kw = math.ceil(max_kw)

        def px(minute):
            return r.left() + minute / 1440 * r.width()

        def py_kw(watts):
            return r.bottom() - watts / 1000 / max_kw * r.height()

        def py_level(level):
            return r.bottom() - level * r.height()

        font = QFont(self.font())
        font.setPixelSize(11)
        p.setFont(font)

        # ночь
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#eef2f8"))
        p.drawRect(QRectF(px(0), r.top(), px(6 * 60) - px(0), r.height()))
        p.drawRect(QRectF(px(20 * 60), r.top(), px(1440) - px(20 * 60), r.height()))

        # сетка и подписи
        for i in range(5):
            y = r.bottom() - i * r.height() / 4
            p.setPen(QPen(QColor("#e3edf4"), 1))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor("#8aa0b2"))
            p.drawText(QRectF(0, y - 8, r.left() - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{max_kw * i / 4:.1f} кВт")
            p.drawText(QRectF(r.right() + 6, y - 8, 46, 16), Qt.AlignLeft | Qt.AlignVCenter, f"{i * 25}%")
        for hour in range(0, 25, 3):
            x = px(hour * 60)
            p.drawText(QRectF(x - 20, r.bottom() + 6, 40, 16), Qt.AlignCenter, f"{hour:02d}:00")

        # прогноз выработки при ясном небе
        forecast = QPainterPath()
        for minute in range(0, 1441, 10):
            hour = minute / 60
            w = SOLAR_PEAK_W * math.sin(math.pi * (hour - 6) / 14) if 6 < hour < 20 else 0
            pt = QPointF(px(minute), py_kw(w))
            forecast.moveTo(pt) if minute == 0 else forecast.lineTo(pt)
        p.setPen(QPen(QColor("#e6b422"), 1.5, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawPath(forecast)

        if len(history) >= 2:
            area = QPainterPath(QPointF(px(history[0][0]), r.bottom()))
            for minute, gen, load, level, *_ in history:
                area.lineTo(px(minute), py_kw(gen))
            area.lineTo(px(history[-1][0]), r.bottom())
            area.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(245, 179, 1, 90))
            p.drawPath(area)
            for index, color, width, fy in ((1, "#f5b301", 2, py_kw), (2, "#2f8de4", 2, py_kw), (3, ACCENT, 2.5, py_level)):
                line = QPainterPath(QPointF(px(history[0][0]), fy(history[0][index])))
                for h in history[1:]:
                    line.lineTo(px(h[0]), fy(h[index]))
                p.setPen(QPen(QColor(color), width))
                p.setBrush(Qt.NoBrush)
                p.drawPath(line)
        else:
            p.setPen(QColor("#8aa0b2"))
            p.drawText(r, Qt.AlignCenter, "График заполняется по ходу симуляции…")

        # «сейчас»
        state = self.main.simulator.state
        if state:
            now_x = px(state["sim_minutes"] % 1440)
            p.setPen(QPen(QColor("#12293c"), 1, Qt.DashLine))
            p.drawLine(QPointF(now_x, r.top()), QPointF(now_x, r.bottom()))
            p.drawText(QRectF(now_x - 30, r.top() - 18, 60, 14), Qt.AlignCenter, "сейчас")

        # легенда
        x = r.left()
        for color, caption, dashed in (("#f5b301", "Выработка панелей", False), ("#2f8de4", "Потребление дома", False),
                                       (ACCENT, "Заряд АКБ (правая шкала)", False), ("#e6b422", "Прогноз (ясно)", True)):
            p.setPen(QPen(QColor(color), 3, Qt.DashLine if dashed else Qt.SolidLine))
            p.drawLine(QPointF(x, 14), QPointF(x + 20, 14))
            p.setPen(QColor("#3f5e75"))
            p.drawText(QRectF(x + 26, 6, 200, 16), Qt.AlignLeft | Qt.AlignVCenter, caption)
            x += 46 + QFontMetrics(font).horizontalAdvance(caption)

        # подсказка при наведении
        if self.hover_x is not None and history:
            minute = (self.hover_x - r.left()) / r.width() * 1440
            nearest = min(history, key=lambda h: abs(h[0] - minute))
            if abs(nearest[0] - minute) < 30:
                hx = px(nearest[0])
                p.setPen(QPen(QColor("#9fb3c3"), 1))
                p.drawLine(QPointF(hx, r.top()), QPointF(hx, r.bottom()))
                lines = [sim_time_text(nearest[0]), f"☀️ {format_power(nearest[1])}", f"🏠 {format_power(nearest[2])}",
                         f"🔋 {nearest[3] * 100:.0f}%"]
                if nearest[4] > 1:
                    lines.append(f"🔌 из сети {format_power(nearest[4])}")
                box = QRectF(min(hx + 10, r.right() - 150), r.top() + 8, 140, 18 * len(lines) + 10)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(18, 41, 60, 230))
                p.drawRoundedRect(box, 8, 8)
                p.setPen(Qt.white)
                for i, line in enumerate(lines):
                    p.drawText(QRectF(box.left() + 10, box.top() + 5 + i * 18, box.width() - 20, 18),
                               Qt.AlignLeft | Qt.AlignVCenter, line)


class EnergyLivePage(QScrollArea):
    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(14)
        self.setWidget(host)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_generated = StatTile("☀️ Выработано сегодня")
        self.tile_saved = StatTile("💰 Сэкономлено сегодня")
        self.tile_bought = StatTile("🔌 Куплено из сети")
        self.tile_co2 = StatTile("🌱 CO₂ не выброшено")
        for tile in (self.tile_generated, self.tile_saved, self.tile_bought, self.tile_co2):
            tiles.addWidget(tile)
        layout.addLayout(tiles)

        chart_card = QFrame()
        chart_card.setObjectName("card")
        chart_layout = QVBoxLayout(chart_card)
        chart_layout.setContentsMargins(18, 14, 18, 10)
        title = QLabel("📊 Энергия за сутки")
        title.setObjectName("sectionTitle")
        chart_layout.addWidget(title)
        self.chart = EnergyChart(main)
        chart_layout.addWidget(self.chart)
        layout.addWidget(chart_card)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        # эко-режим
        eco = QFrame()
        eco.setObjectName("card")
        eco_layout = QVBoxLayout(eco)
        eco_layout.setContentsMargins(18, 14, 18, 14)
        head = QHBoxLayout()
        eco_title = QLabel("🌿 Эко-режим")
        eco_title.setObjectName("sectionTitle")
        self.eco_switch = ToggleSwitch()
        self.eco_switch.set_state_silent(main.eco_mode)
        self.eco_switch.toggled.connect(main.set_eco_mode)
        head.addWidget(eco_title)
        head.addStretch()
        head.addWidget(self.eco_switch)
        eco_layout.addLayout(head)
        names = ", ".join(DEVICE_TYPES[t]["name"].lower() for t in ECO_SHED_TYPES)
        eco_desc = QLabel(f"При заряде АКБ ниже {ECO_OFF_LEVEL * 100:.0f}% автоматически отключаются второстепенные "
                          f"мощные устройства и включаются обратно при {ECO_RESTORE_LEVEL * 100:.0f}%.\n"
                          f"Отключаются: {names}.\nОхрана, датчики и холодильник продолжают работать.")
        eco_desc.setWordWrap(True)
        eco_desc.setObjectName("subtitle")
        eco_layout.addWidget(eco_desc)
        self.eco_status = QLabel()
        self.eco_status.setWordWrap(True)
        self.eco_status.setStyleSheet("font-weight: 600;")
        eco_layout.addWidget(self.eco_status)
        eco_layout.addStretch()
        bottom.addWidget(eco, 1)

        # излишки солнца
        solar = QFrame()
        solar.setObjectName("card")
        solar_layout = QVBoxLayout(solar)
        solar_layout.setContentsMargins(18, 14, 18, 14)
        solar_title = QLabel("☀️ Излишки солнца")
        solar_title.setObjectName("sectionTitle")
        solar_layout.addWidget(solar_title)
        solar_desc = QLabel(f"Зарядка авто и бойлер с режимом «Только от излишков солнца» работают, лишь когда "
                            f"панели дают больше, чем потребляет дом, а АКБ заряжена от "
                            f"{SOLAR_ONLY_MIN_LEVEL * 100:.0f}%. Режим включается в окне устройства.")
        solar_desc.setWordWrap(True)
        solar_desc.setObjectName("subtitle")
        solar_layout.addWidget(solar_desc)
        self.surplus_label = QLabel()
        self.surplus_label.setStyleSheet("font-weight: 600;")
        solar_layout.addWidget(self.surplus_label)
        self.solar_devices_label = QLabel()
        self.solar_devices_label.setWordWrap(True)
        self.solar_devices_label.setTextFormat(Qt.RichText)
        solar_layout.addWidget(self.solar_devices_label)
        solar_layout.addStretch()
        bottom.addWidget(solar, 1)

        # итоги и тариф
        totals = QFrame()
        totals.setObjectName("card")
        totals_layout = QVBoxLayout(totals)
        totals_layout.setContentsMargins(18, 14, 18, 14)
        totals_title = QLabel("💰 За всё время")
        totals_title.setObjectName("sectionTitle")
        totals_layout.addWidget(totals_title)
        tariff_row = QHBoxLayout()
        tariff_caption = QLabel("Тариф")
        tariff_caption.setObjectName("subtitle")
        self.tariff_spin = QDoubleSpinBox()
        self.tariff_spin.setRange(1, 500)
        self.tariff_spin.setDecimals(2)
        self.tariff_spin.setSuffix(" ₸/кВт·ч")
        self.tariff_spin.setValue(main.tariff)
        self.tariff_spin.valueChanged.connect(main.set_tariff)
        tariff_row.addWidget(tariff_caption)
        tariff_row.addStretch()
        tariff_row.addWidget(self.tariff_spin)
        totals_layout.addLayout(tariff_row)
        self.row_total_gen = StatRow("☀️ Выработано")
        self.row_total_saved = StatRow("💰 Сэкономлено")
        self.row_total_bought = StatRow("🔌 Оплачено за сеть")
        self.row_total_co2 = StatRow("🌱 CO₂ не выброшено")
        self.row_trees = StatRow("🌳 Как деревьев за год")
        for row in (self.row_total_gen, self.row_total_saved, self.row_total_bought, self.row_total_co2, self.row_trees):
            totals_layout.addWidget(row)
        totals_layout.addStretch()
        bottom.addWidget(totals, 1)
        layout.addLayout(bottom)
        layout.addStretch()

    def update_state(self, state):
        tariff = self.main.tariff
        generated = state["generated_today"] / 1000
        used = max(0.0, state["generated_today"] - state["export_today"]) / 1000
        bought = state["import_today"] / 1000
        self.tile_generated.set(f"{generated:.2f} кВт·ч", f"в дом / в АКБ: {used:.2f} кВт·ч", "#c98a00")
        self.tile_saved.set(format_money(used * tariff), f"по тарифу {tariff:g} ₸/кВт·ч", ACCENT)
        self.tile_bought.set(format_money(bought * tariff), f"{bought:.2f} кВт·ч из сети",
                             "#e5484d" if bought > 0.01 else "#12293c")
        self.tile_co2.set(f"{generated * CO2_KG_PER_KWH:.1f} кг", f"{CO2_KG_PER_KWH} кг CO₂ на кВт·ч сети РК")

        total_gen = state["total_generated"] / 1000
        total_used = max(0.0, state["total_generated"] - state["total_export"]) / 1000
        self.row_total_gen.set_value(f"{total_gen:.1f} кВт·ч")
        self.row_total_saved.set_value(format_money(total_used * tariff), ACCENT)
        self.row_total_bought.set_value(format_money(state["total_import"] / 1000 * tariff))
        co2 = total_gen * CO2_KG_PER_KWH
        self.row_total_co2.set_value(f"{co2:.1f} кг")
        self.row_trees.set_value(f"{co2 / CO2_PER_TREE_KG:.2f}")

        shed = [d["name"] for d in self.main.devices if d["settings"].get("eco_shed")]
        if not self.main.eco_mode:
            self.eco_status.setText("Эко-режим выключен")
            self.eco_status.setStyleSheet("font-weight: 600; color: #8aa0b2;")
        elif shed:
            self.eco_status.setText("⚠️ Сейчас отключены: " + ", ".join(shed))
            self.eco_status.setStyleSheet("font-weight: 600; color: #e08a00;")
        else:
            self.eco_status.setText(f"✅ Активен · АКБ {state['level'] * 100:.0f}%")
            self.eco_status.setStyleSheet(f"font-weight: 600; color: {ACCENT};")

        surplus = state["generation"] - state["load"]
        self.surplus_label.setText(f"Сейчас излишек: {format_power(max(0, surplus))}" if surplus > 0
                                   else "Сейчас излишков нет")
        solar_devices = [d for d in self.main.devices if d["settings"].get("solar_only")]
        if solar_devices:
            rows = []
            for d in solar_devices:
                power = d.get("_solar_power", 0.0)
                if not d["is_on"]:
                    status = "<span style='color:#8aa0b2'>выключено</span>"
                elif power > 1:
                    status = f"<span style='color:{ACCENT}'>работает · {format_power(power)}</span>"
                else:
                    status = "<span style='color:#e08a00'>ждёт излишков</span>"
                rows.append(f"{DEVICE_TYPES[d['type_code']]['icon']} {d['name']} — {status}")
            self.solar_devices_label.setText("<br>".join(rows))
        else:
            self.solar_devices_label.setText("<span style='color:#8aa0b2'>Нет устройств с этим режимом</span>")
        self.chart.update()


# ---------- отчёты за период ----------

MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS_FULL = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь",
               "ноябрь", "декабрь"]
REPORT_PERIODS = [("today", "Сегодня"), ("week", "Неделя"), ("month", "Месяц"), ("year", "Год"), ("custom", "Свой период")]


def kwh_text(wh, digits=1):
    return f"{wh / 1000:,.{digits}f}".replace(",", " ").replace(".", ",") + " кВт·ч"


class ReportChart(QWidget):
    """Столбики потребления по дням/месяцам: часть от солнца (зелёная) и часть из сети (красная) + линия выработки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.buckets = []
        self.hover = None
        self.setMouseTracking(True)
        self.setMinimumHeight(280)

    def set_data(self, buckets):
        self.buckets = buckets
        self.update()

    def plot_rect(self):
        return QRectF(64, 44, self.width() - 64 - 20, self.height() - 44 - 34)

    def mouseMoveEvent(self, e):
        r = self.plot_rect()
        if self.buckets and r.contains(QPointF(e.pos())):
            self.hover = min(len(self.buckets) - 1, int((e.pos().x() - r.left()) / (r.width() / len(self.buckets))))
        else:
            self.hover = None
        self.update()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.plot_rect()
        font = QFont(self.font())
        font.setPixelSize(11)
        p.setFont(font)
        # легенда
        x = r.left()
        for color, caption, line in ((QColor(ACCENT), "Потребление от солнца и АКБ", False),
                                     (QColor("#e5484d"), "Потребление из сети (платно)", False),
                                     (QColor("#f5b301"), "Выработка панелей", True)):
            if line:
                p.setPen(QPen(color, 3))
                p.drawLine(QPointF(x, 14), QPointF(x + 18, 14))
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(QRectF(x, 8, 14, 12), 3, 3)
            p.setPen(QColor("#3f5e75"))
            p.drawText(QRectF(x + 22, 6, 260, 16), Qt.AlignLeft | Qt.AlignVCenter, caption)
            x += 40 + QFontMetrics(font).horizontalAdvance(caption)
        if not self.buckets:
            p.setPen(QColor("#8aa0b2"))
            p.drawText(r, Qt.AlignCenter, "Нет данных за выбранный период")
            return
        top = max(max(b["cons"], b["gen"]) for b in self.buckets) * 1.12 or 1000
        unit, div = ("кВт·ч", 1000)

        def y(wh):
            return r.bottom() - wh / top * r.height()

        for i in range(5):
            v = top * i / 4
            yy = y(v)
            p.setPen(QPen(QColor("#e3edf4"), 1))
            p.drawLine(QPointF(r.left(), yy), QPointF(r.right(), yy))
            p.setPen(QColor("#8aa0b2"))
            p.drawText(QRectF(0, yy - 8, r.left() - 8, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"{v / div:.0f} {unit}" if top / div >= 8 else f"{v / div:.1f} {unit}")
        n = len(self.buckets)
        slot = r.width() / n
        bw = max(2.0, min(34.0, slot * 0.68))
        label_every = max(1, math.ceil(n / max(1, r.width() / 52)))
        gen_points = []
        for i, b in enumerate(self.buckets):
            cx = r.left() + slot * (i + 0.5)
            grid = min(b["imp"], b["cons"])
            solar = max(0.0, b["cons"] - grid)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 185, 107, 200 if self.hover in (None, i) else 120))
            p.drawRect(QRectF(cx - bw / 2, y(solar), bw, r.bottom() - y(solar)))
            p.setBrush(QColor(229, 72, 77, 220 if self.hover in (None, i) else 130))
            p.drawRect(QRectF(cx - bw / 2, y(solar + grid), bw, y(solar) - y(solar + grid)))
            gen_points.append(QPointF(cx, y(b["gen"])))
            if i % label_every == 0:
                p.setPen(QColor("#8aa0b2"))
                p.drawText(QRectF(cx - 30, r.bottom() + 6, 60, 16), Qt.AlignCenter, b["label"])
        p.setPen(QPen(QColor("#f5b301"), 2.5))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(gen_points[0])
        for pt in gen_points[1:]:
            path.lineTo(pt)
        p.drawPath(path)
        p.setBrush(QColor("#f5b301"))
        p.setPen(Qt.NoPen)
        if n <= 40:
            for pt in gen_points:
                p.drawEllipse(pt, 3, 3)
        if self.hover is not None:
            b = self.buckets[self.hover]
            lines = [b["title"], f"☀️ Выработка: {kwh_text(b['gen'])}", f"🏠 Потребление: {kwh_text(b['cons'])}",
                     f"🔌 Из сети: {kwh_text(b['imp'])}", f"💰 К оплате: {format_money(b['cost'])}"]
            cx = r.left() + slot * (self.hover + 0.5)
            box = QRectF(min(cx + 12, r.right() - 210), r.top() + 6, 200, 18 * len(lines) + 12)
            p.setBrush(QColor(18, 41, 60, 235))
            p.drawRoundedRect(box, 8, 8)
            p.setPen(Qt.white)
            for k, line in enumerate(lines):
                p.drawText(QRectF(box.left() + 10, box.top() + 6 + k * 18, box.width() - 20, 18),
                           Qt.AlignLeft | Qt.AlignVCenter, line)


class ReportsPage(QScrollArea):
    """Отчёты за период: солнце и сеть отдельно, счёт за электроэнергию, прогноз оплаты, таблица, CSV."""

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.period = "week"
        self.rows = []
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(14)
        self.setWidget(host)

        # выбор периода
        row = QHBoxLayout()
        row.setSpacing(8)
        self.period_group = QButtonGroup(self)
        for code, caption in REPORT_PERIODS:
            btn = QPushButton(caption)
            btn.setObjectName("chip")
            btn.setCheckable(True)
            btn.setChecked(code == self.period)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self.set_period(c))
            self.period_group.addButton(btn)
            row.addWidget(btn)
        row.addSpacing(8)
        self.date_from = QDateEdit()
        self.date_to = QDateEdit()
        for edit in (self.date_from, self.date_to):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd.MM.yyyy")
            edit.dateChanged.connect(lambda *_: self.period == "custom" and self.refresh())
        self.dash = QLabel("—")
        row.addWidget(self.date_from)
        row.addWidget(self.dash)
        row.addWidget(self.date_to)
        row.addStretch()
        export = QPushButton("⬇ Экспорт CSV")
        export.setObjectName("secondary")
        export.setCursor(Qt.PointingHandCursor)
        export.clicked.connect(self.export_csv)
        row.addWidget(export)
        layout.addLayout(row)
        self.period_label = QLabel()
        self.period_label.setObjectName("subtitle")
        self.period_label.setWordWrap(True)
        layout.addWidget(self.period_label)

        # прогноз оплаты
        forecast = QFrame()
        forecast.setObjectName("card")
        f_layout = QVBoxLayout(forecast)
        f_layout.setContentsMargins(18, 14, 18, 14)
        f_title = QLabel("🧾 Прогноз оплаты за электроэнергию")
        f_title.setObjectName("sectionTitle")
        f_layout.addWidget(f_title)
        self.forecast_value = QLabel()
        self.forecast_value.setStyleSheet("font-size: 26px; font-weight: 800; color: #12293c;")
        self.forecast_value.setWordWrap(True)
        f_layout.addWidget(self.forecast_value)
        self.forecast_text = QLabel()
        self.forecast_text.setObjectName("subtitle")
        self.forecast_text.setWordWrap(True)
        self.forecast_text.setTextFormat(Qt.RichText)
        f_layout.addWidget(self.forecast_text)
        self.forecast_live = QLabel()
        self.forecast_live.setWordWrap(True)
        self.forecast_live.setStyleSheet("font-size: 13px; color: #3f5e75;")
        f_layout.addWidget(self.forecast_live)
        layout.addWidget(forecast)

        # итоги периода
        tiles = QGridLayout()
        tiles.setSpacing(12)
        self.t_pay = StatTile("💳 К оплате за сеть")
        self.t_grid = StatTile("🔌 Взято из сети")
        self.t_saved = StatTile("💰 Сэкономлено солнцем")
        self.t_gen = StatTile("☀️ Выработали панели")
        self.t_cons = StatTile("🏠 Потребил дом")
        for i, tile in enumerate((self.t_pay, self.t_grid, self.t_saved, self.t_gen, self.t_cons)):
            tile.sub.setWordWrap(True)
            tiles.addWidget(tile, i // 3, i % 3)
        for col in range(3):
            tiles.setColumnStretch(col, 1)
        layout.addLayout(tiles)

        chart_card = QFrame()
        chart_card.setObjectName("card")
        c_layout = QVBoxLayout(chart_card)
        c_layout.setContentsMargins(18, 14, 18, 10)
        self.chart_title = QLabel()
        self.chart_title.setObjectName("sectionTitle")
        c_layout.addWidget(self.chart_title)
        self.chart = ReportChart()
        c_layout.addWidget(self.chart)
        layout.addWidget(chart_card)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        bill = QFrame()
        bill.setObjectName("card")
        b_layout = QVBoxLayout(bill)
        b_layout.setContentsMargins(18, 14, 18, 14)
        b_title = QLabel("💳 Счёт за период")
        b_title.setObjectName("sectionTitle")
        b_layout.addWidget(b_title)
        self.bill_rows = {}
        for key, caption in (("grid", "🔌 Из сети"), ("tariff", "× Тариф"), ("pay", "= К оплате"),
                             ("nosolar", "Без панелей заплатили бы"), ("saved", "💰 Экономия"),
                             ("self", "☀️ Самообеспеченность"), ("export", "↗ Отдано в сеть"), ("co2", "🌱 CO₂ не выброшено")):
            row_w = StatRow(caption)
            self.bill_rows[key] = row_w
            b_layout.addWidget(row_w)
        b_layout.addStretch()
        bottom.addWidget(bill, 2)

        table_card = QFrame()
        table_card.setObjectName("card")
        t_layout = QVBoxLayout(table_card)
        t_layout.setContentsMargins(18, 14, 18, 14)
        t_title = QLabel("📋 Детализация")
        t_title.setObjectName("sectionTitle")
        t_layout.addWidget(t_title)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Период", "Выработка, кВт·ч", "Потребление, кВт·ч", "Из сети, кВт·ч",
                                              "В сеть, кВт·ч", "К оплате, ₸"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(300)
        self.table.setStyleSheet("QTableWidget { background: white; border: none; gridline-color: #eef2f5; }"
                                 "QHeaderView::section { background: #eef4f9; border: none; padding: 6px; font-weight: 600; }")
        t_layout.addWidget(self.table)
        bottom.addWidget(table_card, 3)
        layout.addLayout(bottom)
        layout.addStretch()

        today = self.main.simulator.sim_date()
        self.date_to.setDate(QDate(today.year, today.month, today.day))
        start = today - timedelta(days=13)
        self.date_from.setDate(QDate(start.year, start.month, start.day))
        self.set_period(self.period)

    # ---------- данные ----------

    def period_range(self):
        today = self.main.simulator.sim_date()
        if self.period == "today":
            return today, today
        if self.period == "week":
            return today - timedelta(days=6), today
        if self.period == "month":
            return today - timedelta(days=29), today
        if self.period == "year":
            return today - timedelta(days=364), today
        a, b = self.date_from.date().toPyDate(), self.date_to.date().toPyDate()
        return (a, b) if a <= b else (b, a)

    def set_period(self, code):
        self.period = code
        for btn, (c, _) in zip(self.period_group.buttons(), REPORT_PERIODS):
            btn.setChecked(c == code)
        custom = code == "custom"
        for w in (self.date_from, self.dash, self.date_to):
            w.setVisible(custom)
        self.refresh()

    def buckets(self, start, end):
        tariff = self.main.tariff
        days = self.main.energy_days(start, end)
        if start == end and start == self.main.simulator.sim_date():
            # сегодня - по часам из живой симуляции
            hours = {}
            for minute, gen, load, level, imp, *rest in self.main.energy_history:
                hours.setdefault(int(minute // 60), []).append((gen, load, imp, rest[0] if rest else 0.0))
            result = []
            for hour in range(24):
                samples = hours.get(hour)
                if not samples:
                    continue
                avg = [sum(x[k] for x in samples) / len(samples) for k in range(4)]
                result.append({"label": f"{hour:02d}:00", "title": f"{hour:02d}:00–{hour + 1:02d}:00", "gen": avg[0],
                               "cons": avg[1], "imp": avg[2], "exp": avg[3], "cost": avg[2] / 1000 * tariff})
            return result
        if (end - start).days <= 62:
            result = []
            d = start
            while d <= end:
                if d in days:
                    g, c, i, e = days[d]
                    result.append({"label": d.strftime("%d.%m"), "title": d.strftime("%d.%m.%Y"), "gen": g, "cons": c,
                                   "imp": i, "exp": e, "cost": i / 1000 * tariff})
                d += timedelta(days=1)
            return result
        months = {}
        for d, (g, c, i, e) in sorted(days.items()):
            key = (d.year, d.month)
            m = months.setdefault(key, [0.0, 0.0, 0.0, 0.0])
            for k, v in enumerate((g, c, i, e)):
                m[k] += v
        return [{"label": f"{MONTHS_SHORT[mo - 1]} {str(y)[2:]}", "title": f"{MONTHS_FULL[mo - 1].capitalize()} {y}",
                 "gen": v[0], "cons": v[1], "imp": v[2], "exp": v[3], "cost": v[2] / 1000 * tariff}
                for (y, mo), v in sorted(months.items())]

    def refresh(self):
        start, end = self.period_range()
        self.rows = self.buckets(start, end)
        tariff = self.main.tariff
        days = self.main.energy_days(start, end)
        gen = sum(v[0] for v in days.values())
        cons = sum(v[1] for v in days.values())
        imp = sum(v[2] for v in days.values())
        exp = sum(v[3] for v in days.values())
        n_days = (end - start).days + 1
        self.period_label.setText(
            f"Период: {start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')} ({n_days} "
            f"{plural(n_days, 'день', 'дня', 'дней')}) · сегодня по данным симуляции, прошлые дни — смоделированная история"
        )
        self.t_gen.set(kwh_text(gen), "энергия солнца", "#c98a00")
        self.t_cons.set(kwh_text(cons), f"в среднем {kwh_text(cons / n_days)} в день")
        self.t_grid.set(kwh_text(imp), f"{imp / cons * 100:.0f}% потребления" if cons else "", "#e5484d" if imp > 1 else "#12293c")
        self.t_pay.set(format_money(imp / 1000 * tariff), f"по тарифу {tariff:g} ₸/кВт·ч", "#e5484d" if imp > 1 else "#12293c")
        self.t_saved.set(format_money(max(0.0, cons - imp) / 1000 * tariff), "солнце + аккумулятор", ACCENT)

        self.bill_rows["grid"].set_value(kwh_text(imp, 2))
        self.bill_rows["tariff"].set_value(f"{tariff:g} ₸/кВт·ч")
        self.bill_rows["pay"].set_value(format_money(imp / 1000 * tariff), "#e5484d")
        self.bill_rows["nosolar"].set_value(format_money(cons / 1000 * tariff))
        saved = max(0.0, cons - imp) / 1000 * tariff
        self.bill_rows["saved"].set_value(f"{format_money(saved)} ({(cons - imp) / cons * 100:.0f}%)" if cons else "—", ACCENT)
        self.bill_rows["self"].set_value(f"{(cons - imp) / cons * 100:.0f}%" if cons else "—")
        self.bill_rows["export"].set_value(kwh_text(exp))
        self.bill_rows["co2"].set_value(f"{gen / 1000 * CO2_KG_PER_KWH:,.1f} кг".replace(",", " ").replace(".", ","))

        kind = "по часам" if self.period == "today" else ("по дням" if n_days <= 62 else "по месяцам")
        self.chart_title.setText(f"📊 Потребление и выработка {kind}")
        self.chart.set_data(self.rows)

        self.table.setRowCount(len(self.rows) + 1)
        for i, b in enumerate(self.rows + [{"title": "Итого", "gen": sum(b["gen"] for b in self.rows),
                                            "cons": sum(b["cons"] for b in self.rows), "imp": sum(b["imp"] for b in self.rows),
                                            "exp": sum(b["exp"] for b in self.rows),
                                            "cost": sum(b["cost"] for b in self.rows)}]):
            values = [b["title"], f"{b['gen'] / 1000:.2f}", f"{b['cons'] / 1000:.2f}", f"{b['imp'] / 1000:.2f}",
                      f"{b['exp'] / 1000:.2f}", format_money(b["cost"])]
            for col, v in enumerate(values):
                item = QTableWidgetItem(v.replace(".", ",") if col else v)
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if col == 0 else Qt.AlignRight))
                if i == len(self.rows):
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                if col == 3 and b["imp"] > 1:
                    item.setForeground(QColor("#c0392b"))
                self.table.setItem(i, col, item)
        self.refresh_forecast()

    def refresh_forecast(self):
        """Прогноз счёта за текущий месяц: уже взято из сети + средний расход из сети на оставшиеся дни."""
        import calendar
        tariff = self.main.tariff
        today = self.main.simulator.sim_date()
        month_start = today.replace(day=1)
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        mtd = self.main.energy_days(month_start, today)
        mtd_imp = sum(v[2] for v in mtd.values())
        mtd_cons = sum(v[1] for v in mtd.values())
        recent = self.main.energy_days(today - timedelta(days=14), today - timedelta(days=1))
        source = recent or mtd
        avg_imp = sum(v[2] for v in source.values()) / max(1, len(source))
        avg_cons = sum(v[1] for v in source.values()) / max(1, len(source))
        left = days_in_month - today.day
        forecast_imp = mtd_imp + avg_imp * left
        forecast_cons = mtd_cons + avg_cons * left
        month_name = MONTHS_FULL[today.month - 1]
        self.forecast_value.setText(f"≈ {format_money(forecast_imp / 1000 * tariff)} за {month_name}")
        self.forecast_text.setText(
            f"Уже взято из сети с 1 {MONTHS_SHORT[today.month - 1]}.: <b>{kwh_text(mtd_imp)}</b> "
            f"({format_money(mtd_imp / 1000 * tariff)}). Средний расход из сети за последние дни — "
            f"<b>{kwh_text(avg_imp)}</b> в сутки, до конца месяца {left} {plural(left, 'день', 'дня', 'дней')}. "
            f"Без солнечных панелей счёт был бы ≈ <b>{format_money(forecast_cons / 1000 * tariff)}</b>."
        )
        self.refresh_live_forecast()

    def refresh_live_forecast(self):
        st = self.main.simulator.state
        if not st:
            return
        tariff = self.main.tariff
        load = st["load"]
        grid_now = st["grid_import"]
        self.forecast_live.setText(
            f"⚡ Сейчас дом потребляет {format_power(load)}: сутки при такой нагрузке без солнца стоили бы "
            f"≈ {format_money(load * 24 / 1000 * tariff)}, месяц ≈ {format_money(load * 24 * 30 / 1000 * tariff)}. "
            + (f"Прямо сейчас из сети берётся {format_power(grid_now)} — это ≈ {format_money(grid_now / 1000 * tariff)} в час."
               if grid_now > 1 else "Сейчас дом не берёт энергию из сети — платить не нужно.")
        )

    def export_csv(self):
        start, end = self.period_range()
        folder = os.path.join(APP_DIR, "reports")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"energy_{start.isoformat()}_{end.isoformat()}.csv")
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write("Период;Выработка, кВт·ч;Потребление, кВт·ч;Из сети, кВт·ч;В сеть, кВт·ч;К оплате, тенге\n")
            for b in self.rows:
                f.write(";".join([b["title"]] + [f"{b[k] / 1000:.3f}".replace(".", ",") for k in ("gen", "cons", "imp", "exp")]
                                 + [f"{b['cost']:.0f}"]) + "\n")
        self.main.toasts.show("📄", f"Отчёт сохранён: {path}", ACCENT)


class EnergyPage(QWidget):
    """Вкладка «Энергия»: «Сейчас» (живые данные) и «Отчёты за период»."""

    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.group = QButtonGroup(self)
        for i, caption in enumerate(("⚡ Сейчас", "📑 Отчёты за период")):
            btn = QPushButton(caption)
            btn.setObjectName("chip")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, n=i: self.show_tab(n))
            self.group.addButton(btn, i)
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)
        self.stack = QStackedWidget()
        self.live = EnergyLivePage(main)
        self.reports = ReportsPage(main)
        self.stack.addWidget(self.live)
        self.stack.addWidget(self.reports)
        layout.addWidget(self.stack, 1)
        self._ticks = 0

    def show_tab(self, index):
        self.stack.setCurrentIndex(index)
        self.group.button(index).setChecked(True)
        if index == 1:
            self.reports.refresh()

    def update_state(self, state):
        if self.stack.currentIndex() == 0:
            self.live.update_state(state)
        else:
            self.reports.refresh_live_forecast()
            self._ticks += 1
            if self._ticks % 10 == 0 or state.get("closed_day"):
                self.reports.refresh()


# ---------- журнал событий ----------

class EventsPage(QWidget):
    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        self.filter = "all"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(8)
        group = QButtonGroup(self)
        for code, caption in EVENT_CATEGORIES:
            btn = QPushButton(caption)
            btn.setObjectName("chip")
            btn.setCheckable(True)
            btn.setChecked(code == "all")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, c=code: self.set_filter(c))
            group.addButton(btn)
            row.addWidget(btn)
        row.addStretch()
        clear_btn = QPushButton("Очистить журнал")
        clear_btn.setObjectName("danger")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(main.clear_events)
        row.addWidget(clear_btn)
        layout.addLayout(row)
        self.list = QListWidget()
        self.list.setObjectName("eventsList")
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(self.list, 1)
        self.reload()

    def set_filter(self, code):
        self.filter = code
        self.reload()

    def _item(self, event):
        item = QListWidgetItem(f"{event['sim_time']}     {event['icon']}   {event['text']}")
        colors = {"energy": "#8a6200", "security": "#c0392b", "device": "#14364f"}
        item.setForeground(QColor(colors.get(event["category"], "#14364f")))
        return item

    def add_event(self, event):
        if self.filter in ("all", event["category"]):
            self.list.insertItem(0, self._item(event))
            while self.list.count() > 300:
                self.list.takeItem(self.list.count() - 1)

    def reload(self):
        self.list.clear()
        for event in reversed(self.main.events):
            if self.filter in ("all", event["category"]):
                self.list.addItem(self._item(event))
        if self.list.count() == 0:
            item = QListWidgetItem("Событий пока нет")
            item.setForeground(QColor("#8aa0b2"))
            self.list.addItem(item)


####################################
########### ГЛАВНОЕ ОКНО ###########
####################################

class AddRoomDialog(QDialog):
    """Новая комната: название + этаж (1 этаж / 2 этаж / Участок)."""

    def __init__(self, existing_names, default_floor="floor1", parent=None):
        super().__init__(parent)
        self.existing = {n.lower() for n in existing_names}
        self.setWindowTitle("Новая комната")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        title = QLabel("Новая комната")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Название, например «Детская»")
        self.name_edit.setMaxLength(30)
        layout.addWidget(self.name_edit)
        caption = QLabel("На каком этаже?")
        caption.setObjectName("subtitle")
        layout.addWidget(caption)
        row = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.buttons = {}
        for code, name, _ in FLOORS:
            btn = QPushButton(name)
            btn.setObjectName("chip")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self.update_hint)
            self.group.addButton(btn)
            self.buttons[code] = btn
            row.addWidget(btn)
        self.buttons.get(default_floor, self.buttons["floor1"]).setChecked(True)
        layout.addLayout(row)
        self.hint = QLabel()
        self.hint.setObjectName("subtitle")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.error = QLabel()
        self.error.setObjectName("error")
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        cancel = QPushButton("Отмена")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Создать комнату")
        ok.clicked.connect(self.try_accept)
        self.name_edit.returnPressed.connect(self.try_accept)
        buttons.addWidget(cancel)
        buttons.addWidget(ok, 2)
        layout.addLayout(buttons)
        self.update_hint()

    def floor(self):
        return next(code for code, btn in self.buttons.items() if btn.isChecked())

    def update_hint(self, *_):
        self.hint.setText(f"📍 Комната появится во вкладках с пометкой «{FLOOR_SHORT[self.floor()]}», "
                          f"а её устройства — на плане «{FLOOR_NAMES[self.floor()]}»")

    def try_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            self.error.setText("Введите название комнаты")
        elif name.lower() in self.existing:
            self.error.setText("Комната с таким названием уже есть")
        else:
            self.room_name = name
            self.accept()


class MainWindow(QMainWindow):
    logged_out = pyqtSignal()

    COLUMNS = 3
    PAGES = [("devices", "📱 Устройства"), ("plan", "🗺 План дома"), ("energy", "📊 Энергия"), ("events", "🔔 События")]
    STATEFUL_TYPES = {"kettle", "washer", "robot_vacuum"}  # их состояние периодически сохраняется в базу

    def __init__(self, db: Database, user: dict):
        super().__init__()
        self.db = db
        self.user = user
        self.devices = []
        self.rooms = []
        self.cards = {}
        self.readings = {}       # id устройства -> текст показаний (датчики, инвертор и т.п.)
        self.sensor_state = {}   # внутреннее состояние симуляции датчиков
        self.room_temps = {}     # id комнаты -> температура воздуха
        self.energy_history = []  # [(минута суток, выработка Вт, потребление Вт, заряд 0..1, из сети Вт)]
        self.history_day = None
        self.control_dialog = None
        self.unread_events = 0
        self._battery_flags = None
        self._last_camera_toast = 0.0
        self.eco_mode = bool(user.get("eco_mode", 1))
        self.tariff = float(user.get("tariff_kzt", DEFAULT_TARIFF_KZT))
        self.events = db.get_events(user["id"])
        self.setWindowTitle(f"Умный дом — {user['username']}")
        self.resize(1320, 860)
        self.setMinimumSize(1200, 760)

        totals = {"generated": user.get("total_generated_wh", 0.0), "import": user.get("total_import_wh", 0.0),
                  "export": user.get("total_export_wh", 0.0)}
        self.simulator = SolarSimulator(db.get_battery(user["id"]), self.current_device_load, totals, parent=self)
        self._save_counter = 0

        self.init_ui()
        self.toasts = ToastManager(self.centralWidget())
        self.reload_rooms()
        self.reload_devices()
        self.db.backfill_energy_history(user["id"], len(self.devices), date.today() - timedelta(days=1))

        self.simulator.updated.connect(self.on_energy_update)
        self.solar_panel.speed_changed.connect(self.simulator.set_speed)
        self.simulator.start()

    # ---------- интерфейс ----------

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Шапка в стиле Xiaomi Home: имя дома, батарея, «+», меню пользователя, вкладки комнат
        header = QFrame()
        header.setObjectName("header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(32, 22, 32, 0)
        header_layout.setSpacing(14)

        top = QHBoxLayout()
        home_title = QLabel(f"🏠 Дом пользователя {self.user['username']}")
        home_title.setStyleSheet("font-size: 26px; font-weight: 800;")
        top.addWidget(home_title)
        top.addStretch()

        self.battery_chip = QLabel()
        self.battery_chip.setStyleSheet(
            "background: rgba(255,255,255,0.18); border-radius: 10px; padding: 8px 14px; "
            "font-size: 15px; font-weight: 600;"
        )
        top.addWidget(self.battery_chip)
        top.addSpacing(8)

        add_btn = QToolButton()
        add_btn.setObjectName("headerButton")
        add_btn.setText("＋  Устройство")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self.open_add_device)
        top.addWidget(add_btn)

        user_btn = QToolButton()
        user_btn.setObjectName("headerButton")
        user_btn.setText(f"👤 {self.user['username']} ▾")
        user_btn.setCursor(Qt.PointingHandCursor)
        user_btn.setPopupMode(QToolButton.InstantPopup)
        user_menu = QMenu(user_btn)
        user_menu.addAction("Выйти из аккаунта", self.logout)
        user_btn.setMenu(user_menu)
        top.addWidget(user_btn)
        header_layout.addLayout(top)

        tabs_row = QHBoxLayout()
        self.tab_bar = QTabBar()
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setUsesScrollButtons(True)
        # размер шрифта задаётся через setFont, а не QSS - иначе QTabBar
        # считает ширину вкладки по старому шрифту и обрезает название
        tab_font = QFont(self.font())
        tab_font.setPixelSize(17)
        tab_font.setBold(True)
        self.tab_bar.setFont(tab_font)
        self.tab_bar.currentChanged.connect(self.on_room_changed)
        tabs_row.addWidget(self.tab_bar, 1)

        rooms_btn = QToolButton()
        rooms_btn.setObjectName("headerButton")
        rooms_btn.setText("☰")
        rooms_btn.setToolTip("Управление комнатами")
        rooms_btn.setCursor(Qt.PointingHandCursor)
        rooms_btn.setPopupMode(QToolButton.InstantPopup)
        rooms_menu = QMenu(rooms_btn)
        rooms_menu.aboutToShow.connect(lambda: self.fill_rooms_menu(rooms_menu))
        rooms_btn.setMenu(rooms_menu)
        tabs_row.addWidget(rooms_btn, alignment=Qt.AlignTop)
        header_layout.addLayout(tabs_row)
        root.addWidget(header)

        # Тело: слева страницы (устройства / план / энергия / события), справа панель солнечной энергии
        body = QHBoxLayout()
        body.setContentsMargins(32, 18, 32, 24)
        body.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(12)
        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = {}
        for i, (code, caption) in enumerate(self.PAGES):
            btn = QPushButton(caption)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, n=i: self.show_page(n))
            self.nav_group.addButton(btn, i)
            self.nav_buttons[code] = btn
            nav.addWidget(btn)
        nav.addStretch()
        left.addLayout(nav)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_devices_page())
        self.plan_page = FloorPlanPage(self)
        self.pages.addWidget(self.plan_page)
        self.energy_page = EnergyPage(self)
        self.pages.addWidget(self.energy_page)
        self.events_page = EventsPage(self)
        self.pages.addWidget(self.events_page)
        left.addWidget(self.pages, 1)
        body.addLayout(left, 1)

        self.solar_panel = SolarPanelWidget()
        body.addWidget(self.solar_panel)
        root.addLayout(body, 1)
        self.show_page(0)

    def _build_devices_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        summary_row = QHBoxLayout()
        self.summary_label = QLabel()
        self.summary_label.setObjectName("subtitle")
        self.summary_label.setStyleSheet("font-size: 15px;")
        summary_row.addWidget(self.summary_label)
        summary_row.addStretch()
        hint = QLabel("Клик по карточке — управление, ПКМ — меню")
        hint.setStyleSheet("font-size: 12px; color: #8aa0b2;")
        summary_row.addWidget(hint)
        layout.addLayout(summary_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        grid_host = QWidget()
        self.grid = QGridLayout(grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(grid_host)
        layout.addWidget(scroll, 1)
        return page

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        self.nav_group.button(index).setChecked(True)
        if self.PAGES[index][0] == "events":
            self.unread_events = 0
        self._update_events_badge()
        if self.PAGES[index][0] == "energy" and self.simulator.state:
            self.energy_page.update_state(self.simulator.state)

    def _update_events_badge(self):
        caption = dict(self.PAGES)["events"]
        self.nav_buttons["events"].setText(f"{caption}  ({self.unread_events})" if self.unread_events else caption)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toasts"):
            self.toasts.relayout()

    # ---------- данные ----------

    def fill_rooms_menu(self, menu):
        menu.clear()
        menu.addAction("➕  Добавить комнату…", self.add_room)
        room_id = self.current_room_id()
        floor_menu = menu.addMenu("🏢  Этаж текущей комнаты")
        if room_id is None:
            floor_menu.setEnabled(False)
            floor_menu.setTitle("🏢  Этаж комнаты (выберите вкладку комнаты)")
        else:
            current = self.room_floor(room_id)
            for code, name, _ in FLOORS:
                action = floor_menu.addAction(name, lambda c=code: self.change_room_floor(room_id, c))
                action.setCheckable(True)
                action.setChecked(code == current)
        menu.addSeparator()
        menu.addAction("🗑  Удалить текущую комнату", self.delete_current_room)

    def room_floor(self, room_id):
        return next((r["floor"] for r in self.rooms if r["id"] == room_id), "floor1")

    def change_room_floor(self, room_id, floor):
        self.db.set_room_floor(room_id, floor)
        self.log_event("device", "🏢", f"Комната «{self.room_name(room_id)}» перенесена: {FLOOR_NAMES[floor]}")
        self.reload_rooms(select_room_id=room_id)
        self.reload_devices()
        self.plan_page.set_room(room_id, floor)

    def reload_rooms(self, select_room_id=None):
        current_room = self.current_room_id() if select_room_id is None else select_room_id
        self.rooms = self.db.get_rooms(self.user["id"])
        self.tab_bar.blockSignals(True)
        while self.tab_bar.count():
            self.tab_bar.removeTab(0)
        self.tab_bar.addTab("Умный дом")
        self.tab_bar.setTabData(0, None)
        for room in self.rooms:
            index = self.tab_bar.addTab(f"{room['name']} · {FLOOR_SHORT.get(room['floor'], '')}")
            self.tab_bar.setTabData(index, room["id"])
            self.tab_bar.setTabToolTip(index, f"{room['name']} — {FLOOR_NAMES.get(room['floor'], '')}")
        target = 0
        for i in range(self.tab_bar.count()):
            if self.tab_bar.tabData(i) == current_room:
                target = i
        self.tab_bar.setCurrentIndex(target)
        self.tab_bar.blockSignals(False)
        baseline = room_baseline_temp(self.simulator.sim_minutes)
        for room in self.rooms:
            self.room_temps.setdefault(room["id"], baseline + random.uniform(-0.6, 0.6))

    def reload_devices(self):
        old = {d["id"]: d for d in self.devices}
        self.devices = self.db.get_devices(self.user["id"])
        for d in self.devices:  # переносим служебные (несохраняемые) поля
            for key, value in old.get(d["id"], {}).items():
                if key.startswith("_"):
                    d[key] = value
        self.update_readings(self.simulator.state or None)
        self.refresh_grid()

    def find_device(self, device_id):
        return next((d for d in self.devices if d["id"] == device_id), None)

    def room_name(self, room_id):
        return next((r["name"] for r in self.rooms if r["id"] == room_id), "")

    def current_room_id(self):
        if self.tab_bar.count() == 0:
            return None
        return self.tab_bar.tabData(self.tab_bar.currentIndex())

    def current_device_load(self):
        return sum(device_power(d) for d in self.devices)

    def on_room_changed(self, *_):
        self.refresh_grid()
        room_id = self.current_room_id()
        self.plan_page.set_room(room_id, self.room_floor(room_id) if room_id is not None else None)

    def refresh_grid(self, *_):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()  # deleteLater удаляет не сразу - без hide старая карточка мелькает
                item.widget().deleteLater()
        self.cards = {}

        room_id = self.current_room_id()
        visible = [d for d in self.devices if room_id is None or d["room_id"] == room_id]

        if not visible:
            self.grid.addWidget(self._empty_state(), 0, 0, 1, self.COLUMNS)
        for i, device in enumerate(visible):
            card = DeviceCard(device, show_room=room_id is None)
            card.refresh(self.readings.get(device["id"]))
            card.toggled.connect(self.on_card_toggled)
            card.open_requested.connect(self.open_device)
            card.menu_requested.connect(self.show_device_menu)
            self.grid.addWidget(card, i // self.COLUMNS, i % self.COLUMNS)
            self.cards[device["id"]] = card
        self.update_summary()

    def refresh_cards(self):
        for device_id, card in self.cards.items():
            card.refresh(self.readings.get(device_id))
        self.update_summary()

    def _empty_state(self):
        box = QFrame()
        box.setObjectName("card")
        box.setMinimumWidth(3 * 256 + 2 * 16)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)
        icon = QLabel("📱")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 56px;")
        empty_text = "В доме пока нет устройств" if self.current_room_id() is None else "В этой комнате пока нет устройств"
        text = QLabel(f"{empty_text}\nВыберите тип и модель из каталога, чтобы добавить первое")
        text.setAlignment(Qt.AlignCenter)
        text.setObjectName("subtitle")
        btn = QPushButton("Добавить устройство")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.open_add_device)
        layout.addWidget(icon)
        layout.addWidget(text)
        layout.addWidget(btn)
        return box

    def update_summary(self):
        total = len(self.devices)
        on = sum(1 for d in self.devices if d["is_on"])
        self.summary_label.setText(
            f"Устройств: {total}  ·  включено: {on}  ·  нагрузка устройств: "
            f"{format_power(self.current_device_load())}"
        )

    # ---------- журнал событий ----------

    def log_event(self, category, icon, text, toast=False, color=None):
        sim_time = sim_time_text(self.simulator.sim_minutes)
        event = {"sim_time": sim_time, "category": category, "icon": icon, "text": text}
        self.db.add_event(self.user["id"], sim_time, category, icon, text)
        self.events.append(event)
        self.events = self.events[-300:]
        self.events_page.add_event(event)
        if self.pages.currentWidget() is not self.events_page:
            self.unread_events += 1
            self._update_events_badge()
        if toast:
            default = {"energy": "#f5b301", "security": "#e5484d"}.get(category, ACCENT)
            self.toasts.show(icon, text, color or default)

    def clear_events(self):
        self.db.clear_events(self.user["id"])
        self.events = []
        self.unread_events = 0
        self._update_events_badge()
        self.events_page.reload()

    # ---------- симуляция показаний датчиков ----------

    def update_readings(self, state):
        if not state:
            return
        sim_minutes = state["sim_minutes"]
        advanced = state.get("advanced")
        sensors_count = sum(1 for d in self.devices if DEVICE_TYPES[d["type_code"]]["group"] == "Датчики")

        for d in self.devices:
            t = d["type_code"]
            room = d["room_name"]
            st = self.sensor_state.setdefault(d["id"], {
                "hum": random.uniform(38, 52), "present": False, "open": False, "last_motion": None, "noise": 0.0,
            })
            text = None
            sensor_on = bool(d["is_on"])
            if t == "temp_sensor":
                st["noise"] = max(-0.3, min(0.3, st["noise"] + random.uniform(-0.03, 0.03)))
                st["hum"] = min(65, max(30, st["hum"] + random.uniform(-0.3, 0.3)))
                temp = self.room_temps.get(d["room_id"], ROOM_TEMP) + st["noise"]
                text = f"🌡 {temp:.1f} °C · 💧 {st['hum']:.0f}%"
            elif t in ("air_conditioner", "heater"):
                text = f"🌡 {self.room_temps.get(d['room_id'], ROOM_TEMP):.1f}°C"
            elif t == "presence_sensor":
                if advanced and random.random() < 0.02:
                    st["present"] = not st["present"]
                    if sensor_on:
                        self.log_event("security", "👥", f"{'Обнаружено присутствие' if st['present'] else 'Никого нет'}: {room}")
                text = "👥 Есть присутствие" if st["present"] else "Никого нет"
            elif t == "motion_sensor":
                if advanced and random.random() < 0.03:
                    st["last_motion"] = sim_minutes
                    if sensor_on:
                        self.log_event("security", "🏃", f"Движение: {room} ({d['name']})")
                if st["last_motion"] is None:
                    text = "Движения не было"
                elif sim_minutes - st["last_motion"] < 1:
                    text = "🏃 Движение сейчас"
                else:
                    text = f"Движение {int(sim_minutes - st['last_motion'])} мин назад"
            elif t == "door_sensor":
                if advanced and random.random() < 0.01:
                    st["open"] = not st["open"]
                    if sensor_on:
                        self.log_event("security", "🚪", f"{'Открыто' if st['open'] else 'Закрыто'}: {d['name']} ({room})")
                text = "🚪 Открыто" if st["open"] else "Закрыто"
            elif t == "smoke_sensor":
                text = "✅ Дыма нет"
            elif t == "leak_sensor":
                text = "✅ Протечек нет"
            elif t == "light_sensor":
                lux = 5 + state["generation"] / SOLAR_PEAK_W * 1500
                text = f"🔆 {lux:.0f} лк"
            elif t == "inverter":
                text = f"☀️ Выработка {format_power(state['generation'])}"
            elif t == "battery_bms":
                if state["charge"] > 1:
                    flow = f"+{format_power(state['charge'])}"
                elif state["discharge"] > 1:
                    flow = f"−{format_power(state['discharge'])}"
                else:
                    flow = "покой"
                text = f"🔋 {state['level'] * 100:.0f}% · {flow}"
            elif t == "gateway":
                text = f"Датчиков в сети: {sensors_count}"
            elif t in ("camera", "doorbell"):
                if d["settings"].get("recording"):
                    text = "🔴 Запись"
                # камеры с детекцией иногда замечают людей
                if advanced and sensor_on and d["settings"].get("motion_alerts") and random.random() < 0.006:
                    now = datetime.now().timestamp()
                    toast = now - self._last_camera_toast > 20
                    if toast:
                        self._last_camera_toast = now
                    self.log_event("security", "📹", f"{d['name']}: обнаружен человек ({room})", toast=toast)
            if text is not None:
                self.readings[d["id"]] = text

    # ---------- физика устройств ----------

    def step_climate(self, minutes):
        """Температура в комнатах: кондиционеры охлаждают/греют, обогреватели греют, иначе - к «естественной»."""
        baseline = room_baseline_temp(self.simulator.sim_minutes)
        for room in self.rooms:
            room_id = room["id"]
            temp = self.room_temps.setdefault(room_id, baseline)
            controlled = False
            for d in self.devices:
                if d["room_id"] != room_id or d["type_code"] not in ("air_conditioner", "heater") or not d["is_on"]:
                    continue
                s = d["settings"]
                model = MODELS[d["model_code"]]
                target = s.get("target_temp", 22)
                was_active = d.get("_climate_active", True)
                if d["type_code"] == "heater":
                    factor = dict(TYPE_MODES["heater"]).get(s.get("mode"), 0.75)
                    rate = (0.05 + 0.12 * factor) * (model["power"] / 2200) ** 0.5
                    direction = 1 if temp < target - 0.2 else 0
                else:
                    levels = model.get("levels", 3)
                    rate = (0.06 + 0.1 * s.get("fan_speed", 2) / levels) * (model["power"] / 1100) ** 0.5
                    mode = s.get("mode", "Охлаждение")
                    if mode == "Охлаждение":
                        direction = -1 if temp > target + 0.2 else 0
                    elif mode == "Обогрев":
                        direction = 1 if temp < target - 0.2 else 0
                    elif mode == "Авто":
                        direction = -1 if temp > target + 0.4 else (1 if temp < target - 0.4 else 0)
                    else:
                        d["_climate_active"] = True
                        continue
                if direction:
                    temp += direction * rate * minutes
                    temp = min(temp, target) if direction > 0 else max(temp, target)
                    d["_climate_active"] = True
                else:
                    temp += (target - temp) * min(1.0, 0.5 * minutes)
                    d["_climate_active"] = False
                    if was_active:
                        icon = "🔥" if d["type_code"] == "heater" else "❄️"
                        self.log_event("device", icon, f"{d['name']}: в комнате «{room['name']}» достигнуто {target}°C",
                                       toast=True)
                controlled = True
            if not controlled:
                temp += (baseline - temp) * min(1.0, 0.02 * minutes)
            self.room_temps[room_id] = temp

    def step_washer(self, d, minutes):
        s = d["settings"]
        if not d["is_on"]:
            return
        before = washer_phase(washer_fraction(s))
        s["wash_elapsed"] = s.get("wash_elapsed", 0.0) + minutes
        if washer_fraction(s) >= 1.0:
            s["wash_elapsed"] = 0.0
            s["wash_done"] = True
            self.set_device_on(d, False, source="auto")
            self.log_event("device", "🧺", f"{d['name']}: стирка завершена ({s.get('mode')})", toast=True)
        elif washer_phase(washer_fraction(s)) != before:
            self.log_event("device", "🧺", f"{d['name']}: {washer_phase(washer_fraction(s)).lower()}")

    def step_vacuum(self, d, minutes):
        s = d["settings"]
        state = s.get("vac_state", "docked")
        mode_factor = dict(TYPE_MODES["robot_vacuum"]).get(s.get("mode"), 1.0)
        if state == "cleaning":
            s["vac_progress"] = min(1.0, s.get("vac_progress", 0.0) + minutes / VAC_CLEAN_MIN)
            s["vac_battery"] = max(0.0, s.get("vac_battery", 100) - minutes * VAC_DRAIN * mode_factor)
            if s["vac_progress"] >= 1.0:
                s.update(vac_state="returning", vac_return=0.0)
                self.log_event("device", "🤖", f"{d['name']}: уборка завершена, возвращается на базу", toast=True)
            elif s["vac_battery"] <= VAC_LOW_BATTERY:
                s.update(vac_state="returning", vac_return=0.0)
                self.log_event("device", "🪫", f"{d['name']}: низкий заряд, едет на базу", toast=True)
        elif state == "returning":
            s["vac_return"] = min(1.0, s.get("vac_return", 0.0) + minutes / VAC_RETURN_MIN)
            if s["vac_return"] >= 1.0:
                finished = s.get("vac_progress", 0) >= 1.0
                s.update(vac_state="docked", vac_return=0.0)
                if finished:
                    s["vac_progress"] = 0.0
                if d["is_on"]:
                    d["is_on"] = 0
                    self.db.set_device_state(d["id"], False)
                self.log_event("device", "🏠", f"{d['name']}: на базе, заряжается")
        elif state == "docked":
            s["vac_battery"] = min(100.0, s.get("vac_battery", 100) + minutes * VAC_CHARGE)

    def allocate_solar(self, state):
        """Режим «только от излишков солнца»: раздаём устройствам то, что панели дают сверх потребления дома."""
        solar_devices = [d for d in self.devices if d["is_on"] and d["settings"].get("solar_only")]
        for d in self.devices:
            if d not in solar_devices:
                d["_solar_power"] = 0.0
        if not solar_devices:
            return
        house = BASE_LOAD_W + sum(device_power(d) for d in self.devices if d not in solar_devices)
        available = state["generation"] - house if state["level"] >= SOLAR_ONLY_MIN_LEVEL else 0.0
        solar_devices.sort(key=lambda d: d["type_code"] != "ev_charger")
        for d in solar_devices:
            full = solar_full_power(d)
            previous = d.get("_solar_power", 0.0)
            threshold = EV_MIN_POWER if d["type_code"] == "ev_charger" else full * 0.9
            if previous > 1:
                threshold *= 0.75  # гистерезис, чтобы не дёргаться от облаков
            if available >= threshold:
                power = min(full, available) if d["type_code"] == "ev_charger" else full
            else:
                power = 0.0
            available -= power
            d["_solar_power"] = power
            if previous <= 1 < power:
                self.log_event("energy", "☀️", f"{d['name']}: работает от излишков солнца ({format_power(power)})",
                               toast=True)
            elif previous > 1 >= power:
                self.log_event("energy", "⏸", f"{d['name']}: излишков нет — ждёт солнца")

    def check_eco(self, state):
        level = state["level"]
        if self.eco_mode and level < ECO_OFF_LEVEL:
            shed = [d for d in self.devices if d["type_code"] in ECO_SHED_TYPES and d["is_on"]
                    and not d.get("_eco_override") and not d["settings"].get("solar_only")]
            for d in shed:
                d["settings"]["eco_shed"] = True
                self.set_device_on(d, False, source="eco")
            if shed:
                self.log_event("energy", "🌿", f"Эко-режим: АКБ {level * 100:.0f}% — отключены: "
                               + ", ".join(d["name"] for d in shed), toast=True)
        elif level >= ECO_RESTORE_LEVEL:
            restored = [d for d in self.devices if d["settings"].get("eco_shed")]
            for d in restored:
                d["settings"].pop("eco_shed", None)
                self.set_device_on(d, True, source="eco")
            for d in self.devices:
                d.pop("_eco_override", None)
            if restored:
                self.log_event("energy", "🌿", f"Эко-режим: АКБ {level * 100:.0f}% — снова включены: "
                               + ", ".join(d["name"] for d in restored), toast=True)

    def check_energy_events(self, state):
        level, gen = state["level"], state["generation"]
        flags = self._battery_flags
        if flags is None:
            self._battery_flags = {"low": level < 0.2, "grid": state["grid_import"] > 1, "full": level >= 0.999,
                                   "sun": gen > 0}
            return
        if level < 0.2 and not flags["low"]:
            flags["low"] = True
            self.log_event("energy", "🪫", f"Заряд АКБ ниже 20% ({level * 100:.0f}%)", toast=True, color="#e5484d")
        elif level > 0.25:
            flags["low"] = False
        if state["grid_import"] > 50 and not flags["grid"]:
            flags["grid"] = True
            self.log_event("energy", "🔌", "Дом перешёл на питание от внешней сети", toast=True, color="#e5484d")
        elif state["grid_import"] < 1 and flags["grid"]:
            flags["grid"] = False
            self.log_event("energy", "🔋", "Питание от сети больше не требуется")
        if level >= 0.999 and not flags["full"]:
            flags["full"] = True
            self.log_event("energy", "🔋", "Аккумулятор полностью заряжен", toast=True, color=ACCENT)
        elif level < 0.97:
            flags["full"] = False
        if gen > 0 and not flags["sun"]:
            flags["sun"] = True
            self.log_event("energy", "🌅", "Восход — солнечные панели начали выработку")
        elif gen <= 0 and flags["sun"]:
            flags["sun"] = False
            day_kwh = state["generated_today"] / 1000
            self.log_event("energy", "🌇", f"Закат — выработка за день {day_kwh:.1f} кВт·ч "
                                         f"(≈ {format_money(day_kwh * self.tariff)})", toast=True)

    def record_history(self, state):
        day = int(state["sim_minutes"] // 1440)
        minute = state["sim_minutes"] % 1440
        if day != self.history_day:
            self.history_day = day
            self.energy_history = []
        if not self.energy_history or minute - self.energy_history[-1][0] >= 2:
            self.energy_history.append((minute, state["generation"], state["load"], state["level"], state["grid_import"],
                                        state["grid_export"]))

    # ---------- действия ----------

    def set_device_on(self, device, on, source="user"):
        s = device["settings"]
        t = device["type_code"]
        if t == "robot_vacuum":
            if on:
                if s.get("vac_battery", 100) < VAC_LOW_BATTERY + 10:
                    self.log_event("device", "🪫", f"{device['name']}: недостаточно заряда для уборки", toast=True)
                    on = False
                else:
                    if s.get("vac_progress", 0) >= 1.0:
                        s["vac_progress"] = 0.0
                    s["vac_state"] = "cleaning"
            elif s.get("vac_state") in ("cleaning", "paused"):
                s.update(vac_state="returning", vac_return=0.0)
        if t == "washer":
            if on:
                s.pop("wash_done", None)
            elif source == "user":
                s["wash_elapsed"] = 0.0  # пользователь остановил программу
        if source == "user" and on and t in ECO_SHED_TYPES and self.simulator.state.get("level", 1) < ECO_OFF_LEVEL:
            device["_eco_override"] = True
            s.pop("eco_shed", None)

        device["is_on"] = int(on)
        if not on:
            s.pop("off_at", None)
            s.pop("timer_min", None)
        self.db.save_settings(device["id"], s)
        self.db.set_device_state(device["id"], on)
        if source == "user":
            self.log_event("device", "🟢" if on else "⚪", f"{'Включено' if on else 'Выключено'}: {device['name']} "
                                                         f"({device['room_name']})")
        card = self.cards.get(device["id"])
        if card:
            card.refresh(self.readings.get(device["id"]))
        self.update_summary()
        self.simulator.tick(advance=False)

    def on_card_toggled(self, device_id, checked):
        device = self.find_device(device_id)
        if device:
            self.set_device_on(device, checked)

    def on_device_changed(self, device):
        """Настройки устройства изменены в окне управления."""
        self.db.save_settings(device["id"], device["settings"])
        card = self.cards.get(device["id"])
        if card:
            card.refresh(self.readings.get(device["id"]))
        self.update_summary()
        self.simulator.tick(advance=False)

    def open_device(self, device_id):
        device = self.find_device(device_id)
        if device is None:
            return
        self.control_dialog = DeviceControlDialog(self, device)
        self.control_dialog.exec_()
        self.control_dialog = None

    def run_scene(self, code, room_id):
        """Сценарии пультов/панелей. Возвращает количество изменённых устройств."""
        changed = 0
        for d in self.devices:
            info = DEVICE_TYPES[d["type_code"]]
            is_light = info["group"] == LIGHT_GROUP
            in_room = d["room_id"] == room_id
            if code == "room_lights_on":
                target = True if (is_light and in_room) else None
            elif code == "room_off":
                target = False if (in_room and not is_always_on(d["type_code"])) else None
            elif code == "house_lights_off":
                target = False if is_light else None
            else:  # house_off
                target = False if not is_always_on(d["type_code"]) else None
            if target is not None and bool(d["is_on"]) != target:
                self.set_device_on(d, target, source="scene")
                changed += 1
        caption = dict(SCENES).get(code, code)
        self.log_event("device", "🎬", f"Сценарий «{caption[2:]}»: изменено устройств — {changed}")
        return changed

    def show_device_menu(self, device_id, global_pos):
        device = self.find_device(device_id)
        if device is None:
            return
        menu = QMenu(self)
        menu.addAction("⚙️  Управление", lambda: self.open_device(device_id))
        menu.addAction("✏️  Переименовать", lambda: self.rename_device(device))
        move_menu = menu.addMenu("🚚  Переместить в комнату")
        for room in self.rooms:
            action = move_menu.addAction(room["name"], lambda r=room["id"]: self.move_device(device, r))
            action.setEnabled(room["id"] != device["room_id"])
        plan_menu = menu.addMenu("🗺  На плане")
        for code, caption, _ in PLAN_FLOORS:
            plan_menu.addAction(caption, lambda c=code: self.place_on_plan(device, c))
        plan_menu.addAction("Вернуть место по комнате", lambda: self.place_on_plan(device, None))
        menu.addSeparator()
        menu.addAction("🗑  Удалить устройство", lambda: self.delete_device(device))
        menu.exec_(global_pos)

    def place_on_plan(self, device, floor):
        if floor is None:
            device["settings"].pop("plan", None)
        else:
            device["settings"]["plan"] = {"floor": floor, "x": 0.5, "y": 0.5}
            self.plan_page.set_floor(floor)
        self.db.save_settings(device["id"], device["settings"])
        self.plan_page.view.update()

    def rename_device(self, device):
        name, ok = QInputDialog.getText(self, "Переименовать", "Новое название:", text=device["name"])
        if ok and name.strip():
            self.db.rename_device(device["id"], name.strip()[:40])
            self.reload_devices()

    def move_device(self, device, room_id):
        device["settings"].pop("plan", None)
        self.db.save_settings(device["id"], device["settings"])
        self.db.move_device(device["id"], room_id)
        self.reload_devices()

    def delete_device(self, device):
        answer = QMessageBox.question(self, "Удаление", f"Удалить устройство «{device['name']}»?")
        if answer != QMessageBox.Yes:
            return False
        self.db.delete_device(device["id"])
        self.log_event("device", "🗑", f"Удалено устройство: {device['name']}")
        self.reload_devices()
        self.simulator.tick(advance=False)
        return True

    def open_add_device(self):
        dialog = AddDeviceDialog(self.db, self.user["id"], self.rooms, self.current_room_id(), self)
        accepted = dialog.exec_() == QDialog.Accepted
        if dialog.rooms_changed:
            self.reload_rooms()
        if accepted:
            self.reload_devices()
            newest = max(self.devices, key=lambda d: d["id"], default=None)
            if newest is not None:
                self.log_event("device", "➕", f"Добавлено устройство: {newest['name']} ({newest['room_name']})",
                               toast=True)
            self.simulator.tick(advance=False)

    def add_room(self):
        current = self.current_room_id()
        default_floor = self.room_floor(current) if current is not None else self.plan_page.view.floor
        dialog = AddRoomDialog([r["name"] for r in self.rooms], default_floor, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        floor = dialog.floor()
        room_id = self.db.add_room(self.user["id"], dialog.room_name, floor)
        self.log_event("device", "🚪", f"Добавлена комната «{dialog.room_name}» ({FLOOR_NAMES[floor]})")
        self.reload_rooms(select_room_id=room_id)
        self.room_temps.setdefault(room_id, room_baseline_temp(self.simulator.sim_minutes))
        self.on_room_changed()

    def delete_current_room(self):
        room_id = self.current_room_id()
        if room_id is None:
            QMessageBox.information(self, "Комната", "Выберите вкладку комнаты, которую нужно удалить")
            return
        room_name = self.tab_bar.tabText(self.tab_bar.currentIndex())
        count = sum(1 for d in self.devices if d["room_id"] == room_id)
        text = f"Удалить комнату «{room_name}»?"
        if count:
            text += f"\nВместе с ней будут удалены устройства: {count}."
        if QMessageBox.question(self, "Удаление комнаты", text) == QMessageBox.Yes:
            self.db.delete_room(room_id)
            self.reload_rooms(select_room_id=None)
            self.tab_bar.setCurrentIndex(0)
            self.reload_devices()
            self.simulator.tick(advance=False)

    def energy_days(self, start, end):
        """{дата: (выработка, потребление, из сети, в сеть)} за период; текущий день - живые цифры симуляции."""
        days = self.db.get_energy_days(self.user["id"], start, end)
        today = self.simulator.sim_date()
        if start <= today <= end and self.simulator.state:
            st = self.simulator.state
            days[today] = (st["generated_today"], st["consumed_today"], st["import_today"], st["export_today"])
        return days

    def set_eco_mode(self, enabled):
        self.eco_mode = bool(enabled)
        self.db.set_user_option(self.user["id"], "eco_mode", int(enabled))
        self.log_event("energy", "🌿", "Эко-режим включён" if enabled else "Эко-режим выключен")

    def set_tariff(self, value):
        self.tariff = float(value)
        self.db.set_user_option(self.user["id"], "tariff_kzt", self.tariff)
        self.energy_page.reports.refresh()
        if self.simulator.state:
            self.energy_page.update_state(self.simulator.state)

    def on_energy_update(self, state):
        if state.get("closed_day"):
            self.db.save_energy_day(self.user["id"], *state["closed_day"])
        if state.get("advanced"):
            minutes = self.simulator.minutes_per_tick
            for d in list(self.devices):
                # Таймеры автоотключения считаются по времени симуляции
                off_at = d["settings"].get("off_at")
                if off_at is not None and d["is_on"] and state["sim_minutes"] >= off_at:
                    self.set_device_on(d, False, source="auto")
                    self.log_event("device", "⏱", f"Таймер: выключено «{d['name']}»")
                t = d["type_code"]
                if t == "kettle":
                    was_on = d["is_on"]
                    result = kettle_step(d)
                    if result == "done":
                        self.set_device_on(d, False, source="auto")
                        self.log_event("device", "☕", f"{d['name']}: вода нагрета до {d['settings'].get('target_temp')}°C",
                                       toast=True)
                    elif result == "empty" and was_on:
                        self.set_device_on(d, False, source="auto")
                        self.log_event("device", "💧", f"{d['name']}: нет воды — нагрев отменён", toast=True,
                                       color="#e5484d")
                elif t == "washer":
                    self.step_washer(d, minutes)
                elif t == "robot_vacuum":
                    self.step_vacuum(d, minutes)
            self.step_climate(minutes)
            self.allocate_solar(state)
            self.check_eco(state)
            self.check_energy_events(state)
            self.record_history(state)

        self.update_readings(state)
        self.refresh_cards()
        if self.control_dialog is not None:
            self.control_dialog.refresh_live()

        self.solar_panel.update_state(state)
        if self.pages.currentWidget() is self.energy_page:
            self.energy_page.update_state(state)
        icon = "⚡" if state["charge"] > 1 else "🔋"
        self.battery_chip.setText(f"{icon} {state['level'] * 100:.0f}%  ·  ☀️ {format_power(state['generation'])}")
        if state.get("advanced"):
            self._save_counter += 1
            if self._save_counter % 10 == 0:
                self.save_state()

    def save_state(self):
        self.db.save_battery(self.user["id"], self.simulator.battery_wh)
        self.db.save_energy_totals(self.user["id"], self.simulator.total_generated_wh,
                                   self.simulator.total_import_wh, self.simulator.total_export_wh)
        for d in self.devices:
            if d["type_code"] in self.STATEFUL_TYPES:
                self.db.save_settings(d["id"], d["settings"])

    def logout(self):
        self.logged_out.emit()
        self.close()

    def closeEvent(self, event):
        self.simulator.stop()
        self.save_state()
        super().closeEvent(event)


####################################
############ ЗАПУСК ################
####################################

class SmartHomeApp:
    """Переключение между окном входа и главным окном (вход / выход из аккаунта)."""

    def __init__(self, db: Database):
        self.db = db
        self.main_window = None
        self.login_window = LoginWindow(db)
        self.login_window.logged_in.connect(self.open_main)

        auto_user = db.get_user(AUTO_LOGIN_USER) if SKIP_AUTH else None
        if auto_user is not None:
            self.open_main(dict(auto_user))
        else:
            self.login_window.show()

    def open_main(self, user):
        self.main_window = MainWindow(self.db, user)
        self.main_window.logged_out.connect(self.back_to_login)
        self.main_window.show()
        self.login_window.hide()

    def back_to_login(self):
        # окно входа показывается до закрытия главного, иначе Qt завершит приложение
        self.login_window.reset()
        self.login_window.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)

    db = Database()
    controller = SmartHomeApp(db)

    sys.exit(app.exec_())
