import { money, calcWallArea, migrateSurvey, syncAreasFromLists, buildEstimate } from "./calc.js";
import { houseSvg, paintLiters } from "./house3d.js";
import { TECHNOLOGIES, HOUSE_TYPES, CONDITIONS } from "../data/tech-matrix.js";
import { OBJECT_KINDS, ROOF_TYPES } from "../data/objects.js";

export function openClientReport(survey, catalog) {
  migrateSurvey(survey);
  let html;
  try {
    html = buildReportHtml(survey, catalog);
  } catch (e) {
    alert("Не удалось собрать отчёт: " + (e?.message || e));
    console.error(e);
    return;
  }
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const w = window.open(url, "_blank");
  if (!w) {
    // fallback: download
    const a = document.createElement("a");
    a.href = url;
    a.download = `KP_${(survey.client?.address || "object").replace(/\s+/g, "_")}.html`;
    a.click();
    alert("Всплывающие окна заблокированы — скачан HTML. Откройте файл и сохраните как PDF.");
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function buildReportHtml(survey, catalog) {
  const est = buildEstimate(survey, catalog);
  const areas = est.areas;
  const date = new Date().toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  const buildingPages = survey.buildings
    .map((b, idx) => buildingPage(b, catalog, idx + 1, survey.buildings.length))
    .join("");

  return `<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"/>
<title>КП / Замер — ${esc(survey.client?.address || "объект")}</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Unbounded:wght@500;600&display=swap" rel="stylesheet"/>
<style>
  :root { --ink:#1a1f1c; --muted:#5a6b60; --line:#d5ddd7; --gold:#9a7b32; --bg:#f7f5f0; --ok:#2f6b45; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:Manrope,system-ui,sans-serif; color:var(--ink); background:#e8ebe8; }
  .sheet {
    max-width: 820px; margin: 16px auto; background: white; padding: 28px 32px;
    box-shadow: 0 8px 40px rgba(0,0,0,.12); border-radius: 4px;
  }
  .brand { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:20px; }
  .brand h1 { font-family:Unbounded,sans-serif; font-size:1.35rem; margin:0 0 6px; }
  .brand p { margin:0; color:var(--muted); font-size:.9rem; }
  .logo { font-family:Unbounded,sans-serif; font-weight:600; color:var(--gold); font-size:1rem; letter-spacing:.04em; }
  .meta { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:16px 0; font-size:.92rem; }
  .meta div { background:var(--bg); padding:10px 12px; border-radius:8px; }
  .meta span { display:block; color:var(--muted); font-size:.72rem; margin-bottom:2px; }
  .hero-grid { display:grid; grid-template-columns:1.1fr .9fr; gap:16px; align-items:center; margin:18px 0; }
  .viz { background: linear-gradient(160deg,#1a221c,#0f1412); border-radius:12px; padding:8px; }
  .viz svg { width:100%; height:auto; display:block; }
  .kpis { display:grid; gap:8px; }
  .kpi { background:var(--bg); border-radius:10px; padding:12px; }
  .kpi b { display:block; font-size:1.25rem; margin-top:4px; font-family:Unbounded,sans-serif; }
  .kpi span { color:var(--muted); font-size:.75rem; }
  h2 { font-family:Unbounded,sans-serif; font-size:1.05rem; margin:22px 0 10px; }
  table { width:100%; border-collapse:collapse; font-size:.86rem; }
  th, td { text-align:left; padding:8px 6px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--muted); font-size:.72rem; font-weight:700; }
  .sum { font-weight:800; white-space:nowrap; }
  .totals { margin-top:12px; }
  .totals .row { display:flex; justify-content:space-between; padding:4px 0; color:var(--muted); }
  .totals .row.big { color:var(--ink); font-size:1.2rem; font-weight:800; margin-top:6px; }
  .note { font-size:.8rem; color:var(--muted); line-height:1.45; margin-top:16px; }
  .page-break { page-break-before: always; break-before: page; }
  .chip { display:inline-block; background:#efe6d0; color:#6a5420; padding:3px 8px; border-radius:999px; font-size:.72rem; font-weight:700; margin-right:6px; }
  .toolbar { position:sticky; top:0; z-index:5; background:rgba(232,235,232,.95); padding:10px; display:flex; gap:8px; justify-content:center; backdrop-filter:blur(6px); }
  .toolbar button { border:none; background:#9a7b32; color:white; font-weight:700; padding:12px 18px; border-radius:999px; cursor:pointer; font-family:inherit; }
  .toolbar button.ghost { background:white; color:var(--ink); border:1px solid var(--line); }
  @media print {
    body { background:white; }
    .toolbar { display:none !important; }
    .sheet { box-shadow:none; margin:0; max-width:none; border-radius:0; padding:12mm; }
    .page-break { page-break-before: always; }
  }
  @media (max-width:700px) {
    .hero-grid, .meta { grid-template-columns:1fr; }
    .sheet { margin:0; border-radius:0; }
  }
</style>
</head>
<body>
  <div class="toolbar no-print">
    <button onclick="window.print()">Печать / сохранить PDF</button>
    <button class="ghost" onclick="window.close()">Закрыть</button>
  </div>

  <section class="sheet">
    <div class="brand">
      <div>
        <div class="logo">BESTPAINTS</div>
        <h1>Замер и предварительная смета</h1>
        <p>Покраска деревянных домов · ${date}</p>
      </div>
      <div style="text-align:right;font-size:.85rem;color:var(--muted)">
        www.bestpaints-bp.ru<br/>гарантия до 12 лет
      </div>
    </div>

    <div class="meta">
      <div><span>Заказчик</span><b>${esc(survey.client?.name || "—")}</b></div>
      <div><span>Телефон</span><b>${esc(survey.client?.phone || "—")}</b></div>
      <div><span>Адрес объекта</span><b>${esc(survey.client?.address || "—")}</b></div>
      <div><span>Замерщик</span><b>${esc(survey.client?.surveyor || "—")}</b></div>
    </div>

    <div class="hero-grid">
      <div class="viz">${houseSvg(survey.buildings[0], { width: 420, height: 260 })}</div>
      <div class="kpis">
        <div class="kpi"><span>К покраске всего</span><b>${areas.paintTotal} м²</b></div>
        <div class="kpi"><span>Фасад / интерьер</span><b>${areas.facade} / ${areas.interior} м²</b></div>
        <div class="kpi"><span>Строений</span><b>${survey.buildings.length}</b></div>
        <div class="kpi"><span>Ориентир ЛКМ (фасад)</span><b>~${paintLiters(areas.facade)} л</b></div>
      </div>
    </div>

    <h2>Итоговая смета</h2>
    <table>
      <thead><tr><th>Работа</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr></thead>
      <tbody>
        ${est.lines
          .map(
            (l) => `<tr>
          <td>${esc(l.name)}${l.guarantee ? `<div style="color:var(--muted);font-size:.75rem">гарантия ${l.guarantee} лет</div>` : ""}</td>
          <td>${l.qty} ${esc(l.unit)}</td>
          <td>${money(l.price)}</td>
          <td class="sum">${money(l.sum)}</td>
        </tr>`
          )
          .join("")}
      </tbody>
    </table>
    <div class="totals">
      <div class="row"><span>Итого</span><span>${money(est.subtotal)}</span></div>
      <div class="row"><span>Скидка ${est.discountPct}%</span><span>− ${money(est.subtotal - est.afterDiscount)}</span></div>
      <div class="row"><span>НДС 5%</span><span>${money(est.vat)}</span></div>
      <div class="row big"><span>К оплате</span><span>${money(est.total)}</span></div>
    </div>
    <p class="note">
      Оплата: 10% при договоре → 40% выход бригады → 40% на 50% работ → 10% акт.
      Документ сформирован на объекте по фактическим замерам. Окончательная смета — приложение к договору.
    </p>
  </section>

  ${buildingPages}
</body>
</html>`;
}

function buildingPage(b, catalog, n, total) {
  syncAreasFromLists(b);
  const facade = calcWallArea(b.measure, "facade").total;
  const interior = calcWallArea(b.measure, "interior").total;
  const tech = TECHNOLOGIES.find((t) => t.id === b.tech?.techId);
  const techInt = TECHNOLOGIES.find((t) => t.id === (b.tech?.techIdInterior || b.tech?.techId));
  const kind = OBJECT_KINDS.find((k) => k.id === b.kind)?.title || "";
  const roof = ROOF_TYPES.find((r) => r.id === b.roofType)?.title || "";
  const coat = HOUSE_TYPES.find((t) => t.id === b.houseType)?.title || "";
  const cond = CONDITIONS.find((c) => c.id === b.condition)?.title || "";
  const paintName = (b.tech?.paintId || "").split("::")[1] || "—";
  const paintInt = (b.tech?.paintIdInterior || "").split("::")[1] || paintName;

  const planeRows = (b.measure.walls || [])
    .map((w) => {
      const area = planeArea(w);
      const mat = w.material || "—";
      const ph = (w.photos || []).length;
      const note = (w.note || "").trim();
      const flags = Object.entries(w.flags || {})
        .filter(([, v]) => v)
        .map(([k]) => k)
        .join(", ");
      return `<tr>
        <td>${esc(w.label)} <span style="color:#888;font-size:.75rem">(${esc(w.shape || "rect")} · ${w.zone === "interior" ? "внутри" : "снаружи"} · мат: ${esc(mat)}${ph ? ` · фото ${ph}` : ""}${flags ? ` · ${esc(flags)}` : ""})</span>${note ? `<div style="margin-top:4px;font-size:.82rem;color:#444">💬 ${esc(note)}</div>` : ""}${num(w.damageArea) ? `<div style="font-size:.8rem;color:#a65">Ремонт ${num(w.damageArea)} м²</div>` : ""}</td>
        <td>${area.toFixed(1)} м²</td>
      </tr>`;
    })
    .join("");

  const wallPhotoStrip = (b.measure.walls || [])
    .flatMap((w) => (w.photos || []).slice(0, 2).map((p) => ({ ...p, wall: w.label })))
    .slice(0, 8)
    .map(
      (p) =>
        `<figure style="margin:0;display:inline-block"><img src="${p.dataUrl}" alt="" style="width:100px;height:75px;object-fit:cover;border-radius:6px"/><figcaption style="font-size:10px;color:#666">${esc(p.wall)}</figcaption></figure>`
    )
    .join("");

  return `
  <section class="sheet page-break">
    <div class="brand">
      <div>
        <div class="logo">BESTPAINTS</div>
        <h1>${esc(b.name)}</h1>
        <p>Строение ${n} из ${total}</p>
      </div>
      <div>
        <span class="chip">${esc(kind)}</span>
        <span class="chip">${esc(roof)}</span>
      </div>
    </div>

    <div class="hero-grid">
      <div class="viz">${houseSvg(b, { width: 420, height: 250, color: b.previewColor || (b.zones?.facade ? "#c4a35a" : "#8fbf7a") })}</div>
      <div class="kpis">
        ${b.zones?.facade ? `<div class="kpi"><span>Фасад к покраске</span><b>${facade.toFixed(1)} м²</b></div>` : ""}
        ${b.zones?.interior ? `<div class="kpi"><span>Интерьер стены</span><b>${interior.toFixed(1)} м²</b></div>` : ""}
        ${num(b.measure.soffitArea) ? `<div class="kpi"><span>Подшива</span><b>${num(b.measure.soffitArea)} м²</b></div>` : ""}
        ${num(b.measure.ceilingArea) ? `<div class="kpi"><span>Потолки</span><b>${num(b.measure.ceilingArea)} м²</b></div>` : ""}
        ${num(b.measure.warmSeamTotal) ? `<div class="kpi"><span>Тёплый шов</span><b>${num(b.measure.warmSeamTotal)} пог.м</b></div>` : ""}
        <div class="kpi"><span>Ориентир ЛКМ</span><b>~${paintLiters(facade + interior)} л</b></div>
      </div>
    </div>

    <h2>Состояние и технология</h2>
    <div class="meta">
      <div><span>Покрытие сейчас</span><b>${esc(coat)}</b></div>
      <div><span>Состояние</span><b>${esc(cond)}</b></div>
      <div><span>Влажность</span><b>${esc(b.humidity ? b.humidity + " %" : "—")}</b></div>
      <div><span>Цвет</span><b>${esc(b.colors || "—")}</b></div>
    </div>

    ${
      b.zones?.facade
        ? `<h2>Фасад</h2>
    <div class="meta">
      <div><span>Технология</span><b>${esc(tech?.title || "—")}</b></div>
      <div><span>ЛКМ</span><b>${esc(paintName)}</b></div>
    </div>`
        : ""
    }

    ${
      b.zones?.interior
        ? `<h2>Интерьер</h2>
    <div class="meta">
      <div><span>Технология</span><b>${esc(techInt?.title || "—")}</b></div>
      <div><span>ЛКМ</span><b>${esc(paintInt)}</b></div>
    </div>`
        : ""
    }

    <h2>Плоскости замера</h2>
    <table>
      <thead><tr><th>Плоскость</th><th>Площадь</th></tr></thead>
      <tbody>${planeRows || `<tr><td colspan="2">Нет данных</td></tr>`}</tbody>
    </table>

    ${
      (b.measure.openings || []).length
        ? `<h2>Проёмы</h2>
    <table>
      <thead><tr><th>Проём</th><th>Размер</th></tr></thead>
      <tbody>
        ${(b.measure.openings || [])
          .map((o) => {
            const wall = (b.measure.walls || []).find((w) => w.id === o.wallId);
            return `<tr><td>${esc(o.label)}${wall ? ` · ${esc(wall.label)}` : ""}${o.note ? `<div style="font-size:.8rem;color:#666">${esc(o.note)}</div>` : ""}</td>
            <td>${esc(o.width)}×${esc(o.height)} м${o.needsWarm ? " · шов" : ""}</td></tr>`;
          })
          .join("")}
      </tbody>
    </table>`
        : ""
    }

    ${
      wallPhotoStrip
        ? `<h2>Фото по сторонам</h2><div style="display:flex;flex-wrap:wrap;gap:8px">${wallPhotoStrip}</div>`
        : ""
    }

    <p class="note">
      K закругления: ${esc(String(b.measure.roundCoef || 1))}.
      Формула фасада: (Sстен − Sпроёмов + Sторцов) × K.
      Документ для согласования с заказчиком на объекте.
    </p>

    ${
      (b.photos || []).length
        ? `<h2>Фото с объекта</h2>
    <div class="photo-row">
      ${b.photos
        .slice(0, 6)
        .map((p) => `<img src="${p.dataUrl}" alt="фото" style="width:120px;height:90px;object-fit:cover;border-radius:8px;margin:4px"/>`)
        .join("")}
    </div>`
        : ""
    }
  </section>`;
}

function planeArea(side) {
  const shape = side.shape || "rect";
  const n = (v) => {
    const x = parseFloat(String(v).replace(",", "."));
    return Number.isFinite(x) ? x : 0;
  };
  if (shape === "custom") return Math.max(0, n(side.areaManual));
  const L = n(side.length);
  const H = n(side.height);
  if (shape === "gable") {
    const ridge = n(side.ridge);
    return Math.max(0, L * H + (L * Math.max(0, ridge - H)) / 2);
  }
  if (shape === "trap") {
    const H2 = n(side.height2) || H;
    return Math.max(0, (L * (H + H2)) / 2);
  }
  return Math.max(0, L * H);
}

function num(v) {
  const x = parseFloat(String(v).replace(",", "."));
  return Number.isFinite(x) ? x : 0;
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
