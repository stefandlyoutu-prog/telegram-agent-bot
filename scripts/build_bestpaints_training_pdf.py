#!/usr/bin/env python3
"""Обучающая презентация BestPaints: скриншоты → слайды 16:9 → PDF.

  .venv/bin/python scripts/build_bestpaints_training_pdf.py [--capture]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHOTS = ROOT / "data/bestpaints_training/shots"
SLIDES = ROOT / "data/bestpaints_training/slides"
OUT_PDF = ROOT / "oracle_bot/static/bestpaints/docs/BestPaints_Obuchenie.pdf"
FONT_REG = ROOT / "oracle_bot/assets/fonts/DejaVuSans.ttf"
FONT_BOLD = ROOT / "oracle_bot/assets/fonts/DejaVuSans-Bold.ttf"
W, H = 1920, 1080

SCENES = [
    (None, "BestPaints Survey + CRM",
     "Обучение продукту от и до\n\nКабинет: moracul.ru/bestpaints\nЛогин: bestpaints\nПароль: ZamerBp2026!\n\nБот: @BestPaints_Zamerbot\nГруппы: BP Ops · BP Подписанные"),
    ("01_login.png", "Вход в кабинет",
     "1. Откройте moracul.ru/bestpaints\n2. Логин bestpaints\n3. Пароль ZamerBp2026!\n4. Нажмите «Войти»\n\nПосле входа — список CRM-сделок и локальные замеры."),
    ("02_home.png", "Главный экран",
     "Сверху: CRM · сделки замеров (воронка, статусы, SMS/TG).\nСнизу: локальные замеры (офлайн-конструктор).\n\nКнопка «+ Сделка» — создать сделку в вебе.\nЛидоруб обычно создаёт через Telegram /zamer."),
    ("03_crm_create.png", "Создание сделки",
     "Поля:\n• Название сделки (как в вашей CRM)\n• Квалификация\n• Адрес · дата замера\n• Клиент / Лидоруб\n\nНазначение замерщика — из графика на дату.\nЕсли график пуст — статус «Создана»."),
    ("04_crm_detail.png", "Карточка сделки — статусы",
     "Замерщик по порядку:\n1. Взял в работу\n2. Выезд подтверждён\n3. На адресе · начинаю замер\n4. Конструктор / смета\n5. Заключил / Не заключил\n\nКаждый шаг уходит в группу BP Ops."),
    ("05_crm_admin.png", "Исправить / удалить / вернуть",
     "Блок «Исправить статус / удалить»:\n• сменить статус вручную\n• Вернуть в работу\n• Удалить сделку\n\nЕсли нажали не ту кнопку — здесь правите."),
    ("06_step_project.png", "Замер: шаг «Проект»",
     "Данные клиента и объекта.\nЕсли сделка из CRM — часть полей уже заполнена.\nИз CRM конструктор стартует со шага «Строение»."),
    ("07_step_building.png", "Шаг «Строение»",
     "Тип строения, зоны (фасад/интерьер),\nматериал, крыша.\nНесколько строений на одном участке — вкладками."),
    ("08_step_tech.png", "Конструктор ЛКМ",
     "Состояние дома → технология 1–5 → состав.\n12 составов: ADLER, G-Nature, OSMO, Россия, WOLMAN.\nНа карточке: веер, гарантия, цены за м², сумма."),
    ("09_step_estimate.png", "Смета и договор",
     "Итог, PDF, договорные поля.\nПосле выезда: «Заключил» → чек-лист + чат «Подписанные».\n«Не заключил» → менеджеру из графика (защита ТЗ)."),
    (None, "Telegram: кто что жмёт",
     "Лидоруб: /zamer (сделка + аудио)\nАдмин: /grafik, /grafik_add, /bp_staff\n\nГруппа BP Ops — лента статусов\nГруппа BP Подписанные — только договоры\n\nSMS — когда подключим шлюз (сейчас stub)."),
    (None, "Чек-лист первого дня",
     "□ Войти в кабинет\n□ Бот в группах + /chatid\n□ /grafik_add на сегодня\n□ /zamer тестовая сделка\n□ Пройти статусы до «на адресе»\n□ Открыть конструктор ЛКМ\n□ Проверить Ops / Подписанные"),
]


def capture():
    from playwright.sync_api import sync_playwright

    OUT = SHOTS
    OUT.mkdir(parents=True, exist_ok=True)
    BASE = "https://moracul.ru/bestpaints"
    VIEW = {"width": 390, "height": 844}

    def shot(page, name):
        path = OUT / f"{name}.png"
        page.screenshot(path=str(path), full_page=False)
        print("shot", path.name)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport=VIEW, device_scale_factor=2).new_page()
        page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
        shot(page, "01_login")
        page.fill('input[name="username"], input[type="text"]', "bestpaints")
        page.fill('input[name="password"], input[type="password"]', "ZamerBp2026!")
        page.click('button[type="submit"], button:has-text("Войти")')
        page.wait_for_url("**/bestpaints/**", timeout=30000)
        page.wait_for_timeout(1500)
        shot(page, "02_home")
        btn = page.locator("#crm-toggle-create").first
        if btn.count():
            btn.click()
            page.wait_for_timeout(800)
        shot(page, "03_crm_create")
        open_btn = page.locator("[data-crm-open]").first
        if open_btn.count():
            open_btn.click()
            page.wait_for_timeout(1200)
            shot(page, "04_crm_detail")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(400)
            shot(page, "05_crm_admin")
            back = page.locator("#crm-back").first
            if back.count():
                back.click()
                page.wait_for_timeout(800)
        else:
            shot(page, "04_crm_detail")
            shot(page, "05_crm_admin")
        new_btn = page.locator("#btn-new").first
        if new_btn.count():
            new_btn.click()
            page.wait_for_timeout(1200)
            shot(page, "06_step_project")
            for i, name in [(1, "07_step_building"), (5, "08_step_tech"), (7, "09_step_estimate")]:
                page.evaluate(f"window.__BP__ && window.__BP__.setStep({i})")
                page.wait_for_timeout(900)
                shot(page, name)
        browser.close()


def build_pdf():
    from PIL import Image, ImageDraw, ImageFont
    from fpdf import FPDF

    def font(path, size):
        return ImageFont.truetype(str(path), size=size)

    def wrap(draw, text, fnt, max_w):
        lines = []
        for para in text.split("\n"):
            if not para:
                lines.append("")
                continue
            cur = ""
            for w in para.split(" "):
                trial = (cur + " " + w).strip()
                if draw.textlength(trial, font=fnt) <= max_w:
                    cur = trial
                else:
                    if cur:
                        lines.append(cur)
                    cur = w
            if cur:
                lines.append(cur)
        return lines

    def compose(shot_name, title, body, out_path: Path):
        bg = Image.new("RGB", (W, H), (15, 20, 18))
        draw = ImageDraw.Draw(bg)
        draw.rectangle([0, 0, 14, H], fill=(196, 163, 90))
        f_title = font(FONT_BOLD, 44)
        f_body = font(FONT_REG, 28)
        f_small = font(FONT_REG, 20)
        phone_w, phone_h = 420, 860
        px, py = 100, (H - phone_h) // 2
        draw.rounded_rectangle([px - 10, py - 10, px + phone_w + 10, py + phone_h + 10], radius=40, fill=(28, 36, 32))
        shot_path = SHOTS / shot_name if shot_name else None
        if shot_path and shot_path.exists():
            img = Image.open(shot_path).convert("RGB").resize((phone_w, phone_h), Image.Resampling.LANCZOS)
            mask = Image.new("L", (phone_w, phone_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, phone_w, phone_h], radius=30, fill=255)
            bg.paste(img, (px, py), mask)
        else:
            draw.rounded_rectangle([px, py, px + phone_w, py + phone_h], radius=30, fill=(22, 28, 25))
            draw.text((px + 40, py + phone_h // 2 - 20), "BestPaints", fill=(143, 191, 122), font=f_title)
        tx = px + phone_w + 80
        tw = W - tx - 80
        draw.text((tx, 80), title, fill=(232, 240, 234), font=f_title)
        y = 160
        for line in wrap(draw, body, f_body, tw):
            draw.text((tx, y), line, fill=(180, 195, 185), font=f_body)
            y += 38
            if y > H - 80:
                break
        draw.text((tx, H - 50), "BestPaints · обучение", fill=(100, 120, 110), font=f_small)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        bg.save(out_path, "PNG", optimize=True)

    SLIDES.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (shot, title, body) in enumerate(SCENES, 1):
        path = SLIDES / f"slide_{i:02d}.png"
        compose(shot, title, body, path)
        paths.append(path)
        print("slide", path.name)

    pdf = FPDF(orientation="L", unit="mm", format=(297, 167.0625))
    for sp in paths:
        pdf.add_page()
        pdf.image(str(sp), x=0, y=0, w=297, h=167.0625)
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT_PDF))
    print("PDF", OUT_PDF, OUT_PDF.stat().st_size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", action="store_true")
    args = ap.parse_args()
    if args.capture:
        capture()
    build_pdf()


if __name__ == "__main__":
    main()
