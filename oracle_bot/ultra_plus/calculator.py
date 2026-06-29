"""Расчёт Матрицы Судьбы (22 аркана) по дате рождения."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


def reduce22(n: int) -> int:
    while n > 22:
        n = sum(int(d) for d in str(abs(n)))
    return n


def digit_sum(n: int) -> int:
    return sum(int(d) for d in str(abs(n)))


def year_arcana(year: int) -> int:
    return reduce22(digit_sum(year))


@dataclass
class MatrixProfile:
    name: str
    birth: date
    A: int  # день
    B: int  # месяц
    C: int  # год
    D: int
    E: int  # центр
    AB: int
    AC: int
    BD: int
    CD: int
    AE: int
    BE: int
    CE: int
    DE: int
    AD: int
    BC: int
    day_digits: int = 0
    extras: dict[str, int] = field(default_factory=dict)

    @property
    def age(self) -> int:
        today = date.today()
        return today.year - self.birth.year - (
            (today.month, today.day) < (self.birth.month, self.birth.day)
        )


def calculate(name: str, birth: date) -> MatrixProfile:
    if birth.year < 1900 or birth.year > 2099:
        raise ValueError("Год рождения должен быть 1900–2099")

    A = reduce22(birth.day)
    B = birth.month
    C = year_arcana(birth.year)
    D = reduce22(A + B + C)
    E = reduce22(A + B + C + D)
    AB = reduce22(A + B)
    AC = reduce22(A + C)
    BD = reduce22(B + D)
    CD = reduce22(C + D)
    AE = reduce22(A + E)
    BE = reduce22(B + E)
    CE = reduce22(C + E)
    DE = reduce22(D + E)
    AD = reduce22(A + D)
    BC = reduce22(B + C)

    extras = {
        "BCD": reduce22(B + C + D),
        "ACD": reduce22(A + C + D),
        "ACE": reduce22(A + C + E),
        "BDE": reduce22(B + D + E),
        "DCE": reduce22(D + C + E),
        "EAB": reduce22(E + AB),
        "EAC": reduce22(E + AC),
        "B_plus_BD_plus_D": reduce22(B + BD + D),
    }

    return MatrixProfile(
        name=name.strip(),
        birth=birth,
        A=A,
        B=B,
        C=C,
        D=D,
        E=E,
        AB=AB,
        AC=AC,
        BD=BD,
        CD=CD,
        AE=AE,
        BE=BE,
        CE=CE,
        DE=DE,
        AD=AD,
        BC=BC,
        day_digits=reduce22(digit_sum(birth.day)),
        extras=extras,
    )


def section_numbers(profile: MatrixProfile) -> dict[str, list[int] | int | tuple[int, ...]]:
    """Ключи секций книги → номера арканов (проверено на образце 21.06.1994)."""
    x = profile.extras
    return {
        "personal": (profile.A, profile.B),
        "communication": profile.E,
        "talents_god": (profile.B, x["B_plus_BD_plus_D"], x["BCD"]),
        "talents_mother": (profile.BD, profile.B, x["B_plus_BD_plus_D"]),
        "talents_father": (profile.AB, profile.BD, x["DCE"]),
        "purpose_20_40": (profile.BD, profile.AC, x["EAB"]),
        "purpose_40_60": (x["EAB"], profile.BD),
        "purpose_general": profile.day_digits,
        "money_direction": x["EAC"],
        "money_success": (profile.day_digits, profile.C, profile.CE, x["DCE"]),
        "sexuality": (profile.A, profile.BE, profile.CE),
        "past_life": (profile.AB, profile.AC, profile.AD),
        "parents": (profile.A, profile.AE, profile.AD),
        "lineage_male": (profile.A, profile.AC, profile.C),
        "lineage_female": (profile.BD, profile.AC, x["EAB"]),
        "parent_wounds": (profile.A, profile.AE, profile.AD),
        "children": (profile.A, profile.AE, profile.AD),
        "relationships": (x["EAC"], profile.CE, profile.day_digits),
        "health_recommend": (profile.A, profile.B, profile.AB),
        "life_guide": (profile.E, profile.CD, profile.D),
        "year_forecast": (profile.C, profile.E, profile.CE),
    }


def program_channels(profile: MatrixProfile) -> list[tuple[str, tuple[int, int, int]]]:
    """Каналы матрицы → ключ программы 'a-b-c'."""
    p = profile
    x = p.extras
    channels = [
        ("vertical_right", (p.BD, p.B, x["B_plus_BD_plus_D"])),
        ("vertical_left", (p.AC, p.A, p.C)),
        ("horizontal_top", (p.A, p.AB, p.B)),
        ("horizontal_bottom", (p.C, p.CD, p.D)),
        ("sky", (p.A, p.AB, p.B)),
        ("earth", (p.C, p.CD, p.D)),
        ("male", (p.A, p.E, p.D)),
        ("female", (p.B, p.E, p.C)),
        ("diag_ad", (p.A, p.AD, p.D)),
        ("center_spread", (p.AB, p.E, x["EAB"])),
        ("karma_tail", (x["EAB"], p.AB, p.A)),
    ]
    out: list[tuple[str, tuple[int, int, int]]] = []
    for label, triple in channels:
        key = f"{triple[0]}-{triple[1]}-{triple[2]}"
        out.append((key, triple))
    return out
