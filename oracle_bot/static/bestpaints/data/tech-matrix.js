/** Матрица «Виды домов и технологии» + правила BestPaints (смета от 25.06.2026) */
export const TECHNOLOGIES = [
  {
    id: 1,
    short: "Мойка",
    title: "1. Очистка без шлифовки (мойка)",
    desc: "Очистка поверхности без шлифовки. Минимальная подготовка.",
  },
  {
    id: 2,
    short: "Лёгкая",
    title: "2. Лёгкая шлифовка",
    desc: "Ручная шлифовка губками. Удаляется только явно отслаивающееся покрытие / поднятый ворс.",
  },
  {
    id: 3,
    short: "1 проход",
    title: "3. Шлифовка в 1 проход",
    desc: "Эксцентриковая шлифмашина. Слабодержащееся покрытие / верхний слой древесины.",
  },
  {
    id: 4,
    short: "2 прохода",
    title: "4. Шлифовка в 2 прохода",
    desc: "Базовая подготовка. Полное удаление старого покрытия до древесины. Предлагаем первой.",
    isBase: true,
  },
  {
    id: 5,
    short: "2 прохода (окр.)",
    title: "5. Шлифовка в 2 прохода (ранее окрашенный / рубленый)",
    desc: "Как технология 4, для ранее окрашенных домов и рубленого бревна/лафета.",
  },
];

export const HOUSE_TYPES = [
  {
    id: "new",
    title: "Новый дом",
    hint: "Не окрашен, естественная древесина",
  },
  {
    id: "non_film",
    title: "Ранее окрашен (не плёнка)",
    hint: "Масло / водная пропитка, нет слоя краски",
  },
  {
    id: "film",
    title: "Ранее окрашен (плёнка)",
    hint: "Краска / лак / плёнкообразующий состав",
  },
];

export const CONDITIONS = [
  {
    id: "good",
    title: "Хорошее",
    byType: {
      new: "Чистая светлая поверхность, без синевы и потемнений",
      non_film: "Покрытие держится, не шелушится, нет оголённой древесины",
      film: "Нет шелушений, отслоений и участков оголённой древесины",
    },
  },
  {
    id: "medium",
    title: "Среднее",
    byType: {
      new: "Незначительная естественная серость",
      non_film: "Лёгкое шелушение местами, дерево нормальное, не серое/чёрное",
      film: "Небольшие шелушения, отслоения или участки оголённой древесины",
    },
  },
  {
    id: "bad",
    title: "Плохое",
    byType: {
      new: "Значительные потемнения, плесень, чернота (или рубленое бревно)",
      non_film: "Сильно шелушится, дерево серое/чёрное, видно повреждение",
      film: "Сильные отслоения, много оголённой древесины, потемнения",
    },
  },
];

/**
 * allowed: true | false
 * note: текст ограничений для замерщика
 * opacity: 'any' | 'opaque' | 'opaque_or_dark_semi' | 'restricted'
 */
const cell = (allowed, note, opacity = "any") => ({ allowed, note, opacity });

/** key: `${houseType}:${condition}` → techId → cell */
export const MATRIX = {
  "new:good": {
    1: cell(true, "Любые составы — укрывные и полупрозрачные"),
    2: cell(true, "Любые составы — укрывные и полупрозрачные"),
    3: cell(true, "Любые составы — укрывные и полупрозрачные"),
    4: cell(true, "Любые составы — укрывные и полупрозрачные"),
    5: cell(true, "Любые составы — укрывные и полупрозрачные"),
  },
  "new:medium": {
    1: cell(true, "Укрывные — все. Полупрозрачные — только тёмные цвета", "opaque_or_dark_semi"),
    2: cell(true, "Укрывные — все. Полупрозрачные — только тёмные цвета", "opaque_or_dark_semi"),
    3: cell(true, "Укрывные — все. Полупрозрачные — только тёмные цвета", "opaque_or_dark_semi"),
    4: cell(true, "Любые составы"),
    5: cell(true, "Любые составы"),
  },
  "new:bad": {
    1: cell(false, "Нельзя применять"),
    2: cell(false, "Нельзя применять"),
    3: cell(false, "Нельзя применять"),
    4: cell(true, "Любые составы (для рубленого — минимум 2 прохода)"),
    5: cell(true, "Любые составы"),
  },
  "non_film:good": {
    1: cell(true, "PULLEX COLOR любой цвет; укрывные масла / полупрозрачные — тот же цвет или темнее", "restricted"),
    2: cell(true, "PULLEX COLOR любой цвет; укрывные масла / полупрозрачные — тот же цвет или темнее", "restricted"),
    3: cell(true, "PULLEX COLOR любой цвет; укрывные масла / полупрозрачные — тот же цвет или темнее", "restricted"),
    4: cell(true, "Любые составы"),
    5: cell(true, "Любые составы"),
  },
  "non_film:medium": {
    1: cell(true, "PULLEX COLOR / укрывные масла тот же/темнее. Полупрозрачные — нельзя", "opaque"),
    2: cell(true, "PULLEX COLOR / укрывные масла тот же/темнее. Полупрозрачные — нельзя", "opaque"),
    3: cell(true, "Любые составы (с оговорками по цвету)"),
    4: cell(true, "Любые составы"),
    5: cell(true, "Любые составы"),
  },
  "non_film:bad": {
    1: cell(false, "Нельзя применять"),
    2: cell(false, "Нельзя применять"),
    3: cell(true, "Укрывные (тот же/темнее) / полупрозрачные тот же или темнее", "restricted"),
    4: cell(true, "Любые составы"),
    5: cell(true, "Любые составы"),
  },
  "film:good": {
    1: cell(true, "Только ADLER PULLEX COLOR (любой) или PLUS LASUR тот же/темнее", "restricted"),
    2: cell(true, "Только ADLER PULLEX COLOR (любой) или PLUS LASUR тот же/темнее", "restricted"),
    3: cell(true, "Только ADLER PULLEX COLOR", "opaque"),
    4: cell(true, "Любые составы"),
    5: cell(true, "Любые составы"),
  },
  "film:medium": {
    1: cell(false, "Нельзя применять"),
    2: cell(true, "Только ADLER PULLEX COLOR", "opaque"),
    3: cell(true, "Только ADLER PULLEX COLOR", "opaque"),
    4: cell(true, "Любые составы"),
    5: cell(true, "Любые составы"),
  },
  "film:bad": {
    1: cell(false, "Нельзя применять"),
    2: cell(false, "Нельзя применять"),
    3: cell(true, "Только ADLER PULLEX COLOR", "opaque"),
    4: cell(true, "Любые составы"),
    5: cell(true, "Любые составы"),
  },
};

export const FORBIDDEN = [
  "Полупрозрачный на укрывной без полного удаления старого покрытия",
  "Покраска на старое покрытие без теста на совместимость",
  "Интерьерные составы на фасад",
  "Смена цвета полупрозрачным без удаления старого (только тот же оттенок или темнее)",
  "Плёнкообразующее + полупрозрачный без полной шлифовки (техн. 4/5)",
  "Рубленое бревно / лафет — нельзя продавать 1 проход, минимум 2 прохода",
];

export const MATERIAL_OPTIONS = [
  { id: "beam", label: "Брус" },
  { id: "log", label: "Бревно (оцилиндровка)" },
  { id: "hand_log", label: "Рубленое бревно / лафет" },
  { id: "imit", label: "Имитация бруса / планкен" },
  { id: "block", label: "Блок-хаус" },
  { id: "board", label: "Доска / вагонка" },
  { id: "other", label: "Другое" },
];

/** Элементы как в конструкторе smeta-bestpaints.ru */
export const HOUSE_ELEMENTS = [
  { id: "walls", title: "Стены" },
  { id: "soffit", title: "Подшива" },
  { id: "fascia", title: "Лобовая доска" },
  { id: "posts", title: "Столбы" },
  { id: "terrace", title: "Терраса" },
  { id: "railings", title: "Ограждения/перила" },
  { id: "ceiling", title: "Потолок" },
  { id: "floor", title: "Пол" },
  { id: "stairs", title: "Лестница" },
  { id: "porch", title: "Крыльцо" },
  { id: "other", title: "Другое" },
];

export const ROUND_COEF = [
  { id: "1", label: "1.0 — брус / плоские стены", value: 1 },
  { id: "1.15", label: "1.15 — оцилиндровка", value: 1.15 },
  { id: "1.2", label: "1.2 — рубленое / сложный профиль", value: 1.2 },
  { id: "custom", label: "Свой коэффициент", value: null },
];

/** Рекомендации смет «с полки» при полупрозрачных */
export const SEMI_LADDER = [
  { brand: "WOLMAN", productIncludes: "Wolman", label: "Выгодный", tip: "Wolman Semi Transparent" },
  { brand: "ADLER", productIncludes: "3in1", label: "Средний", tip: "Adler Pullex 3in1" },
  { brand: "G-Nature", productIncludes: "280", label: "Подороже", tip: "G-Nature 280" },
  { brand: "OSMO", productIncludes: "Holzschutz", label: "Премиум", tip: "OSMO Holzschutz Öl-Lasur" },
];

export function getMatrixCell(houseType, condition, techId) {
  const row = MATRIX[`${houseType}:${condition}`];
  if (!row) return null;
  return row[techId] || null;
}

export function recommendTechs(houseType, condition, materialId) {
  const row = MATRIX[`${houseType}:${condition}`];
  if (!row) return [];
  let list = TECHNOLOGIES.map((t) => {
    const c = row[t.id];
    return {
      ...t,
      allowed: !!c?.allowed,
      note: c?.note || "",
      opacity: c?.opacity || "any",
    };
  }).filter((t) => t.allowed);

  // Рубленое — минимум 2 прохода
  if (materialId === "hand_log") {
    list = list.filter((t) => t.id >= 4);
  }

  // Для ранее окрашенных базовая = техн.5, для новых = 4
  const preferred = houseType === "new" ? 4 : 5;
  list.sort((a, b) => {
    if (a.id === preferred) return -1;
    if (b.id === preferred) return 1;
    return b.id - a.id;
  });
  return list;
}

export function defaultTechId(houseType, condition, materialId) {
  const rec = recommendTechs(houseType, condition, materialId);
  if (!rec.length) return null;
  const preferred = materialId === "hand_log" || houseType !== "new" ? 5 : 4;
  return rec.find((t) => t.id === preferred)?.id || rec[0].id;
}
