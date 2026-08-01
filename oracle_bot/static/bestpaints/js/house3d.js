import { num, calcWallArea, money } from "./calc.js";
import {
  TECHNOLOGIES,
  recommendTechs,
  getMatrixCell,
} from "../data/tech-matrix.js";
import { findPaintProduct, isPaintAllowedForCell } from "./calc.js";
import { OBJECT_KINDS, ROOF_TYPES } from "../data/objects.js";

/** Вытащить габариты строения из замеренных плоскостей */
export function inferBox(building) {
  const walls = building.measure?.walls || [];
  const facade = walls.filter((w) => (w.zone || "facade") === "facade");
  const lengths = facade.map((w) => num(w.length)).filter((n) => n > 0);
  const heights = facade.map((w) => num(w.height)).filter((n) => n > 0);
  const ridges = facade.map((w) => num(w.ridge)).filter((n) => n > 0);

  // эвристика: самая длинная = длина дома, вторая уникальная = ширина
  const sorted = [...new Set(lengths.map((n) => Math.round(n * 10) / 10))].sort((a, b) => b - a);
  const length = sorted[0] || 10;
  const width = sorted.find((n) => Math.abs(n - length) > 0.3) || sorted[1] || Math.max(6, length * 0.75);

  const hWall = heights.length ? heights.reduce((a, b) => a + b, 0) / heights.length : 3;
  const hRidge = ridges.length ? Math.max(...ridges) : hWall * 1.4;

  return {
    length,
    width,
    hWall,
    hRidge,
    area: calcWallArea(building.measure, "facade").total,
    kind: building.kind,
    roofType: building.roofType,
    name: building.name,
  };
}

/**
 * Изометрический «3D» домик SVG — печатается и смотрится «вау» без WebGL.
 */
export function houseSvg(building, opts = {}) {
  const box = inferBox(building);
  const w = opts.width || 340;
  const h = opts.height || 220;
  const paintColor = opts.color || building.previewColor || "#c4a35a";
  const roofColor = opts.roofColor || "#4a5560";

  // isometric unit
  const s = Math.min(w, h) / 18;
  const cx = w * 0.42;
  const cy = h * 0.72;

  const L = Math.min(7.5, 3.2 + box.length * 0.22);
  const D = Math.min(5.5, 2.4 + box.width * 0.18);
  const H = Math.min(4.2, 1.8 + box.hWall * 0.35);
  const Rh = Math.min(2.8, 0.8 + (box.hRidge - box.hWall) * 0.35);

  const iso = (x, y, z) => ({
    x: cx + (x - y) * s * 0.9,
    y: cy - z * s * 0.85 - (x + y) * s * 0.35,
  });

  const poly = (...pts) => pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  // box corners
  const A = iso(0, 0, 0);
  const B = iso(L, 0, 0);
  const C = iso(L, D, 0);
  const D0 = iso(0, D, 0);
  const At = iso(0, 0, H);
  const Bt = iso(L, 0, H);
  const Ct = iso(L, D, H);
  const Dt = iso(0, D, H);

  // roof ridge
  const showGable = ["gable", "broken", "complex"].includes(box.roofType);
  const Rfront = iso(L / 2, 0, H + Rh);
  const Rback = iso(L / 2, D, H + Rh);

  const leftFace = poly(At, Dt, D0, A);
  const rightFace = poly(Bt, Ct, C, B);
  const frontFace = poly(At, Bt, B, A);

  let roof = "";
  if (showGable) {
    roof = `
      <polygon points="${poly(At, Bt, Rfront)}" fill="${roofColor}" opacity="0.95"/>
      <polygon points="${poly(Bt, Ct, Rback, Rfront)}" fill="${shade(roofColor, -20)}" opacity="0.95"/>
      <polygon points="${poly(At, Dt, Rback, Rfront)}" fill="${shade(roofColor, 15)}" opacity="0.9"/>
      <polygon points="${poly(At, Bt, Rfront)}" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="1"/>
    `;
  } else {
    const Rf1 = iso(0, D / 2, H + Rh * 0.6);
    const Rf2 = iso(L, D / 2, H + Rh * 0.6);
    roof = `
      <polygon points="${poly(At, Bt, Rf2, Rf1)}" fill="${roofColor}" opacity="0.95"/>
      <polygon points="${poly(Dt, Ct, Rf2, Rf1)}" fill="${shade(roofColor, -25)}" opacity="0.9"/>
    `;
  }

  // windows hint
  const win1 = iso(L * 0.25, -0.02, H * 0.45);
  const win2 = iso(L * 0.45, -0.02, H * 0.45);
  const win3 = iso(L * 0.25, -0.02, H * 0.7);
  const win4 = iso(L * 0.45, -0.02, H * 0.7);

  const kindTitle = OBJECT_KINDS.find((k) => k.id === box.kind)?.title || "Объект";
  const roofTitle = ROOF_TYPES.find((r) => r.id === box.roofType)?.title || "";

  const walls = building.measure?.walls || [];
  const facadeWalls = walls.filter((x) => (x.zone || "facade") === "facade");
  // iso: front≈0, right≈1, left≈3 (back rarely visible)
  const faceMap = {
    front: facadeWalls[0]?.id || walls[0]?.id || "",
    right: facadeWalls[1]?.id || walls[1]?.id || "",
    left: facadeWalls[3]?.id || facadeWalls[2]?.id || walls[3]?.id || walls[2]?.id || "",
  };
  const activeId = opts.activeWallId || "";
  const interactive = !!opts.interactive;
  const faceStroke = (id) =>
    id && id === activeId
      ? 'stroke="#e0b86a" stroke-width="2.4" class="face-active"'
      : 'stroke="rgba(0,0,0,0.25)" stroke-width="0.8"';
  const faceCls = interactive ? "house-face" : "";
  const cursor = interactive ? 'style="cursor:pointer"' : "";

  return `
  <svg class="house-3d ${interactive ? "interactive" : ""}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Схема ${escapeXml(box.name)}">
    <defs>
      <linearGradient id="gnd" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="rgba(143,191,122,0.15)"/>
        <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
      </linearGradient>
    </defs>
    <ellipse cx="${cx}" cy="${cy + 8}" rx="${s * 8}" ry="${s * 1.6}" fill="url(#gnd)"/>
    <polygon class="${faceCls}" data-wall-id="${faceMap.left}" points="${leftFace}" fill="${shade(paintColor, -25)}" ${faceStroke(faceMap.left)} ${cursor}/>
    <polygon class="${faceCls}" data-wall-id="${faceMap.right}" points="${rightFace}" fill="${shade(paintColor, -10)}" ${faceStroke(faceMap.right)} ${cursor}/>
    <polygon class="${faceCls}" data-wall-id="${faceMap.front}" points="${frontFace}" fill="${paintColor}" ${faceStroke(faceMap.front)} ${cursor}/>
    <polygon points="${poly(win1, win2, win4, win3)}" fill="rgba(30,50,70,0.55)" stroke="rgba(255,255,255,0.2)" stroke-width="0.6" pointer-events="none"/>
    ${roof}
    <text x="12" y="22" fill="#eef3ef" font-size="13" font-family="Manrope,sans-serif" font-weight="700" pointer-events="none">${escapeXml(box.name)}</text>
    <text x="12" y="40" fill="#9aada2" font-size="11" font-family="Manrope,sans-serif" pointer-events="none">${escapeXml(kindTitle)} · ${escapeXml(roofTitle)}</text>
    <text x="12" y="${h - 14}" fill="#c4a35a" font-size="12" font-family="Manrope,sans-serif" font-weight="700" pointer-events="none">≈ ${box.length.toFixed(1)}×${box.width.toFixed(1)} м · фасад ${box.area.toFixed(1)} м²</text>
  </svg>`;
}

function shade(hex, amt) {
  const c = hex.replace("#", "");
  if (c.length !== 6) return hex;
  const n = (i) => Math.max(0, Math.min(255, parseInt(c.slice(i, i + 2), 16) + amt));
  return `#${[n(0), n(2), n(4)].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function escapeXml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Сравнение технологий подготовки на текущей площади: цена и гарантия по вариантам */
export function techCompareHtml(building, catalog) {
  const area = calcWallArea(building.measure, "facade").total;
  if (area <= 0 || !building.tech?.paintId) {
    return `<div class="callout">Выберите ЛКМ — покажем разницу технологий в рублях на вашу площадь.</div>`;
  }
  const product = findPaintProduct(catalog, building.tech.paintId);
  if (!product) return "";

  const name = (product.name || "").toLowerCase();
  const paintOpt = {
    id: building.tech.paintId,
    name: product.displayName || product.name,
    fullName: product.name,
    opacity: product.coating || (name.includes("укрывн") ? "opaque" : "semi"),
  };
  const allowedTechs = recommendTechs(building.houseType, building.condition, building.material);
  const rows = allowedTechs
    .map((t) => {
      const cell = getMatrixCell(building.houseType, building.condition, t.id);
      if (!isPaintAllowedForCell(paintOpt, cell)) return null;
      const item = product.items.find((i) => i.tech === t.id);
      if (!item || !(item.price > 0)) return null;
      const sum = item.price * area;
      return { t, item, sum };
    })
    .filter(Boolean);

  if (rows.length < 2) return "";

  const selected = building.tech.techId;
  // База — техн.4 для нового дома, техн.5 для ранее окрашенного (см. recommendTechs).
  const preferredId = building.houseType === "new" ? 4 : 5;
  const base = rows.find((r) => r.t.id === preferredId) || rows.find((r) => r.t.isBase) || rows[rows.length - 1];
  const cheaper = rows.filter((r) => r.sum < base.sum).sort((a, b) => b.sum - a.sum)[0];
  const pricier = rows.filter((r) => r.sum > base.sum).sort((a, b) => a.sum - b.sum)[0];

  const tips = [];
  if (cheaper) {
    tips.push(
      `«${cheaper.t.short}» дешевле на ${money(base.sum - cheaper.sum)}, но гарантия ${yearsLabel(cheaper.item.guarantee)} вместо ${yearsLabel(base.item.guarantee)} на «${base.t.short}»`
    );
  }
  if (pricier) {
    const reason =
      pricier.t.id === 5
        ? "на ранее окрашенном доме старое покрытие снимают полностью, иначе новый слой не приляжет"
        : "это более глубокая подготовка поверхности";
    tips.push(`«${pricier.t.short}» дороже на ${money(pricier.sum - base.sum)} — ${reason}`);
  }

  return `
    <div class="compare-tech">
      <h3 class="subhead">Сравнение на ${area.toFixed(0)} м² · ${escapeXml(product.name.split(" - ")[0])}</h3>
      <p class="section-sub">Что входит в подготовку на этой площади — цена и гарантия по вариантам.</p>
      <div class="compare-rows">
        ${rows
          .map((r) => {
            const diff = r.sum - base.sum;
            const isSel = r.t.id === selected;
            const isBase = r.t.id === base.t.id;
            return `
            <div class="compare-row ${isSel ? "selected" : ""} ${isBase ? "base" : ""}">
              <div>
                <strong>${r.t.short}${isBase ? " ★ база" : ""}</strong>
                <div class="hint">гарантия ${r.item.guarantee || "—"} лет · ${money(r.item.price)}/м²</div>
              </div>
              <div class="compare-sum">
                <b>${money(r.sum)}</b>
                <span class="hint">${diff === 0 ? "база" : diff > 0 ? "+" + money(diff) : money(diff)}</span>
              </div>
            </div>`;
          })
          .join("")}
      </div>
      ${tips.length ? `<div class="callout ok">Клиенту: ${tips.join(". ")}.</div>` : ""}
    </div>
  `;
}

function yearsLabel(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return String(n ?? "—");
  const mod10 = v % 10;
  const mod100 = v % 100;
  if (mod10 === 1 && mod100 !== 11) return `${v} год`;
  if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return `${v} года`;
  return `${v} лет`;
}

/** Расход ЛКМ roughly: 1 л / 7.5 м² на 2 слоя (из описания ЛКМ BestPaints) */
export function paintLiters(areaM2) {
  if (!areaM2) return 0;
  return Math.ceil((areaM2 / 7.5) * 10) / 10;
}
