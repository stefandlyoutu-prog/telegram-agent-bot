"""Партнёры и задания. Ссылки подставляются из .env или data/work_links.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from work_bot.config import ORACLE_BOT_USERNAME, WORKER_SHARE

_LINKS_FILE = Path(__file__).resolve().parents[1] / "data" / "work_links.json"


@dataclass(frozen=True)
class Partner:
    slug: str
    title: str
    emoji: str
    desc: str


@dataclass(frozen=True)
class Task:
    id: str
    partner_slug: str
    title: str
    steps: str
    proof_hint: str
    admin_reward_rub: int
    proof_type: str  # photo | photo_text | screenshot
    ref_env_key: str
    auto_pick: bool = True


PARTNERS: list[Partner] = [
    Partner("yandex_browser", "Яндекс Браузер", "🌐", "Установка браузера по партнёрской ссылке"),
    Partner("yandex_distribution", "Яндекс Дистрибуция", "📣", "Подключение рекламы / Маркета"),
    Partner("ozon", "Ozon", "🛒", "Установка приложения и первый заказ"),
    Partner("yandex_eda", "Яндекс Еда", "🍔", "Приведи курьера или установи приложение"),
    Partner("our_projects", "Наши проекты", "🔮", "Подписчик с оплатой в Оракул / другие боты"),
    Partner("cpa_banks", "Банки и карты", "💳", "CPA: оформление карты / кредита"),
    Partner("osago", "ОСАГО", "🚗", "Оформление полиса по вашей ссылке"),
]


def _worker_pay(admin_rub: int) -> int:
    return max(1, int(round(admin_rub * WORKER_SHARE)))


def _default_tasks() -> list[Task]:
    oracle = f"https://t.me/{ORACLE_BOT_USERNAME}?start=wrk_{{worker_id}}"
    return [
        Task(
            id="yandex_browser_install",
            partner_slug="yandex_browser",
            title="Установить Яндекс Браузер",
            steps=(
                "1. Перейди по ссылке ниже\n"
                "2. Скачай и установи Яндекс Браузер\n"
                "3. Открой браузер один раз\n"
                "4. Сделай скрин главного экрана / экрана «Браузер установлен»\n"
                "5. Нажми «Сдать отчёт» и пришли фото"
            ),
            proof_hint="Скрин установленного Яндекс Браузера",
            admin_reward_rub=600,
            proof_type="photo",
            ref_env_key="WORK_LINK_YANDEX_BROWSER",
        ),
        Task(
            id="yandex_dist_client",
            partner_slug="yandex_distribution",
            title="Подключить клиента в Дистрибуции",
            steps=(
                "1. Расскажи знакомому бизнесу про Яндекс Директ / Маркет\n"
                "2. Отправь ему свою реферальную ссылку\n"
                "3. Когда клиент подключится — скрин из кабинета партнёра\n"
                "4. Сдай отчёт с фото"
            ),
            proof_hint="Скрин из кабинета: новый подключённый клиент",
            admin_reward_rub=3000,
            proof_type="photo",
            ref_env_key="WORK_LINK_YANDEX_DIST",
        ),
        Task(
            id="ozon_install_order",
            partner_slug="ozon",
            title="Ozon: установка + первый заказ",
            steps=(
                "1. Перейди по ссылке Ozon Blogger\n"
                "2. Установи приложение Ozon (если ещё нет)\n"
                "3. Сделай первый заказ от 500 ₽\n"
                "4. Скрин заказа «Оформлен» + скрин установленного приложения"
            ),
            proof_hint="Два скрина: приложение + заказ",
            admin_reward_rub=500,
            proof_type="photo",
            ref_env_key="WORK_LINK_OZON",
        ),
        Task(
            id="yandex_eda_courier",
            partner_slug="yandex_eda",
            title="Приведи курьера Яндекс Еда",
            steps=(
                "1. Отправь другу ссылку на регистрацию курьера\n"
                "2. Друг должен пройти регистрацию и выйти на смену\n"
                "3. Скрин из реф. кабинета: курьер активен"
            ),
            proof_hint="Скрин кабинета: курьер принят",
            admin_reward_rub=5000,
            proof_type="photo",
            ref_env_key="WORK_LINK_YANDEX_EDA",
        ),
        Task(
            id="oracle_paid_sub",
            partner_slug="our_projects",
            title="Подписчик Оракул с оплатой",
            steps=(
                "1. Отправь другу ссылку на @MOracul_bot\n"
                "2. Друг должен оплатить Premium или Stars (любая оплата)\n"
                "3. Скрин переписки / оплаты (без личных данных друга — замажь)\n"
                "4. Напиши username друга в отчёте"
            ),
            proof_hint="Скрин оплаты + @username друга",
            admin_reward_rub=500,
            proof_type="photo_text",
            ref_env_key="WORK_LINK_ORACLE",
            auto_pick=True,
        ),
        Task(
            id="oracle_channel_sub",
            partner_slug="our_projects",
            title="Подписчик канала → оплата в боте",
            steps=(
                "1. Приведи человека в наш канал (гороскоп / аура)\n"
                "2. Он переходит в бота и совершает оплату\n"
                "3. Скрин: подписка на канал + оплата в боте"
            ),
            proof_hint="Подписка + оплата",
            admin_reward_rub=500,
            proof_type="photo",
            ref_env_key="WORK_LINK_CHANNEL",
        ),
        Task(
            id="bank_card_cpa",
            partner_slug="cpa_banks",
            title="Оформление дебетовой карты",
            steps=(
                "1. Перейди по CPA-ссылке банка\n"
                "2. Заполни заявку на карту (сам или помоги знакомому)\n"
                "3. Скрин «Заявка одобрена» / карта активирована"
            ),
            proof_hint="Скрин одобрения из банка / CPA-кабинета",
            admin_reward_rub=2000,
            proof_type="photo",
            ref_env_key="WORK_LINK_BANK_CPA",
        ),
        Task(
            id="osago_policy",
            partner_slug="osago",
            title="Оформление ОСАГО",
            steps=(
                "1. Отправь ссылку на оформление ОСАГО\n"
                "2. Клиент оформляет полис\n"
                "3. Скрин из CPA-кабинета: конверсия / оплаченный полис"
            ),
            proof_hint="Скрин конверсии в CPA",
            admin_reward_rub=1500,
            proof_type="photo",
            ref_env_key="WORK_LINK_OSAGO",
        ),
        Task(
            id="watch_ads_install",
            partner_slug="our_projects",
            title="Установка приложения рекламодателя",
            steps=(
                "1. Получи ссылку на задание\n"
                "2. Установи приложение / пройди целевое действие\n"
                "3. Скрин выполнения"
            ),
            proof_hint="Скрин «Готово» в задании",
            admin_reward_rub=200,
            proof_type="photo",
            ref_env_key="WORK_LINK_MICRO_CPA",
            auto_pick=True,
        ),
    ]


TASKS: list[Task] = _default_tasks()


def _load_file_links() -> dict[str, str]:
    if not _LINKS_FILE.is_file():
        return {}
    try:
        data = json.loads(_LINKS_FILE.read_text(encoding="utf-8"))
        return {k: str(v).strip() for k, v in data.items() if v}
    except (json.JSONDecodeError, OSError):
        return {}


def ref_link(task: Task, worker_id: int = 0) -> str:
    """Реферальная ссылка: env → файл → плейсхолдер."""
    env_val = os.getenv(task.ref_env_key, "").strip()
    if env_val:
        return env_val.replace("{worker_id}", str(worker_id))
    file_links = _load_file_links()
    if task.ref_env_key in file_links:
        return file_links[task.ref_env_key].replace("{worker_id}", str(worker_id))
    if task.partner_slug == "our_projects" and "ORACLE" in task.ref_env_key:
        return f"https://t.me/{ORACLE_BOT_USERNAME}?start=wrk_{worker_id}"
    return ""


def partner_by_slug(slug: str) -> Partner | None:
    return next((p for p in PARTNERS if p.slug == slug), None)


def task_by_id(task_id: str) -> Task | None:
    return next((t for t in TASKS if t.id == task_id), None)


def tasks_for_partner(slug: str) -> list[Task]:
    return [t for t in TASKS if t.partner_slug == slug]


def auto_tasks() -> list[Task]:
    return [t for t in TASKS if t.auto_pick]


def task_display(task: Task) -> dict[str, Any]:
    worker_rub = _worker_pay(task.admin_reward_rub)
    return {
        "id": task.id,
        "title": task.title,
        "partner": task.partner_slug,
        "worker_reward_rub": worker_rub,
        "admin_reward_rub": task.admin_reward_rub,
        "steps": task.steps,
        "proof_hint": task.proof_hint,
    }
