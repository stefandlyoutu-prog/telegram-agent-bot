/** Виды строений на участке */
export const OBJECT_KINDS = [
  {
    id: "house",
    title: "Дом",
    hint: "Жилой дом, основной объём",
    wallPreset: "box4",
  },
  {
    id: "dacha",
    title: "Дача",
    hint: "Сезонный дом, часто проще и ниже",
    wallPreset: "box4",
  },
  {
    id: "bath",
    title: "Баня",
    hint: "Сруб/брус, часто с террасой",
    wallPreset: "box4",
  },
  {
    id: "garage",
    title: "Гараж",
    hint: "Отдельно или пристрой; ворота = большой проём",
    wallPreset: "box4",
  },
  {
    id: "shed",
    title: "Хозблок / сарай",
    hint: "Небольшой объём",
    wallPreset: "box4",
  },
  {
    id: "terrace",
    title: "Терраса / веранда",
    hint: "Стойки, ограждения, потолок, пол",
    wallPreset: "open",
  },
  {
    id: "fence",
    title: "Забор",
    hint: "Длина × высота пролётов, столбы отдельно",
    wallPreset: "fence",
  },
  {
    id: "other",
    title: "Другое",
    hint: "Беседка, навес, пиломатериалы…",
    wallPreset: "box4",
  },
];

export const ROOF_TYPES = [
  {
    id: "gable",
    title: "Двускатная",
    tip: "На торцах часто фронтон: длина × высота до свеса + треугольник до конька.",
  },
  {
    id: "broken",
    title: "Ломаная (мансардная)",
    tip: "Стену делите на пояса или считайте трапецией: две высоты (слева/справа или низ/верх).",
  },
  {
    id: "hip",
    title: "Вальмовая / шатровая",
    tip: "Фронтонов может не быть. Высота стены обычно ровная до свеса; ендовы и торцы — отдельно.",
  },
  {
    id: "shed",
    title: "Односкатная / плоская",
    tip: "Высоты по углам разные — используйте форму «трапеция» (средняя высота).",
  },
  {
    id: "complex",
    title: "Сложная / многоуровневая",
    tip: "Режьте на простые куски: каждая плоскость = отдельная «сторона».",
  },
];

export const WALL_SHAPES = [
  {
    id: "rect",
    title: "Прямоугольник",
    hint: "Длина × высота",
  },
  {
    id: "gable",
    title: "С фронтоном",
    hint: "Прямоугольник до свеса + треугольник до конька",
  },
  {
    id: "trap",
    title: "Трапеция / ср. высота",
    hint: "Длина × (H₁ + H₂) / 2 — ломаная, односкат",
  },
  {
    id: "custom",
    title: "Своя площадь",
    hint: "Уже посчитали вручную / по чертежу",
  },
];

export const WORK_ZONES = [
  { id: "facade", title: "Снаружи (фасад)", hint: "Стены, подшива, торцы, шов" },
  { id: "interior", title: "Внутри (интерьер)", hint: "Стены комнат, потолки, полы" },
];

/** Пресеты сторон под тип объекта */
function blankWall(u, label, zone = "facade", note = "") {
  return {
    id: u(),
    label,
    shape: "rect",
    length: "",
    height: "",
    height2: "",
    ridge: "",
    areaManual: "",
    zone,
    note,
    material: "",
    condition: "",
    coatingWant: "",
    photos: [],
  };
}

export function wallsForPreset(preset, uidFn) {
  const u = uidFn;
  if (preset === "fence") {
    return [blankWall(u, "Пролёт 1"), blankWall(u, "Пролёт 2")];
  }
  if (preset === "open") {
    return [
      blankWall(u, "Потолок террасы", "facade", "или занесите в «потолки»"),
      blankWall(u, "Ограждение", "facade", "длина × высота перил"),
    ];
  }
  return [
    blankWall(u, "Главный фасад"),
    blankWall(u, "Правый фасад"),
    blankWall(u, "Задний фасад"),
    blankWall(u, "Левый фасад"),
  ];
}
