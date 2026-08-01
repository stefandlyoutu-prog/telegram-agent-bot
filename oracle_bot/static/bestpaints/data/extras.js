/**
 * Типовые доп.работы (из сметы ADLER / общие позиции).
 * Торцы, наличники/доборы, тёплый шов, водосток и отливы уже считаются
 * автоматически из замера стен (длины/площади по сторонам) и попадают
 * в смету сами — здесь их дублировать не нужно. Ниже только то, что
 * по стенам не считается: новые изделия, доп.демонтаж и разовые работы.
 */
export const EXTRA_WORKS = [
  {
    group: "Наличники / доборы",
    items: [
      { id: "trim_make_pine", name: "Изготовление наличников до 140 мм (хвоя)", unit: "пог.м", price: 1650 },
      { id: "trim_make_larch", name: "Изготовление наличников до 140 мм (лиственница)", unit: "пог.м", price: 1850 },
    ],
  },
  {
    group: "Подготовка швов",
    items: [
      { id: "caulk_remove", name: "Удаление конопатки", unit: "пог.м", price: 50 },
      { id: "seal_remove", name: "Удаление старого герметика", unit: "пог.м", price: 150 },
    ],
  },
  {
    group: "Прочее на объекте",
    items: [
      { id: "window_cover", name: "Укрытие окон пленкой", unit: "кв.м", price: 400 },
      { id: "plinth_cover", name: "Укрытие цоколя пленкой", unit: "пог.м", price: 200 },
      { id: "surface_cover", name: "Укрытие поверхности пленкой", unit: "кв.м", price: 100 },
      { id: "ac_cover", name: "Укрытие блоков кондиционера", unit: "шт", price: 1000 },
      { id: "cable", name: "Демонтаж/монтаж кабель-каналов", unit: "пог.м", price: 150 },
      { id: "lights", name: "Демонтаж/монтаж светильников", unit: "шт", price: 500 },
      { id: "garland", name: "Демонтаж/монтаж гирлянды", unit: "пог.м", price: 150 },
      { id: "radiator", name: "Демонтаж/монтаж батареи (радиатора)", unit: "шт", price: 1500 },
      { id: "antiseptic", name: "Антисептик Lignofix 1 слой", unit: "кв.м", price: 230 },
    ],
  },
  {
    group: "Доступ и высота",
    items: [
      { id: "scaffold_tower", name: "Вышка-тура (аренда, смена)", unit: "шт", price: 3500 },
      { id: "scaffold_full", name: "Леса строительные (комплект/месяц)", unit: "шт", price: 25000 },
      { id: "lift", name: "Подъёмник / люлька (смена)", unit: "шт", price: 12000 },
      { id: "ladder_tall", name: "Работа с высотных лестниц (надбавка)", unit: "кв.м", price: 150 },
    ],
  },
  {
    group: "Ремонт и подготовка",
    items: [
      { id: "board_replace", name: "Замена доски / элемента", unit: "пог.м", price: 800 },
      { id: "full_strip", name: "Полное снятие старого покрытия", unit: "кв.м", price: 450 },
      { id: "chimney_work", name: "Обход / подготовка дымохода", unit: "шт", price: 2500 },
    ],
  },
  {
    group: "Быт бригады",
    items: [
      { id: "cabin_near", name: "Бытовка до 80 км от МКАД (1 мес)", unit: "шт", price: 40000 },
      { id: "cabin_far", name: "Бытовка свыше 80 км от МКАД (1 мес)", unit: "шт", price: 45000 },
      { id: "toilet_near", name: "Биотуалет до 80 км от МКАД", unit: "шт", price: 12000 },
      { id: "toilet_far", name: "Биотуалет свыше 80 км от МКАД", unit: "шт", price: 16000 },
      { id: "trash_near", name: "Вывоз мусора до 80 км от МКАД", unit: "шт", price: 12000 },
      { id: "trash_far", name: "Вывоз мусора свыше 80 км от МКАД", unit: "шт", price: 16000 },
    ],
  },
];

export const ATTENTION_ELEMENTS = [
  { id: "lights", label: "Светильники", unit: "шт" },
  { id: "antennas", label: "Антенны", unit: "шт" },
  { id: "ac", label: "Кондиционеры", unit: "шт" },
  { id: "radiators", label: "Батареи / радиаторы", unit: "шт" },
  { id: "chimneys", label: "Дымоходы / трубы", unit: "шт" },
  { id: "wiring", label: "Внешняя проводка", unit: "м" },
  { id: "garlands", label: "Гирлянды", unit: "м" },
  { id: "decor", label: "Элементы декора", unit: "шт" },
  { id: "furniture", label: "Мебель у стен", unit: "шт" },
  { id: "cable_duct", label: "Кабель-канал", unit: "м" },
];

/** Быстрые флаги стороны — замерщик тапает на объекте */
export const WALL_FLAGS = [
  { id: "rot", label: "Гниль / ремонт" },
  { id: "peel", label: "Отслоение" },
  { id: "high", label: "Высота / леса" },
  { id: "furniture", label: "Мебель мешает" },
  { id: "partial", label: "Частичная покраска" },
  { id: "wet", label: "Сыро / плесень" },
];

/** Attention → позиция в смете */
export const ATTENTION_TO_EXTRA = {
  lights: "lights",
  radiators: "radiator",
  ac: "ac_cover",
  garlands: "garland",
  chimneys: "chimney_work",
  cable_duct: "cable",
};

export const SCAFFOLD_OPTIONS = [
  { id: "none", title: "С земли / стремянка" },
  { id: "ladder", title: "Высотные лестницы" },
  { id: "tower", title: "Вышка-тура" },
  { id: "scaffold", title: "Леса" },
  { id: "lift", title: "Подъёмник" },
];


/**
 * Поток продукта:
 * 1 Проект (имя, клиент, адрес)
 * 2–5 Замер
 * 6 Конструктор (технология / ЛКМ)
 * 7 Участок (быт, доступ/леса — влияет на смету, + реквизиты для договора)
 * 8 Смета (итог)
 */
export const STEPS = [
  { id: "client", title: "Проект", icon: "1", phase: "project", coach: "Название · клиент · адрес" },
  { id: "building", title: "Строение", icon: "2", phase: "measure", coach: "Тип · зоны · крыша" },
  { id: "walls", title: "Замер", icon: "3", phase: "measure", coach: "Сторона целиком: стены · проёмы · допы" },
  { id: "tech", title: "Конструктор", icon: "4", phase: "constructor", coach: "Технология и ЛКМ" },
  { id: "site", title: "Участок", icon: "5", phase: "rest", coach: "Быт и реквизиты" },
  { id: "estimate", title: "Смета", icon: "6", phase: "rest", coach: "Итог · PDF" },
];

export const PHASE_LABELS = {
  project: "Проект",
  measure: "Замер",
  constructor: "Конструктор",
  rest: "Участок и смета",
};

export const WALL_PRESETS = [
  { label: "Главный фасад", hint: "Сторона с входом / к дороге" },
  { label: "Правый фасад", hint: "Идя лицом к главному — справа" },
  { label: "Задний фасад", hint: "Противоположная главному" },
  { label: "Левый фасад", hint: "Идя лицом к главному — слева" },
];

export const OPENING_PRESETS = [
  { label: "Окно", kind: "window" },
  { label: "Дверь", kind: "door" },
  { label: "Панорамное / витраж", kind: "window" },
];
