import { num, syncAreasFromLists, totalAreas, calcWallArea, migrateSurvey } from "./calc.js";

/** Оценка готовности замера — как «можно уезжать?» */
export function readiness(survey) {
  migrateSurvey(survey);
  const checks = [];
  const add = (id, ok, label, fix) => checks.push({ id, ok: !!ok, label, fix });

  add("title", !!survey.title?.trim() || !!survey.contract?.objectName?.trim(), "Название проекта", "Укажите название");
  add("address", !!survey.client?.address?.trim(), "Адрес участка", "Укажите адрес");
  add("client", !!survey.client?.name?.trim() || !!survey.client?.phone?.trim(), "Клиент или телефон", "ФИО или телефон");
  add("buildings", survey.buildings?.length > 0, "Есть строение", "Добавьте строение");

  for (const b of survey.buildings || []) {
    syncAreasFromLists(b);
    const prefix = survey.buildings.length > 1 ? `[${b.name}] ` : "";
    const facade = b.zones?.facade ? calcWallArea(b.measure, "facade").total : 0;
    const interior = b.zones?.interior ? calcWallArea(b.measure, "interior").total : 0;
    add(`${b.id}_zone`, b.zones?.facade || b.zones?.interior, `${prefix}Зона работ`, "Снаружи и/или внутри");
    add(`${b.id}_area`, facade + interior > 0, `${prefix}Площадь > 0`, "Замерьте плоскости");
    add(`${b.id}_humid`, num(b.humidity) > 0, `${prefix}Влажность`, "Влагомер на объекте");
    if (b.zones?.facade) {
      add(`${b.id}_paint`, !!b.tech?.paintId, `${prefix}ЛКМ фасад`, "Выберите материал");
      add(`${b.id}_tech`, !!b.tech?.techId, `${prefix}Технология фасад`, "Выберите подготовку");
    }
    if (b.zones?.interior) {
      add(`${b.id}_paint_i`, !!b.tech?.paintIdInterior || !!b.tech?.paintId, `${prefix}ЛКМ интерьер`, "Выберите интерьерный состав");
    }
    if (b.houseType && b.houseType !== "new") {
      add(`${b.id}_compat`, !!b.tech?.compatibilityTest, `${prefix}Тест совместимости`, "Отметьте тест на шаге технологии");
    }
    add(
      `${b.id}_photo`,
      (b.photos?.length || 0) > 0 || (b.measure?.walls || []).some((w) => (w.photos || []).length > 0),
      `${prefix}Фото (общий или сторон)`,
      "Сделайте фото сторон на шаге «Замер»"
    );
    const wallsNeed = (b.measure?.walls || []).filter((w) => num(w.length) || num(w.areaManual) || num(w.height));
    if (wallsNeed.length) {
      const withPh = wallsNeed.filter((w) => (w.photos || []).length > 0).length;
      add(
        `${b.id}_wall_photos`,
        withPh >= wallsNeed.length,
        `${prefix}Фото по плоскостям ${withPh}/${wallsNeed.length}`,
        "Каждая замерённая сторона — со своим фото"
      );
    }
  }

  const required = checks.filter((c) => !c.id.endsWith("_photo") && !c.id.endsWith("_compat") && !c.id.endsWith("_wall_photos"));
  const soft = checks.filter((c) => c.id.endsWith("_photo") || c.id.endsWith("_compat") || c.id.endsWith("_wall_photos"));
  const reqOk = required.filter((c) => c.ok).length;
  const softOk = soft.filter((c) => c.ok).length;
  const pct = Math.round((reqOk / Math.max(1, required.length)) * 100);
  const canLeave = required.every((c) => c.ok);
  const areas = totalAreas(survey);

  return {
    checks,
    required,
    soft,
    pct,
    canLeave,
    softPct: soft.length ? Math.round((softOk / soft.length) * 100) : 100,
    areas,
    missing: required.filter((c) => !c.ok),
  };
}

export function readinessHtml(survey) {
  const r = readiness(survey);
  return `
    <div class="ready-card ${r.canLeave ? "ok" : "warn"}">
      <div class="ready-top">
        <div>
          <strong>Готовность замера</strong>
          <div class="hint">${r.canLeave ? "Можно показывать клиенту и уезжать" : "До закрытия объекта закройте пункты ниже"}</div>
        </div>
        <div class="ready-pct">${r.pct}%</div>
      </div>
      <div class="ready-bar"><i style="width:${r.pct}%"></i></div>
      <ul class="ready-list">
        ${r.checks
          .map(
            (c) => `
          <li class="${c.ok ? "done" : "todo"}">
            <span class="mark">${c.ok ? "✓" : "!"}</span>
            <span>${c.label}${c.ok ? "" : ` — <em>${c.fix}</em>`}</span>
          </li>`
          )
          .join("")}
      </ul>
    </div>
  `;
}

/** Типовые стартовые шаблоны */
export const TEMPLATES = [
  {
    id: "house_10x12",
    title: "Дом 10×12",
    hint: "4 стены, 2 фронтона, типовой загородный",
    apply(survey, emptyBuilding, uid, syncWarmTotal, syncAreas) {
      const b = emptyBuilding({ name: "Дом", kind: "house" });
      b.roofType = "gable";
      b.zones = { facade: true, interior: false };
      b.measure.walls = [
        { id: uid(), label: "Главный", shape: "gable", length: "12", height: "3.0", ridge: "5.2", height2: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "Правый", shape: "rect", length: "10", height: "3.0", ridge: "", height2: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "Задний", shape: "gable", length: "12", height: "3.0", ridge: "5.2", height2: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "Левый", shape: "rect", length: "10", height: "3.0", ridge: "", height2: "", areaManual: "", zone: "facade", note: "" },
      ];
      b.measure.roundCoef = 1;
      syncAreas(b);
      survey.buildings = [b];
      survey.activeBuildingId = b.id;
    },
  },
  {
    id: "bath_log",
    title: "Баня из бревна",
    hint: "6×4, K=1.15, двускат",
    apply(survey, emptyBuilding, uid, syncWarmTotal, syncAreas) {
      const b = emptyBuilding({ name: "Баня", kind: "bath" });
      b.material = "log";
      b.roofType = "gable";
      b.measure.roundCoef = 1.15;
      b.measure.walls = [
        { id: uid(), label: "А", shape: "rect", length: "6", height: "2.6", ridge: "", height2: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "Б", shape: "gable", length: "4", height: "2.4", ridge: "3.5", height2: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "В", shape: "rect", length: "6", height: "2.6", ridge: "", height2: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "Г", shape: "gable", length: "4", height: "2.4", ridge: "3.5", height2: "", areaManual: "", zone: "facade", note: "" },
      ];
      syncAreas(b);
      survey.buildings = [b];
      survey.activeBuildingId = b.id;
    },
  },
  {
    id: "garage",
    title: "Гараж + ворота",
    hint: "Сразу с проёмом ворот",
    apply(survey, emptyBuilding, uid, syncWarmTotal, syncAreas) {
      const b = emptyBuilding({ name: "Гараж", kind: "garage" });
      b.roofType = "shed";
      b.measure.walls = [
        { id: uid(), label: "Фасад с воротами", shape: "rect", length: "6", height: "3", ridge: "", height2: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "Бок", shape: "trap", length: "7", height: "2.5", height2: "3", ridge: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "Зад", shape: "rect", length: "6", height: "2.5", ridge: "", height2: "", areaManual: "", zone: "facade", note: "" },
        { id: uid(), label: "Бок 2", shape: "trap", length: "7", height: "2.5", height2: "3", ridge: "", areaManual: "", zone: "facade", note: "" },
      ];
      b.measure.openings = [{ id: uid(), label: "Ворота", width: "3.5", height: "2.5", zone: "facade" }];
      syncAreas(b);
      survey.buildings = [b];
      survey.activeBuildingId = b.id;
    },
  },
  {
    id: "fence_50",
    title: "Забор 50 м",
    hint: "Щит 1.8 м, без фронтонов",
    apply(survey, emptyBuilding, uid, syncWarmTotal, syncAreas) {
      const b = emptyBuilding({ name: "Забор", kind: "fence" });
      b.roofType = "shed";
      b.zones = { facade: true, interior: false };
      b.measure.roundCoef = 1;
      b.measure.walls = [
        { id: uid(), label: "Пролёт", shape: "rect", length: "50", height: "1.8", ridge: "", height2: "", areaManual: "", zone: "facade", note: "две стороны — уточните" },
      ];
      syncAreas(b);
      survey.buildings = [b];
      survey.activeBuildingId = b.id;
    },
  },
];
