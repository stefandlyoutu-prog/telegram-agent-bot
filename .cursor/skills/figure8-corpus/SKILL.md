---
name: figure8-corpus
description: >-
  Генерация и правка корпуса-трубки «8» (лемниската) для Bambu: две половинки,
  канал Ø40 мм, over/under в центре без смешивания. Используй при правке
  figure8_tube_mesh, hybrid_v3_figure8_corpus, сборке ZIP/3MF, ошибках слайсера
  (общая чаша в центре, разрыв канала).
---

# Корпус-трубка «8» (PETG, Bambu)

## Эталон (storyboard)

Референс: `~/Downloads/storyboard 3.html` — силиконовая трубка «∞» с жидкостью по кругу.

**В этом проекте:** корпус **сам является трубкой** (монолит PETG), не канавка под вставку.

## Жёсткие требования (не ослаблять)

| Параметр | Значение |
|----------|----------|
| Деталей в архиве | **2**: `fig8_body_lower`, `fig8_body_upper` |
| Ширина канала (Ø) | **≥ 40 мм** → `tube_bore_radius_mm = 20` |
| Высота каждой половинки | **≥ 40 мм** → `half_height_mm = 40` |
| Стенка | **≥ 5 мм** (`wall_mm`) — под шип-паз |
| Контур воды | **один замкнутый** «∞», одно направление |
| Центр (0,0) | **без общей чаши** — потоки **не смешиваются** |
| Перекрёсток | **over/under** по Z + мосты **±X**, сплошной **остров** в (0,0) |
| Подставка / пьезо | **не включать** в print pack |

## Ключевые файлы

- `bot/services/figure8_tube_mesh.py` — геометрия, verify, sweep (manifold3d)
- `bot/services/hybrid_v3_figure8_corpus.py` — spec, pack, PDF, part mesh
- `scripts/build_v3_print_pack.py` — локальная сборка ZIP в `~/Downloads/`

Текущий pack: `figure8-corpus-v13-bridge-cross-40mm-bambu-pack.zip`

## Правильная геометрия (v12+)

### Контур канала

Использовать **`fig8_closed_bridge_path_3d`** — две петли + мосты на `x = ±_bridge_x_mm`, **не** самопересечение лемнискаты через (0,0).

```python
# ✅ Правильно: мосты ±X, петли fig8_lobes_bridged
path = fig8_closed_bridge_path_3d(lemniscate_a, r_bore=20, half_h=40)

# ❌ Запрещено: одна 2D-лемниската, вырезанная на всю высоту
void = extrude_polygon(bore_blob, height=half_h)  # → чаша в центре

# ❌ Запрещено: fig8_centerline(t) через (0,0) как единственный 3D-путь
# → в слайсере круглая «ванна» где сходятся обе петли
```

### Корпус = труба

Строить через **`_build_tube_corpus_half_manifold`**:

1. Sweep круглой трубы по 3D-пути (manifold3d)
2. Обрезка половинки по z=0
3. **`hub`** — цилиндр в (0,0), закрывает остаток пересечения объёмов
4. Мосты идут **вдоль X** (`bridge_via_x`), не диагональю через центр

### Разрез z=0

- Печать: **швом z=0 на стол**
- Шип-паз: `add_seam_tongue_groove` после `build_figure8_tube_shell`

## Workflow агента

1. Прочитать storyboard / этот скилл — не менять требования без запроса пользователя.
2. Править только `figure8_tube_mesh.py` / `hybrid_v3_figure8_corpus.py` (минимальный diff).
3. Собрать и проверить:

```bash
cd /Users/polzovatel/Projects/telegram-agent-bot
.venv/bin/python3 scripts/validate_figure8_corpus.py   # быстро: только verify
.venv/bin/python3 scripts/build_v3_print_pack.py       # полный ZIP
```

4. Убедиться, что проходят:
   - `verify_figure8_dimensions`
   - `verify_figure8_channel` (в т.ч. **остров в (0,0)**)
   - `verify_lanes_no_plan_crossing`
5. При необходимости: `.venv/bin/python3 -c "import asyncio; from scripts.verify_bot import test_v3_print_pack; asyncio.run(test_v3_print_pack())"`

**Не отдавать ZIP**, если `build_v3_print_pack` или `validate_figure8_corpus.py` падают.

Обязательно проверять **финальные** детали (`build_v3_part_mesh` с шип-пазом): `verify_figure8_part_mesh` — STL > 100 KB, объём > 10000 мм³.

## Приёмка в Bambu Studio (вид сверху открытой половинки)

| ✅ OK | ❌ Брак |
|-------|--------|
| Круглое сечение канала (~40 мм) | Плоский прямоугольный «карман» |
| В центре **пластиковый остров** | Одна **круглая чаша**, куда сходятся обе петли |
| Два рукава подходят слева/справа | Треугольные мёртвые карманы без связи |
| Over/under: разные ярусы у центра | Оба канала открыты на одной плоскости z |

## Типичные регрессии (2 дня ошибок)

1. **Чаша в центре** — путь через (0,0) или 2D-extrude `bore_blob` → вернуть bridge path + hub.
2. **Разрыв контура** — `t_eps` слишком большой у `fig8_lobes` → использовать `fig8_lobes_bridged` + `_VOID_LOBE_EPS`.
3. **Hub режет мост** — hub_r слишком большой или мост диагональный → `bridge_via_x`, hub_r ≈ `min(bx*0.72, r_bore*0.58)`.
4. **Высота < 40 мм** — ось трубы на z=0 при r=20 → оси на z=±half_h/2.
5. **Плоский вырез вместо трубы** — забыли manifold sweep → `_build_tube_corpus_half_manifold`.

## Spec по умолчанию

`Figure8CorpusSpec`: `lemniscate_a_mm=78`, `tube_bore_radius_mm=20`, `wall_mm=5`, `half_height_mm=40`.

## Коммуникация с пользователем

Кратко на русском: что было не так в слайсере, что изменено, путь к новому ZIP, как проверить центр сверху.
