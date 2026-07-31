import { EXTRA_WORKS } from "../data/extras.js";
import { OBJECT_KINDS, wallsForPreset } from "../data/objects.js";

export function num(v, fallback = 0) {
  const n = parseFloat(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : fallback;
}

export function round2(n) {
  return Math.round(n * 100) / 100;
}

export function uid() {
  return `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * Площадь одной плоскости:
 * rect: L × H
 * gable: L × H + L × (Hконёк − H) / 2
 * trap: L × (H + H2) / 2
 * custom: areaManual
 */
export function wallAreaOf(side) {
  const shape = side.shape || "rect";
  if (shape === "custom") {
    return round2(Math.max(0, num(side.areaManual)));
  }
  const L = num(side.length);
  const H = num(side.height);
  if (shape === "gable") {
    const ridge = num(side.ridge);
    const triangle = Math.max(0, ridge - H);
    return round2(Math.max(0, L * H + (L * triangle) / 2));
  }
  if (shape === "trap") {
    const H2 = num(side.height2, H);
    return round2(Math.max(0, (L * (H + H2)) / 2));
  }
  return round2(Math.max(0, L * H));
}

export function openingsAreaOf(list) {
  return round2(
    (list || []).reduce((s, o) => s + Math.max(0, num(o.width) * num(o.height)), 0)
  );
}

export function wallsAreaOf(list, zoneFilter = null) {
  return round2(
    (list || [])
      .filter((w) => !zoneFilter || (w.zone || "facade") === zoneFilter)
      .reduce((s, w) => s + wallAreaOf(w), 0)
  );
}

/**
 * Площадь торцов / перерубов на одной стороне.
 * Выступ ~0.2 м; при «с боками» ×3 (торец + 2 бока), как на объекте.
 * Приоритет: ручная м² → длина пог.м × глубина → кол-во × высота × глубина.
 */
export function wallEndsAreaOf(side) {
  if (!side) return 0;
  const manual = num(side.endsAreaManual);
  if (manual > 0) return round2(manual);
  const on = side.endsOn || num(side.endsCount) > 0 || num(side.endsLength) > 0;
  if (!on) return 0;
  const depth = num(side.endsDepth, 0.2) || 0.2;
  const mul = side.endsWithSides ? 3 : 1;
  const len = num(side.endsLength);
  if (len > 0) return round2(len * depth * mul);
  const count = num(side.endsCount);
  const H = num(side.height) || num(side.ridge) || 0;
  if (count > 0 && H > 0) return round2(count * H * depth * mul);
  return 0;
}

export function endsAreaFromWalls(list) {
  return round2((list || []).reduce((s, w) => s + wallEndsAreaOf(w), 0));
}

export function trimLengthFromWalls(list) {
  return round2((list || []).reduce((s, w) => s + Math.max(0, num(w.trimLength)), 0));
}

/** Сумма числового поля со всех сторон → в measure */
export function sumWallField(list, key) {
  return round2((list || []).reduce((s, w) => s + Math.max(0, num(w?.[key])), 0));
}

/** Поля допов, которые считаем по сторонам и суммируем в measure */
export const WALL_EXTRA_FIELDS = [
  ["soffitArea", "soffitArea"],
  ["fasciaArea", "fasciaArea"],
  ["overhangArea", "overhangArea"],
  ["porchArea", "porchArea"],
  ["stairsArea", "stairsArea"],
  ["trimLength", "trimLength"],
  ["doborLength", "doborLength"],
  ["gutterLength", "gutterLength"],
  ["sillLength", "sillLength"],
  ["railingsArea", "railingsArea"],
  ["warmLength", "warmSeamTotal"],
  ["ceilingArea", "ceilingArea"],
  ["floorArea", "floorArea"],
];

/** Sобщ = (Sст − Sок/дв + Sтор) × K */
export function calcWallArea(m, zoneFilter = null) {
  const wallsList = m.walls || [];
  const openingsList = (m.openings || []).filter(
    (o) => !zoneFilter || (o.zone || "facade") === zoneFilter
  );
  let walls = zoneFilter ? wallsAreaOf(wallsList, zoneFilter) : num(m.wallsArea) || wallsAreaOf(wallsList);
  const openings = zoneFilter
    ? openingsAreaOf(openingsList)
    : num(m.openingsArea) || openingsAreaOf(m.openings || []);
  const fromWalls = zoneFilter === "interior" ? 0 : endsAreaFromWalls(wallsList);
  const endsArea = zoneFilter === "interior" ? 0 : fromWalls > 0 ? fromWalls : num(m.endsArea);
  const k = zoneFilter === "interior" ? 1 : num(m.roundCoef, 1) || 1;
  const sides = zoneFilter === "interior" ? 1 : Math.max(1, num(m.paintSides, 1) || 1);
  if (sides > 1) walls = round2(walls * sides);
  const base = walls - openings + endsArea;
  return {
    base,
    k,
    total: Math.max(0, round2(base * k)),
    walls,
    openings,
    endsArea,
  };
}

/** Живая формула как в листе осмотра */
export function formulaHtml(building, zone = "facade") {
  const r = calcWallArea(building.measure, zone);
  const label = zone === "interior" ? "Интерьер" : "Фасад";
  return `
    <div class="formula-card" data-formula-zone="${zone}">
      <div class="formula-label">${label} · лист осмотра</div>
      <div class="formula-eq">
        S<sub>общ</sub> = (S<sub>ст</sub> − S<sub>ок/дв</sub> + S<sub>тор</sub>) × K
      </div>
      <div class="formula-nums">
        (${r.walls.toFixed(2)} − ${r.openings.toFixed(2)} + ${r.endsArea.toFixed(2)}) × ${r.k}
        = <b>${r.total.toFixed(2)} м²</b>
        ${num(building.measure.paintSides, 1) > 1 ? ` · сторон ×${building.measure.paintSides}` : ""}
      </div>
    </div>
  `;
}

export function syncAreasFromLists(buildingOrSurvey) {
  // accept building or whole survey (legacy)
  const b = buildingOrSurvey.measure ? buildingOrSurvey : getActiveBuilding(buildingOrSurvey);
  const m = b.measure;
  if (!m.walls) m.walls = [];
  if (!m.openings) m.openings = [];
  m.paintSides = b.kind === "fence" && b.fenceBothSides ? 2 : 1;
  m.wallsArea = wallsAreaOf(m.walls);
  m.openingsArea = openingsAreaOf(m.openings);
  const endsWalls = endsAreaFromWalls(m.walls);
  if (endsWalls > 0) m.endsArea = endsWalls;
  for (const [wallKey, measureKey] of WALL_EXTRA_FIELDS) {
    const sum = sumWallField(m.walls, wallKey);
    if (sum > 0) m[measureKey] = sum;
  }
  m.facadeArea = calcWallArea(m, "facade").total;
  m.interiorArea = calcWallArea(m, "interior").total;
  return calcWallArea(m);
}

export function coefForMaterial(materialId) {
  if (materialId === "log") return 1.15;
  if (materialId === "hand_log") return 1.2;
  if (materialId === "block") return 1.1;
  return 1;
}

export function money(n) {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(n || 0);
}

export function listPaintOptions(catalog, scope = "facade") {
  const out = [];
  for (const [brand, pack] of Object.entries(catalog || {})) {
    for (const p of pack.products) {
      const name = (p.name || "").toLowerCase();
      const scopeMeta = (p.scope || "").toLowerCase();
      const both =
        name.includes("фасад и интерьер") ||
        scopeMeta.includes("фасад и интерьер") ||
        scopeMeta.includes("фасад/интерьер");
      const isInterior =
        !both &&
        (scopeMeta.includes("интерьер") ||
          name.includes("интерьер") ||
          name.includes("terra wax") ||
          name.includes("sterling"));
      if (scope === "facade" && isInterior) continue;
      if (scope === "interior" && !isInterior && !both) continue;
      const opacity =
        p.coating || (name.includes("укрывн") ? "opaque" : "semi");
      out.push({
        id: p.id ? `${brand}::${p.id}` : `${brand}::${p.name}`,
        brand,
        name: p.displayName || p.name,
        fullName: p.name,
        type: p.type || "",
        opacity,
        fan: p.fan || "",
        country: p.country || "",
        warrantyYears45: p.warrantyYears45 || null,
        antisepticRequired: !!p.antisepticRequired,
        note: p.note || "",
        pricesByTech: p.pricesByTech || null,
        items: p.items,
      });
    }
  }
  return out;
}

export function emptyMeasure(kind = "house") {
  const meta = OBJECT_KINDS.find((k) => k.id === kind) || OBJECT_KINDS[0];
  return {
    walls: wallsForPreset(meta.wallPreset, uid),
    openings: [],
    wallsArea: 0,
    openingsArea: 0,
    facadeArea: 0,
    interiorArea: 0,
    endsArea: "",
    endsLength: "",
    soffitArea: "",
    fasciaArea: "",
    ceilingArea: "",
    floorArea: "",
    floorNote: "",
    railingsArea: "",
    railingsLength: "",
    beamsLength: "",
    overhangLength: "",
    overhangArea: "",
    trimLength: "",
    doborLength: "",
    layoutLength: "",
    gutterLength: "",
    sillLength: "",
    porchArea: "",
    stairsArea: "",
    fencePosts: "",
    plinthNote: "",
    roundCoef: 1,
    paintSides: 1,
    warmHorizontal: "",
    warmSnake: "",
    warmCracks: "",
    warmWindows: "",
    warmMinus: "",
    warmSeamTotal: "",
    caulk: "unknown",
    oldSealant: "unknown",
    notes: "",
  };
}

export function emptyBuilding(overrides = {}) {
  const kind = overrides.kind || "house";
  const meta = OBJECT_KINDS.find((k) => k.id === kind) || OBJECT_KINDS[0];
  return {
    id: uid(),
    name: overrides.name || meta.title,
    kind,
    roofType: "gable",
    zones: { facade: true, interior: false },
    material: "beam",
    materialSize: "",
    houseType: "new",
    condition: "good",
    humidity: "",
    colors: "",
    oldCoatingNote: "",
    removalDifficulty: "normal",
    fenceBothSides: false,
    plinthSkip: false,
    tech: {
      techId: 4,
      paintId: "",
      paintIdInterior: "",
      scope: "facade",
      colorSameOrDarker: true,
      compatibilityTest: false,
      techIdInterior: 4,
    },
    previewColor: "#c4a35a",
    photos: [],
    dims: { length: "", width: "", heightRidge: "", heightGable: "" },
    measure: emptyMeasure(kind),
    ...overrides,
  };
}

export function emptySurvey() {
  const b = emptyBuilding({ name: "Строение 1", kind: "house" });
  return {
    id: uid(),
    title: "",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    client: {
      name: "",
      phone: "",
      email: "",
      address: "",
      surveyor: "",
    },
    buildings: [b],
    activeBuildingId: b.id,
    // legacy flat mirrors for older helpers — kept in sync via getActiveBuilding
    house: null,
    measure: null,
    tech: null,
    attention: {},
    site: {
      startWhen: "",
      workHours: "",
      powerKw: "",
      powerFrom: "",
      powerOk: "yes",
      generator: false,
      housing: "none",
      toilet: "none",
      shower: "none",
      water: "none",
      shop: "",
      scaffold: "none",
      maxHeight: "",
      accessNote: "",
      occupancy: "empty",
      clientFurniture: "yes",
      notes: "",
    },
    extras: { qty: {} },
    estimate: {
      discountPct: 0,
      payments: { advance: 10, second: 40, third: 40, final: 10 },
      customLines: [],
    },
    contract: {
      objectName: "",
      number: "",
      date: "",
      workDays: "",
      startDate: "",
      managerName: "",
      managerPhone: "",
      surveyorPhone: "",
      passport: "",
      passportIssued: "",
      passportCode: "",
      registration: "",
    },
  };
}

export function getActiveBuilding(survey) {
  if (!survey.buildings?.length) {
    // migrate legacy
    migrateSurvey(survey);
  }
  let b = survey.buildings.find((x) => x.id === survey.activeBuildingId);
  if (!b) {
    b = survey.buildings[0];
    survey.activeBuildingId = b.id;
  }
  return b;
}

export function migrateSurvey(survey) {
  if (survey.title == null) {
    survey.title = survey.contract?.objectName || "";
  }
  if (!survey.attention) survey.attention = {};
  if (!survey.extras) survey.extras = { qty: {} };
  if (!survey.extras.qty) survey.extras.qty = {};
  if (survey.buildings?.length) {
    for (const b of survey.buildings) {
      if (!b.measure) b.measure = emptyMeasure(b.kind);
      if (!b.zones) b.zones = { facade: true, interior: false };
      if (!b.tech) b.tech = emptyBuilding().tech;
      if (!b.previewColor) b.previewColor = "#c4a35a";
      if (!Array.isArray(b.photos)) b.photos = [];
      if (!b.dims) b.dims = { length: "", width: "", heightRidge: "", heightGable: "" };
      for (const w of b.measure.walls || []) {
        if (!w.shape) w.shape = "rect";
        if (!w.zone) w.zone = "facade";
        if (w.height2 == null) w.height2 = "";
        if (w.ridge == null) w.ridge = "";
        if (w.areaManual == null) w.areaManual = "";
        if (!Array.isArray(w.photos)) w.photos = [];
        if (w.material == null) w.material = "";
        if (w.condition == null) w.condition = "";
        if (w.coatingWant == null) w.coatingWant = "";
        if (!w.flags) w.flags = {};
        if (w.damageArea == null) w.damageArea = "";
      }
      for (const o of b.measure.openings || []) {
        if (!o.zone) o.zone = "facade";
        if (o.obsadaProtrudes == null) o.obsadaProtrudes = false;
        if (o.obsadaSide == null) o.obsadaSide = "";
        if (o.obsadaTop == null) o.obsadaTop = "";
        if (o.obsadaBottom == null) o.obsadaBottom = "";
        if (o.wallId == null) o.wallId = "";
        if (o.needsWarm == null) o.needsWarm = false;
        if (o.note == null) o.note = "";
      }
      if (survey.site && survey.site.shower == null) survey.site.shower = "none";
      if (!survey.estimate) survey.estimate = { discountPct: 0 };
      if (!survey.estimate.payments) survey.estimate.payments = { advance: 10, second: 40, third: 40, final: 10 };
      if (!Array.isArray(survey.estimate.customLines)) survey.estimate.customLines = [];
      if (survey.site) {
        if (survey.site.scaffold == null) survey.site.scaffold = "none";
        if (survey.site.powerOk == null) survey.site.powerOk = "yes";
        if (survey.site.occupancy == null) survey.site.occupancy = "empty";
        if (survey.site.clientFurniture == null) survey.site.clientFurniture = "yes";
        if (survey.site.generator == null) survey.site.generator = false;
      }
      if (b.fenceBothSides == null) b.fenceBothSides = false;
      if (b.plinthSkip == null) b.plinthSkip = false;
      syncWarmTotal(b.measure);
      if (!survey.contract) {
        survey.contract = {
          objectName: "",
          number: "",
          date: "",
          workDays: "",
          startDate: "",
          managerName: "",
          managerPhone: "",
          surveyorPhone: "",
          passport: "",
          passportIssued: "",
          passportCode: "",
          registration: "",
        };
      }
      syncAreasFromLists(b);
    }
    return survey;
  }

  // legacy flat → one building
  const b = emptyBuilding({
    name: "Основной объект",
    kind: "house",
    material: survey.house?.material || "beam",
    materialSize: survey.house?.materialSize || "",
    houseType: survey.house?.houseType || "new",
    condition: survey.house?.condition || "good",
    humidity: survey.house?.humidity || "",
    colors: survey.house?.colors || "",
    oldCoatingNote: survey.house?.oldCoatingNote || "",
    removalDifficulty: survey.house?.removalDifficulty || "normal",
  });
  if (survey.measure) {
    b.measure = { ...emptyMeasure(), ...survey.measure };
    if (!Array.isArray(b.measure.walls) || !b.measure.walls.length) {
      b.measure.walls = emptyMeasure().walls;
    }
  }
  if (survey.tech) b.tech = { ...b.tech, ...survey.tech };
  if (survey.tech?.scope === "interior") {
    b.zones = { facade: false, interior: true };
  }
  survey.buildings = [b];
  survey.activeBuildingId = b.id;
  syncAreasFromLists(b);
  return survey;
}

export function totalAreas(survey) {
  migrateSurvey(survey);
  let facade = 0;
  let interior = 0;
  let soffit = 0;
  let ceiling = 0;
  let floor = 0;
  let warm = 0;
  let ends = 0;
  for (const b of survey.buildings) {
    syncAreasFromLists(b);
    if (b.zones?.facade) facade += num(b.measure.facadeArea);
    if (b.zones?.interior) interior += num(b.measure.interiorArea);
    soffit += num(b.measure.soffitArea);
    ceiling += num(b.measure.ceilingArea);
    floor += num(b.measure.floorArea);
    warm += num(b.measure.warmSeamTotal);
    ends += num(b.measure.endsLength);
  }
  return {
    facade: round2(facade),
    interior: round2(interior),
    soffit: round2(soffit),
    ceiling: round2(ceiling),
    floor: round2(floor),
    warm: round2(warm),
    ends: round2(ends),
    paintTotal: round2(facade + interior),
  };
}

function paintLine(catalog, paintId, techId, qty, label) {
  if (!paintId || !techId || qty <= 0) return null;
  const [brand, ...rest] = paintId.split("::");
  const key = rest.join("::");
  const product = catalog[brand]?.products.find(
    (p) => p.id === key || p.name === key || p.displayName === key
  );
  const item = product?.items.find((i) => i.tech === techId);
  if (!item) return null;
  return {
    id: `paint_${label}_${techId}`,
    name: `${label}: ${product.name} (техн. ${techId})`,
    unit: "кв.м",
    qty,
    price: item.price,
    sum: round2(qty * item.price),
    guarantee: item.guarantee,
  };
}

export function buildEstimate(state, catalog) {
  migrateSurvey(state);
  const lines = [];

  for (const b of state.buildings) {
    syncAreasFromLists(b);
    const prefix = state.buildings.length > 1 ? `[${b.name}] ` : "";

    if (b.zones?.facade) {
      const facade = calcWallArea(b.measure, "facade").total;
      const line = paintLine(catalog, b.tech.paintId, b.tech.techId, facade, `${prefix}Фасад стены`);
      if (line) lines.push(line);

      const soffit = num(b.measure.soffitArea);
      const soffitLine = paintLine(
        catalog,
        b.tech.paintId,
        b.tech.techId,
        soffit,
        `${prefix}Подшива`
      );
      if (soffitLine) lines.push(soffitLine);

      const fascia = num(b.measure.fasciaArea);
      const fasciaLine = paintLine(
        catalog,
        b.tech.paintId,
        b.tech.techId,
        fascia,
        `${prefix}Лобовая`
      );
      if (fasciaLine) lines.push(fasciaLine);

      const rail = num(b.measure.railingsArea);
      const railLine = paintLine(
        catalog,
        b.tech.paintId,
        b.tech.techId,
        rail,
        `${prefix}Ограждения`
      );
      if (railLine) lines.push(railLine);

      const endsLen = num(b.measure.endsLength);
      if (endsLen > 0) {
        lines.push({
          id: `ends_${b.id}`,
          name: `${prefix}Торцы: шлифовка, пропитка, покраска`,
          unit: "пог.м",
          qty: endsLen,
          price: 1100,
          sum: round2(endsLen * 1100),
        });
      }

      const warm = num(b.measure.warmSeamTotal);
      if (warm > 0) {
        lines.push({
          id: `warm_${b.id}`,
          name: `${prefix}Тёплый шов (комплекс)`,
          unit: "пог.м",
          qty: warm,
          price: 500,
          sum: round2(warm * 500),
        });
      }

      const trim = num(b.measure.trimLength);
      if (trim > 0) {
        lines.push({
          id: `trim_${b.id}`,
          name: `${prefix}Наличники/доборы`,
          unit: "пог.м",
          qty: trim,
          price: 750,
          sum: round2(trim * 750),
        });
      }

      const dobor = num(b.measure.doborLength);
      if (dobor > 0) {
        lines.push({
          id: `dobor_${b.id}`,
          name: `${prefix}Доборы / раскладка (покраска без полного цикла)`,
          unit: "пог.м",
          qty: dobor,
          price: 400,
          sum: round2(dobor * 400),
        });
      }

      const layout = num(b.measure.layoutLength);
      if (layout > 0) {
        lines.push({
          id: `layout_${b.id}`,
          name: `${prefix}Раскладка / уголок`,
          unit: "пог.м",
          qty: layout,
          price: 550,
          sum: round2(layout * 550),
        });
      }

      const gutter = num(b.measure.gutterLength);
      if (gutter > 0) {
        lines.push({
          id: `gutter_${b.id}`,
          name: `${prefix}Демонтаж/монтаж водостока`,
          unit: "пог.м",
          qty: gutter,
          price: 600,
          sum: round2(gutter * 600),
        });
      }

      const sill = num(b.measure.sillLength);
      if (sill > 0) {
        lines.push({
          id: `sill_${b.id}`,
          name: `${prefix}Отливы (демонтаж/монтаж)`,
          unit: "пог.м",
          qty: sill,
          price: 500,
          sum: round2(sill * 500),
        });
      }

      const beams = num(b.measure.beamsLength);
      if (beams > 0) {
        lines.push({
          id: `beams_${b.id}`,
          name: `${prefix}Балки / элементы (покраска)`,
          unit: "пог.м",
          qty: beams,
          price: 400,
          sum: round2(beams * 400),
        });
      }

      const overhang = num(b.measure.overhangArea);
      const ohLine = paintLine(catalog, b.tech.paintId, b.tech.techId, overhang, `${prefix}Свесы`);
      if (ohLine) lines.push(ohLine);

      const porch = num(b.measure.porchArea);
      const porchLine = paintLine(catalog, b.tech.paintId, b.tech.techId, porch, `${prefix}Крыльцо / вход`);
      if (porchLine) lines.push(porchLine);

      const stairs = num(b.measure.stairsArea);
      const stairsLine = paintLine(catalog, b.tech.paintId, b.tech.techId, stairs, `${prefix}Лестница`);
      if (stairsLine) lines.push(stairsLine);

      // per-wall damage / prep
      for (const w of b.measure.walls || []) {
        const dmg = num(w.damageArea);
        if (dmg > 0 && (w.flags?.rot || w.flags?.wet)) {
          lines.push({
            id: `rot_${w.id}`,
            name: `${prefix}${w.label || "Сторона"}: ремонт / антисептик`,
            unit: "кв.м",
            qty: dmg,
            price: 1200,
            sum: round2(dmg * 1200),
          });
        }
        if (w.flags?.high && num(wallAreaOf(w)) > 0) {
          const ha = wallAreaOf(w) * (b.fenceBothSides && b.kind === "fence" ? 2 : 1);
          lines.push({
            id: `high_${w.id}`,
            name: `${prefix}${w.label || "Сторона"}: надбавка за высоту`,
            unit: "кв.м",
            qty: ha,
            price: 150,
            sum: round2(ha * 150),
          });
        }
      }
    }

    if (b.zones?.interior) {
      const interior = calcWallArea(b.measure, "interior").total;
      const paintInt = b.tech.paintIdInterior || b.tech.paintId;
      const techInt = b.tech.techIdInterior || b.tech.techId;
      const line = paintLine(catalog, paintInt, techInt, interior, `${prefix}Интерьер стены`);
      if (line) lines.push(line);

      const ceiling = num(b.measure.ceilingArea);
      const ceilLine = paintLine(catalog, paintInt, techInt, ceiling, `${prefix}Потолки`);
      if (ceilLine) lines.push(ceilLine);

      // floors — often separate materials; use same paint as rough estimate with note
      const floor = num(b.measure.floorArea);
      if (floor > 0 && paintInt) {
        const fl = paintLine(catalog, paintInt, techInt, floor, `${prefix}Полы (оценка)`);
        if (fl) {
          fl.name += b.measure.floorNote ? ` — ${b.measure.floorNote}` : " — уточнить ЛКМ";
          lines.push(fl);
        }
      }
    }
  }

  for (const [id, qtyRaw] of Object.entries(state.extras?.qty || {})) {
    const qty = num(qtyRaw);
    if (qty <= 0) continue;
    const found = EXTRA_WORKS.flatMap((g) => g.items).find((i) => i.id === id);
    if (!found) continue;
    if (
      ["ends_seal", "warm_full", "trim_full", "gutter"].includes(id) &&
      lines.some((l) => l.id.startsWith("ends_") || l.id.startsWith("warm_") || l.id.startsWith("trim_") || l.id.startsWith("gutter_"))
    ) {
      continue;
    }
    lines.push({
      id: `extra_${id}`,
      name: found.name,
      unit: found.unit,
      qty,
      price: found.price,
      sum: round2(qty * found.price),
    });
  }

  // scaffold from site
  const sc = state.site?.scaffold;
  if (sc === "tower" && !lines.some((l) => l.id === "extra_scaffold_tower")) {
    lines.push({ id: "site_tower", name: "Вышка-тура (оценка)", unit: "шт", qty: 1, price: 3500, sum: 3500 });
  } else if (sc === "scaffold" && !lines.some((l) => l.id === "extra_scaffold_full")) {
    lines.push({ id: "site_scaffold", name: "Леса (оценка/мес)", unit: "шт", qty: 1, price: 25000, sum: 25000 });
  } else if (sc === "lift" && !lines.some((l) => l.id === "extra_lift")) {
    lines.push({ id: "site_lift", name: "Подъёмник (смена, оценка)", unit: "шт", qty: 1, price: 12000, sum: 12000 });
  } else if (sc === "ladder") {
    // height surcharge already per-wall; optional global
  }

  for (const cl of state.estimate?.customLines || []) {
    const qty = num(cl.qty);
    const price = num(cl.price);
    if (!cl.name?.trim() || qty <= 0) continue;
    lines.push({
      id: `custom_${cl.id || cl.name}`,
      name: cl.name.trim(),
      unit: cl.unit || "шт",
      qty,
      price,
      sum: round2(qty * price),
    });
  }

  const subtotal = round2(lines.reduce((s, l) => s + l.sum, 0));
  const discountPct = num(state.estimate?.discountPct);
  const afterDiscount = round2(subtotal * (1 - discountPct / 100));
  const vat = round2(afterDiscount * 0.05);
  const total = round2(afterDiscount + vat);
  const areas = totalAreas(state);

  return {
    lines,
    subtotal,
    discountPct,
    afterDiscount,
    vat,
    total,
    paintArea: areas.paintTotal,
    areas,
  };
}

export function syncWarmTotal(measure) {
  const parts = [
    num(measure.warmHorizontal),
    num(measure.warmSnake),
    num(measure.warmCracks),
    num(measure.warmWindows),
  ];
  const minus = num(measure.warmMinus);
  measure.warmSeamTotal = round2(Math.max(0, parts.reduce((a, b) => a + b, 0) - minus));
  return measure;
}

export function applyKindPreset(building, kind) {
  const meta = OBJECT_KINDS.find((k) => k.id === kind) || OBJECT_KINDS[0];
  building.kind = kind;
  building.name = building.name || meta.title;
  const hasData = (building.measure.walls || []).some(
    (w) => num(w.length) || num(w.height) || num(w.areaManual)
  );
  if (!hasData) {
    building.measure.walls = wallsForPreset(meta.wallPreset, uid);
  }
  if (kind === "fence") {
    building.zones = { facade: true, interior: false };
    building.measure.roundCoef = 1;
  }
  if (kind === "terrace") {
    building.zones = { facade: true, interior: false };
  }
  return building;
}

// aliases used by older app code
export function defaultWalls() {
  return wallsForPreset("box4", uid);
}


/** Продукт ЛКМ по paintId brand::id */
export function findPaintProduct(catalog, paintId) {
  if (!paintId || !catalog) return null;
  const [brand, ...rest] = String(paintId).split("::");
  const key = rest.join("::");
  return (
    catalog[brand]?.products.find(
      (p) => p.id === key || p.name === key || p.displayName === key
    ) || null
  );
}

/**
 * Разложение стоимости фасадной покраски по сторонам (пропорционально площади).
 */
export function sideCostBreakdown(building, catalog) {
  if (!building?.zones?.facade) return [];
  syncAreasFromLists(building);
  const walls = (building.measure?.walls || []).filter((w) => (w.zone || "facade") !== "interior");
  const facade = calcWallArea(building.measure, "facade");
  const product = findPaintProduct(catalog, building.tech?.paintId);
  const techId = Number(building.tech?.techId) || 4;
  const item = product?.items?.find((i) => i.tech === techId);
  const priceM2 = item ? Number(item.price) || 0 : 0;
  const totalPaint = facade.total * priceM2;
  const wallAreas = walls.map((w) => {
    const gross = wallAreaOf(w);
    const opens = (building.measure.openings || [])
      .filter((o) => o.wallId === w.id)
      .reduce((s, o) => s + num(o.width) * num(o.height), 0);
    const ends = num(w.endsLength) ? num(w.endsLength) : 0;
    // доля от фасада по «вкладу» стены (грубо: площадь стены)
    return { wall: w, gross, opens, ends, net: Math.max(0, gross - opens) };
  });
  const sumGross = wallAreas.reduce((s, x) => s + x.gross, 0) || 1;
  const k = num(building.measure.roundCoef, 1) || 1;
  return wallAreas.map((x) => {
    const share = x.gross / sumGross;
    const paintSum = round2(totalPaint * share);
    const endsSum = round2(x.ends * 1100);
    return {
      label: x.wall.label,
      shape: x.wall.shape || "rect",
      length: num(x.wall.length),
      height: num(x.wall.height),
      gross: round2(x.gross),
      opens: round2(x.opens),
      net: round2(x.net),
      share,
      paintSum,
      endsSum,
      total: round2(paintSum + endsSum),
      priceM2,
      techId,
      k,
      note: x.wall.note || "",
      photos: (x.wall.photos || []).length,
    };
  });
}
