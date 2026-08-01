import {
  money,
  calcWallArea,
  migrateSurvey,
  syncAreasFromLists,
  buildEstimate,
  sideCostBreakdown,
  findPaintProduct,
  } from "./calc.js";
import { houseSvg, paintLiters } from "./house3d.js";
import { TECHNOLOGIES, HOUSE_TYPES, CONDITIONS } from "../data/tech-matrix.js";
import { OBJECT_KINDS, ROOF_TYPES } from "../data/objects.js";
import {
  pitchForPaint,
  pitchForTech,
  HOUSE_TYPE_PITCH,
  CONDITION_PITCH,
  WOW_LINES,
  paintIdKey,
} from "../data/pitch.js";

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
    const a = document.createElement("a");
    a.href = url;
    a.download = `KP_${(survey.client?.address || "object").replace(/\s+/g, "_")}.html`;
    a.click();
    alert("Всплывающие окна заблокированы — скачан HTML. Откройте файл и сохраните как PDF.");
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function logoMarkHtml() {
  return `<div class="logo-row">
    <svg class="logo-mark" width="38" height="38" viewBox="0 0 38 38">
      <circle cx="19" cy="19" r="17" fill="#121816"/>
      <circle cx="19" cy="19" r="17" fill="none" stroke="#9a7b32" stroke-width="1.4"/>
      <circle cx="19" cy="19" r="13" fill="none" stroke="#9a7b32" stroke-width=".6" opacity=".5"/>
      <text x="19" y="24" text-anchor="middle" font-family="Unbounded,sans-serif" font-size="12" font-weight="700" fill="#e6cf8a">BP</text>
    </svg>
    <div class="logo-word">BESTPAINTS<span>покраска деревянных домов</span></div>
  </div>`;
}

function buildReportHtml(survey, catalog) {
  const est = buildEstimate(survey, catalog);
  const areas = est.areas;
  const date = new Date().toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
  const primary = survey.buildings[0];
  const paintProd = findPaintProduct(catalog, primary?.tech?.paintId);
  const paintPitch = pitchForPaint(primary?.tech?.paintId);
  const techPitch = pitchForTech(primary?.tech?.techId);
  const warranty = paintProd?.warrantyYears45 || 5;
  const perYear =
    warranty > 0 && est.total > 0 ? Math.round(est.total / warranty / (areas.facade || 1)) : 0;
  const color = primary?.previewColor || "#c4a35a";
  const qr = `https://api.qrserver.com/v1/create-qr-code/?size=140x140&data=${encodeURIComponent(
    "https://www.bestpaints-bp.ru/?from=kp"
  )}`;

  const choicePages = survey.buildings.map((b, idx) => choicePage(b, catalog, est, idx + 1)).join("");
  const buildingPages = survey.buildings
    .map((b, idx) => buildingPage(b, catalog, idx + 1, survey.buildings.length))
    .join("");

  return `<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8"/>
<title>КП BestPaints — ${esc(survey.client?.address || "объект")}</title>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Unbounded:wght@500;600;700&display=swap" rel="stylesheet"/>
<style>
  :root { --ink:#1a1f1c; --muted:#5a6b60; --line:#d5ddd7; --gold:#9a7b32; --bg:#f7f5f0; --ok:#2f6b45; --deep:#121816; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:Manrope,system-ui,sans-serif; color:var(--ink); background:#e8ebe8; }
  .sheet {
    max-width: 820px; margin: 16px auto; background: white; padding: 28px 32px;
    box-shadow: 0 8px 40px rgba(0,0,0,.12); border-radius: 4px;
    animation: rise .45s ease both;
  }
  @keyframes rise { from { opacity:0; transform: translateY(8px);} to { opacity:1; transform:none;} }
  .brand { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:20px; }
  .brand h1 { font-family:Unbounded,sans-serif; font-size:1.4rem; margin:0 0 6px; letter-spacing:-.01em; }
  .brand p { margin:0; color:var(--muted); font-size:.9rem; }
  .logo-row { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
  .logo-mark { flex-shrink:0; }
  .logo-word { font-family:Unbounded,sans-serif; font-weight:700; color:var(--deep); font-size:1.05rem; letter-spacing:.06em; line-height:1; }
  .logo-word span { display:block; font-family:Manrope,sans-serif; font-weight:600; color:var(--gold); font-size:.62rem; letter-spacing:.14em; margin-top:2px; }
  .meta { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:16px 0; font-size:.92rem; }
  .meta div { background:var(--bg); padding:10px 12px; border-radius:8px; }
  .meta span { display:block; color:var(--muted); font-size:.72rem; margin-bottom:2px; }
  .hero-grid { display:grid; grid-template-columns:1.1fr .9fr; gap:16px; align-items:center; margin:18px 0; }
  .viz { background: linear-gradient(160deg,#1a221c,#0f1412); border-radius:12px; padding:8px; position:relative; overflow:hidden; }
  .viz::after { content:""; position:absolute; inset:-40% -20%; background:radial-gradient(circle at 30% 40%, ${esc(color)}55, transparent 55%); pointer-events:none; animation: glow 4s ease-in-out infinite alternate; }
  @keyframes glow { from { opacity:.55;} to { opacity:1;} }
  .viz svg { width:100%; height:auto; display:block; position:relative; z-index:1; }
  .kpis { display:grid; gap:8px; }
  .kpi { background:var(--bg); border-radius:10px; padding:12px; }
  .kpi b { display:block; font-size:1.25rem; margin-top:4px; font-family:Unbounded,sans-serif; }
  .kpi span { color:var(--muted); font-size:.75rem; }
  h2 { font-family:Unbounded,sans-serif; font-size:1.1rem; margin:24px 0 12px; letter-spacing:-.01em; }
  h2::before { content:""; display:inline-block; width:16px; height:2px; background:var(--gold); margin-right:8px; vertical-align:middle; }
  h3 { font-family:Unbounded,sans-serif; font-size:.92rem; margin:16px 0 8px; color:var(--gold); }
  table { width:100%; border-collapse:collapse; font-size:.86rem; }
  .table-wrap { border:1px solid var(--line); border-radius:12px; overflow:hidden; }
  .table-wrap table { margin:0; }
  th, td { text-align:left; padding:10px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--muted); font-size:.7rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em; background:#fbfaf6; }
  tbody tr:last-child td { border-bottom:none; }
  tbody tr:nth-child(even) { background:#fbfaf7; }
  .sum { font-weight:800; white-space:nowrap; }
  .totals { margin-top:12px; }
  .totals .row { display:flex; justify-content:space-between; padding:4px 0; color:var(--muted); }
  .totals .row.big { color:var(--ink); font-size:1.2rem; font-weight:800; margin-top:6px; }
  .note { font-size:.8rem; color:var(--muted); line-height:1.45; margin-top:16px; }
  .price-block {
    margin:16px 0; padding:20px 22px; border-radius:14px; display:flex; justify-content:space-between;
    align-items:center; gap:16px; flex-wrap:wrap;
    background:linear-gradient(135deg,#151b18,#243028); color:#f4efe4;
  }
  .price-block .label { font-size:.72rem; text-transform:uppercase; letter-spacing:.1em; opacity:.7; margin:0 0 6px; }
  .price-block .amount { font-family:Unbounded,sans-serif; font-size:1.9rem; font-weight:600; color:#e6cf8a; line-height:1; }
  .price-block .sub { font-size:.78rem; opacity:.75; margin-top:4px; }
  .page-break { page-break-before: always; break-before: page; }
  .chip { display:inline-block; background:#efe6d0; color:#6a5420; padding:3px 8px; border-radius:999px; font-size:.72rem; font-weight:700; margin-right:6px; margin-bottom:4px; }
  .chip.ok { background:#dceee2; color:#1f5a35; }
  .chip.gold { background:linear-gradient(120deg,#efe6d0,#f7efd8); }
  .toolbar { position:sticky; top:0; z-index:5; background:rgba(232,235,232,.95); padding:10px; display:flex; gap:8px; justify-content:center; backdrop-filter:blur(6px); }
  .toolbar button { border:none; background:#9a7b32; color:white; font-weight:700; padding:12px 18px; border-radius:999px; cursor:pointer; font-family:inherit; }
  .toolbar button.ghost { background:white; color:var(--ink); border:1px solid var(--line); }
  .wow {
    background: linear-gradient(135deg, #151b18 0%, #243028 55%, #3a2f18 100%);
    color: #f4efe4; border-radius: 16px; padding: 24px 22px; margin: 12px 0 18px;
    position: relative; overflow: hidden;
  }
  .wow::after {
    content:""; position:absolute; inset:0; pointer-events:none;
    background: radial-gradient(480px 200px at 100% 0%, rgba(212,181,106,.18), transparent 60%);
  }
  .wow h2 { color:#f0e2b8; margin:0 0 8px; font-size:1.2rem; position:relative; z-index:1; }
  .wow h2::before { display:none; }
  .wow p { margin:0; opacity:.92; line-height:1.55; position:relative; z-index:1; max-width:78%; }
  .wow .seal {
    position:absolute; right:20px; top:20px; width:64px; height:64px; border-radius:50%;
    display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center;
    background:radial-gradient(circle at 35% 30%, rgba(212,181,106,.25), rgba(0,0,0,.25));
    box-shadow:inset 0 0 0 1.5px #d4b56a, inset 0 0 0 5px rgba(212,181,106,.15);
    font-family:Unbounded,sans-serif; letter-spacing:.03em; z-index:1;
  }
  .wow .seal b { display:block; font-size:1.05rem; color:#f0e2b8; line-height:1; }
  .wow .seal span { display:block; font-size:.5rem; color:#d4b56a; letter-spacing:.08em; margin-top:2px; }
  .benefit-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin:12px 0; }
  .benefit {
    border:1px solid var(--line); border-radius:12px; padding:12px 14px; background:linear-gradient(180deg,#fff,#f9f7f2);
  }
  .benefit strong { display:block; margin-bottom:4px; }
  .benefit ul { margin:8px 0 0; padding-left:18px; color:var(--muted); font-size:.86rem; }
  .timeline { display:flex; gap:0; margin:14px 0; position:relative; }
  .timeline .step {
    flex:1; text-align:center; padding:14px 6px 10px; background:var(--bg); font-size:.78rem;
    position:relative; border-right:1px solid white;
  }
  .timeline .step::before {
    content:attr(data-n); position:absolute; top:-9px; left:50%; transform:translateX(-50%);
    width:18px; height:18px; border-radius:50%; background:var(--gold); color:#fff;
    font-size:.62rem; font-weight:800; display:flex; align-items:center; justify-content:center;
  }
  .timeline .step:first-child { border-radius:10px 0 0 10px; }
  .timeline .step:last-child { border-radius:0 10px 10px 0; border-right:none; }
  .timeline b { display:block; font-family:Unbounded,sans-serif; font-size:.95rem; color:var(--gold); }
  .invest {
    display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:14px 0;
  }
  .invest .box {
    background:var(--deep); color:#f3efe6; border-radius:12px; padding:14px; text-align:center;
  }
  .invest .box b { display:block; font-family:Unbounded,sans-serif; font-size:1.2rem; margin:6px 0 2px; color:#e6cf8a; }
  .invest .box span { font-size:.72rem; opacity:.8; }
  .qr-row { display:flex; gap:14px; align-items:center; margin-top:18px; padding:14px 16px; background:var(--bg); border-radius:12px; border:1px solid var(--line); }
  .qr-row img { width:80px; height:80px; border-radius:8px; background:white; padding:4px; }
  .qr-row strong { font-family:Unbounded,sans-serif; font-size:.88rem; font-weight:600; }
  .side-bar {
    height:8px; border-radius:99px; background:#ece7db; overflow:hidden; margin-top:4px;
  }
  .side-bar i { display:block; height:100%; background:linear-gradient(90deg,#9a7b32,#c4a35a); }
  @media print {
    body { background:white; }
    .toolbar { display:none !important; }
    .sheet { box-shadow:none; margin:0; max-width:none; border-radius:0; padding:12mm; animation:none; }
    .page-break { page-break-before: always; }
    .viz::after { animation:none; }
  }
  @media (max-width:700px) {
    .hero-grid, .meta, .benefit-grid, .invest { grid-template-columns:1fr; }
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
        ${logoMarkHtml()}
        <h1>Смета и презентация решения</h1>
        <p>${esc(survey.client?.address || "объект")} · ${date}</p>
      </div>
      <div style="text-align:right;font-size:.85rem;color:var(--muted)">
        www.bestpaints-bp.ru<br/>гарантия до 12 лет
      </div>
    </div>

    <div class="wow">
      <div class="seal"><b>${warranty}</b><span>лет гарантии</span></div>
      <h2>${esc(paintPitch.headline)}</h2>
      <p>${esc(paintPitch.wow)}</p>
      <p style="margin-top:10px;font-size:.9rem;opacity:.85;max-width:78%">${esc(WOW_LINES[0])}</p>
    </div>

    <div class="meta">
      <div><span>Заказчик</span><b>${esc(survey.client?.name || "—")}</b></div>
      <div><span>Телефон</span><b>${esc(survey.client?.phone || "—")}</b></div>
      <div><span>Адрес объекта</span><b>${esc(survey.client?.address || "—")}</b></div>
      <div><span>Замерщик</span><b>${esc(survey.client?.surveyor || "—")}</b></div>
    </div>

    <div class="hero-grid">
      <div class="viz">${houseSvg(primary, { width: 420, height: 260, color })}</div>
      <div class="kpis">
        <div class="kpi"><span>К покраске всего</span><b>${areas.paintTotal} м²</b></div>
        <div class="kpi"><span>Фасад / интерьер</span><b>${areas.facade} / ${areas.interior} м²</b></div>
        <div class="kpi"><span>Ориентир ЛКМ</span><b>~${paintLiters(areas.facade)} л</b></div>
      </div>
    </div>

    <div class="invest">
      <div class="box"><span>Защита на</span><b>${warranty} лет</b><span>${esc(techPitch.title)}</span></div>
      <div class="box"><span>≈ в год на м²</span><b>${perYear ? money(perYear) : "—"}</b><span>прозрачная экономика</span></div>
      <div class="box"><span>Строений</span><b>${survey.buildings.length}</b><span>в этой смете</span></div>
    </div>

    <h2>Итоговая смета</h2>
    <div class="table-wrap">
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
    </div>

    <div class="price-block">
      <div>
        <p class="label">К оплате, с НДС 5%</p>
        <div class="amount">${money(est.total)}</div>
        <p class="sub">Итого ${money(est.subtotal)}${Number(est.discountPct) > 0 ? ` · скидка ${est.discountPct}% (− ${money(est.subtotal - est.afterDiscount)})` : ""} · НДС 5% ${money(est.vat)}</p>
      </div>
    </div>

    <h2>Этапы оплаты</h2>
    <div class="timeline">
      <div class="step" data-n="1"><b>${esc(String(survey.estimate?.payments?.advance ?? 10))}%</b>договор</div>
      <div class="step" data-n="2"><b>${esc(String(survey.estimate?.payments?.second ?? 40))}%</b>выход бригады</div>
      <div class="step" data-n="3"><b>${esc(String(survey.estimate?.payments?.third ?? 40))}%</b>50% работ</div>
      <div class="step" data-n="4"><b>${esc(String(survey.estimate?.payments?.final ?? 10))}%</b>акт</div>
    </div>

    <div class="qr-row">
      <img src="${qr}" alt="QR BestPaints"/>
      <div>
        <strong>Сохраните КП и сайт BestPaints</strong>
        <p class="note" style="margin:4px 0 0">Наведите камеру — www.bestpaints-bp.ru. Документ для согласования; окончательная смета — приложение к договору.</p>
      </div>
    </div>
  </section>

  ${choicePages}
  ${buildingPages}
</body>
</html>`;
}

function choicePage(b, catalog, est, n) {
  syncAreasFromLists(b);
  const tech = TECHNOLOGIES.find((t) => t.id === b.tech?.techId);
  const coat = HOUSE_TYPES.find((t) => t.id === b.houseType);
  const cond = CONDITIONS.find((c) => c.id === b.condition);
  const product = findPaintProduct(catalog, b.tech?.paintId);
  const paintPitch = pitchForPaint(b.tech?.paintId);
  const techPitch = pitchForTech(b.tech?.techId);
  const sides = sideCostBreakdown(b, catalog);
  const facade = calcWallArea(b.measure, "facade").total;
  const color = b.previewColor || "#c4a35a";
  const warranty = product?.warrantyYears45 || 5;
  const maxSide = Math.max(...sides.map((s) => s.total), 1);

  return `
  <section class="sheet page-break">
    <div class="brand">
      <div>
        ${logoMarkHtml()}
        <h1>Почему это решение — правильное</h1>
        <p>${esc(b.name)} · строение ${n}</p>
      </div>
      <div>
        <span class="chip gold">${esc(product?.displayName || paintIdKey(b.tech?.paintId) || "ЛКМ")}</span>
        <span class="chip ok">гарантия до ${warranty} лет</span>
      </div>
    </div>

    <div class="wow">
      <h2>${esc(paintPitch.headline)}</h2>
      <p>${esc(paintPitch.wow)}</p>
    </div>

    <div class="benefit-grid">
      <div class="benefit">
        <strong>Что выбрали · ЛКМ</strong>
        <div class="chip">${esc(product?.brand || "")} ${esc(product?.displayName || "")}</div>
        <div class="chip">${product?.coating === "opaque" ? "Укрывной" : "Полупрозрачный"}</div>
        <div class="chip">${esc(product?.country || "")}</div>
        <ul>${paintPitch.benefits.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      </div>
      <div class="benefit">
        <strong>Что выбрали · технология</strong>
        <div class="chip">${esc(tech?.short || "")}</div>
        <p style="margin:8px 0 0;font-size:.88rem;color:var(--muted)">${esc(techPitch.why)}</p>
        <ul>${techPitch.benefits.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      </div>
      <div class="benefit">
        <strong>Состояние дома</strong>
        <p style="margin:0;font-size:.88rem">${esc(coat?.title || "")} · ${esc(cond?.title || "")}</p>
        <p style="margin:8px 0 0;font-size:.86rem;color:var(--muted)">${esc(
          HOUSE_TYPE_PITCH[b.houseType] || ""
        )}</p>
        <p style="margin:8px 0 0;font-size:.86rem;color:var(--muted)">${esc(
          CONDITION_PITCH[b.condition] || ""
        )}</p>
      </div>
      <div class="benefit">
        <strong>Цвет и визуализация</strong>
        <div style="display:flex;gap:10px;align-items:center;margin-top:8px">
          <span style="width:36px;height:36px;border-radius:50%;background:${esc(
            color
          )};border:2px solid #ddd;box-shadow:0 2px 8px rgba(0,0,0,.15)"></span>
          <span>${esc(b.colors || "цвет согласуем по вееру")}</span>
        </div>
        <div class="viz" style="margin-top:10px">${houseSvg(b, {
          width: 280,
          height: 160,
          color,
        })}</div>
      </div>
    </div>

    <h2>Из чего складывается цена по сторонам</h2>
    <p class="note" style="margin-top:0">${esc(WOW_LINES[1])} Фасад к покраске: <b>${facade.toFixed(
      1
    )} м²</b>.</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Сторона</th>
            <th>Размер</th>
            <th>Площадь</th>
            <th>Доля сметы</th>
            <th>Сумма</th>
          </tr>
        </thead>
        <tbody>
          ${
            sides.length
              ? sides
                  .map((s) => {
                    const pct = Math.round(s.share * 100);
                    const bar = Math.round((s.total / maxSide) * 100);
                    return `<tr>
              <td><b>${esc(s.label)}</b>
                <div class="side-bar"><i style="width:${bar}%"></i></div>
                ${s.note ? `<div style="font-size:.75rem;color:#666;margin-top:4px">${esc(s.note)}</div>` : ""}
              </td>
              <td>${s.length || "—"} × ${s.height || "—"} м</td>
              <td>${s.gross} м²${s.opens ? `<div style="font-size:.75rem;color:#666">− проёмы ${s.opens}</div>` : ""}</td>
              <td>${pct}%</td>
              <td class="sum">${money(s.total)}
                <div style="font-size:.72rem;color:#888">${money(s.priceM2)}/м² · техн. ${s.techId}</div>
              </td>
            </tr>`;
                  })
                  .join("")
              : `<tr><td colspan="5">Нет сторон фасада — заполните замер или загрузите чертёж</td></tr>`
          }
        </tbody>
      </table>
    </div>

    <h3>Обоснование цены</h3>
    <ul style="color:var(--muted);font-size:.9rem;line-height:1.5">
      <li>Цена за м² уже включает работу, расходники и выбранный ЛКМ по технологии <b>${esc(
        tech?.title || ""
      )}</b>.</li>
      <li>Дороже база (2 прохода) — потому что снимаем старое покрытие до древесины: это и есть фундамент гарантии ${warranty} лет.</li>
      <li>Дешевле «мойка» имеет смысл только при хорошем состоянии — иначе экономия сегодня превращается в переделку завтра.</li>
      <li>${esc(WOW_LINES[2])}</li>
    </ul>
  </section>`;
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
  const product = findPaintProduct(catalog, b.tech?.paintId);
  const paintName = product?.displayName || (b.tech?.paintId || "").split("::")[1] || "—";
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
        ${logoMarkHtml()}
        <h1>${esc(b.name)}</h1>
        <p>Замер · строение ${n} из ${total}</p>
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
    <div class="table-wrap">
      <table>
        <thead><tr><th>Плоскость</th><th>Площадь</th></tr></thead>
        <tbody>${planeRows || `<tr><td colspan="2">Нет данных</td></tr>`}</tbody>
      </table>
    </div>

    ${
      (b.measure.openings || []).length
        ? `<h2>Проёмы</h2>
    <div class="table-wrap">
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
      </table>
    </div>`
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
    </p>

    ${
      (b.photos || []).length
        ? `<h2>Фото / чертежи с объекта</h2>
    <div class="photo-row">
      ${b.photos
        .slice(0, 8)
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
