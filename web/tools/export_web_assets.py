"""
Готовит данные и картинки для веб-версии (web/) из настольной home.py:
каталог устройств, режимы, стартовый дом, сцены для камер, планировки, иконки.
Запуск: QT_QPA_PLATFORM=offscreen python web/tools/export_web_assets.py
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(ROOT, "web")
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import home  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from PyQt5.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QRadialGradient, QPainterPath, QImage  # noqa: E402
from PyQt5.QtCore import Qt, QRectF, QPointF  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)


def export_data():
    data = {
        "groups": [{"name": g, "types": [{"code": c, "name": n, "icon": i} for c, n, i in items]}
                   for g, items in home.DEVICE_GROUPS],
        "catalog": {t: [{k: v for k, v in m.items()} for m in models] for t, models in home.CATALOG.items()},
        "modes": {t: [[n, f] for n, f in modes] for t, modes in home.TYPE_MODES.items()},
        "temps": home.TYPE_TEMP,
        "duty": home.DUTY_CYCLE,
        "capNames": home.CAP_NAMES,
        "boolCaps": home.BOOL_CAPS,
        "timerOptions": home.TIMER_OPTIONS,
        "colorPresets": home.COLOR_PRESETS,
        "scenes": home.SCENES,
        "alwaysOnGroups": sorted(home.ALWAYS_ON_GROUPS),
        "alwaysOnTypes": sorted(home.ALWAYS_ON_TYPES),
        "ecoShedTypes": home.ECO_SHED_TYPES,
        "washDurations": home.WASH_DURATIONS,
        "washPhases": home.WASH_PHASES,
        "defaultUsers": home.DEFAULT_USERS,
        "defaultPassword": home.DEFAULT_PASSWORD,
        "defaultRooms": home.DEFAULT_ROOMS,
        "seedUser": home.SEED_USER,
        "seedExtraRooms": home.SEED_EXTRA_ROOMS,
        "seedDevices": home.SEED_DEVICES,
        "planFloors": home.PLAN_FLOORS,
        "roomZones": home.ROOM_ZONES,
        "floors": home.FLOORS,
        "floorDefaultPos": home.FLOOR_DEFAULT_POS,
        "const": {
            "BATTERY_CAPACITY_WH": home.BATTERY_CAPACITY_WH, "SOLAR_PEAK_W": home.SOLAR_PEAK_W,
            "MAX_CHARGE_W": home.MAX_CHARGE_W, "BASE_LOAD_W": home.BASE_LOAD_W,
            "BATTERY_RESERVE": home.BATTERY_RESERVE, "GRID_VOLTAGE": home.GRID_VOLTAGE,
            "KETTLE_SPEEDUP": home.KETTLE_SPEEDUP, "ROOM_TEMP": home.ROOM_TEMP,
            "MIN_KETTLE_WATER_ML": home.MIN_KETTLE_WATER_ML,
            "VAC_CLEAN_MIN": home.VAC_CLEAN_MIN, "VAC_RETURN_MIN": home.VAC_RETURN_MIN,
            "VAC_DRAIN": home.VAC_DRAIN, "VAC_CHARGE": home.VAC_CHARGE, "VAC_LOW_BATTERY": home.VAC_LOW_BATTERY,
            "DEFAULT_TARIFF_KZT": home.DEFAULT_TARIFF_KZT, "CO2_KG_PER_KWH": home.CO2_KG_PER_KWH,
            "CO2_PER_TREE_KG": home.CO2_PER_TREE_KG, "ECO_OFF_LEVEL": home.ECO_OFF_LEVEL,
            "ECO_RESTORE_LEVEL": home.ECO_RESTORE_LEVEL, "SOLAR_ONLY_MIN_LEVEL": home.SOLAR_ONLY_MIN_LEVEL,
            "EV_MIN_POWER": home.EV_MIN_POWER,
        },
        "simSpeeds": home.SIM_SPEEDS,
    }
    with open(os.path.join(WEB, "data.js"), "w", encoding="utf-8") as f:
        f.write("// Сгенерировано web/tools/export_web_assets.py из home.py - не редактировать вручную\n")
        f.write("window.HOME_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n")


def export_scenes():
    """Сцены комнат для камер - те же, что рисует настольная версия (день / ночь / ИК)."""
    out_dir = os.path.join(WEB, "img", "scenes")
    for kind, painter_fn in home.SCENE_PAINTERS.items():
        for variant in ("day", "night"):
            pix = QPixmap(home.SCENE_W, home.SCENE_H)
            pix.fill(Qt.black)
            p = QPainter(pix)
            p.setRenderHint(QPainter.Antialiasing)
            painter_fn(p, home.SCENE_W, home.SCENE_H, variant == "night")
            p.end()
            small = pix.scaled(1600, 600, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            small.save(os.path.join(out_dir, f"{kind}_{variant}.jpg"), "JPG", 78)
            if variant == "night":
                ir = QPixmap.fromImage(small.toImage().convertToFormat(QImage.Format_Grayscale8))
                p = QPainter(ir)
                p.fillRect(ir.rect(), QColor(255, 255, 255, 45))
                p.end()
                ir.save(os.path.join(out_dir, f"{kind}_ir.jpg"), "JPG", 78)


def export_plans():
    for _, _, file_name in home.PLAN_FLOORS:
        src = os.path.join(ROOT, file_name)
        img = QImage(src)
        img = img.scaledToWidth(1100, Qt.SmoothTransformation)
        img.save(os.path.join(WEB, "img", file_name.replace(".png", ".jpg")), "JPG", 85)


def draw_icon(size, path, maskable=False):
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 512
    bg = QLinearGradient(0, 0, size, size)
    bg.setColorAt(0, QColor("#2d5f8f"))
    bg.setColorAt(1, QColor("#6f9fc6"))
    p.setPen(Qt.NoPen)
    p.setBrush(bg)
    if maskable:
        p.drawRect(0, 0, size, size)
    else:
        p.drawRoundedRect(QRectF(0, 0, size, size), 110 * s, 110 * s)
    # солнце
    sun = QPointF(360 * s, 150 * s)
    glow = QRadialGradient(sun, 110 * s)
    glow.setColorAt(0, QColor(255, 224, 102, 230))
    glow.setColorAt(1, QColor(255, 224, 102, 0))
    p.setBrush(glow)
    p.drawEllipse(sun, 110 * s, 110 * s)
    p.setBrush(QColor("#ffd34d"))
    p.drawEllipse(sun, 52 * s, 52 * s)
    # домик
    house = QPainterPath()
    house.moveTo(256 * s, 150 * s)
    house.lineTo(420 * s, 290 * s)
    house.lineTo(92 * s, 290 * s)
    house.closeSubpath()
    p.setBrush(QColor("#ffffff"))
    p.drawPath(house)
    p.drawRoundedRect(QRectF(130 * s, 270 * s, 252 * s, 150 * s), 14 * s, 14 * s)
    # солнечная панель на крыше
    p.setBrush(QColor("#1d3d6e"))
    panel = QPainterPath()
    panel.moveTo(276 * s, 185 * s)
    panel.lineTo(372 * s, 266 * s)
    panel.lineTo(330 * s, 266 * s)
    panel.lineTo(250 * s, 200 * s)
    panel.closeSubpath()
    p.drawPath(panel)
    # дверь и окно
    p.setBrush(QColor("#00b96b"))
    p.drawRoundedRect(QRectF(226 * s, 330 * s, 60 * s, 90 * s), 8 * s, 8 * s)
    p.setBrush(QColor("#9ecbe6"))
    p.drawRoundedRect(QRectF(160 * s, 310 * s, 46 * s, 46 * s), 6 * s, 6 * s)
    p.drawRoundedRect(QRectF(306 * s, 310 * s, 46 * s, 46 * s), 6 * s, 6 * s)
    p.end()
    pix.save(path, "PNG")


if __name__ == "__main__":
    export_data()
    export_scenes()
    export_plans()
    icons = os.path.join(WEB, "icons")
    draw_icon(192, os.path.join(icons, "icon-192.png"))
    draw_icon(512, os.path.join(icons, "icon-512.png"))
    draw_icon(512, os.path.join(icons, "icon-maskable-512.png"), maskable=True)
    draw_icon(180, os.path.join(icons, "apple-touch-icon.png"), maskable=True)
    print("web assets exported")
