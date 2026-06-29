"""Эксклюзив: Хронально-Векторная Диагностика (ХВД)."""

from oracle_bot.exclusive_hvd.calculator import calculate, HVDProfile
from oracle_bot.exclusive_hvd.report import build_report_parts, build_teaser

__all__ = ["calculate", "HVDProfile", "build_report_parts", "build_teaser"]
