import { money, totalAreas, migrateSurvey, calcWallArea, syncAreasFromLists } from "./calc.js";
import { TECHNOLOGIES } from "../data/tech-matrix.js";
import { paintLiters } from "./house3d.js";
import { buildEstimate } from "./calc.js";
import { readiness } from "./quality.js";

export function buildShareText(survey, catalog) {
  migrateSurvey(survey);
  const est = buildEstimate(survey, catalog);
  const a = est.areas;
  const r = readiness(survey);
  const lines = [
    `🏠 BestPaints — замер`,
    `📍 ${survey.client?.address || "адрес не указан"}`,
    `👤 ${survey.client?.name || "—"} ${survey.client?.phone ? "· " + survey.client.phone : ""}`,
    ``,
    `Строений: ${survey.buildings.length}`,
    `К покраске: ${a.paintTotal} м² (фасад ${a.facade} · интерьер ${a.interior})`,
    a.warm ? `Тёплый шов: ${a.warm} пог.м` : null,
    `Ориентир ЛКМ: ~${paintLiters(a.facade + a.interior)} л`,
    ``,
  ].filter((x) => x !== null);

  for (const b of survey.buildings) {
    syncAreasFromLists(b);
    const tech = TECHNOLOGIES.find((t) => t.id === b.tech?.techId);
    const paint = (b.tech?.paintId || "").split("::")[1] || "ЛКМ не выбран";
    lines.push(`▸ ${b.name}: ${calcWallArea(b.measure, "facade").total.toFixed(1)} м² фасад`);
    lines.push(`  ${tech?.short || "техн.?"} · ${paint}`);
  }

  lines.push(``);
  lines.push(`💰 К оплате (предварительно): ${money(est.total)} (с НДС 5%)`);
  lines.push(`Готовность замера: ${r.pct}%`);
  lines.push(``);
  lines.push(`www.bestpaints-bp.ru`);
  return lines.join("\n");
}

export async function copyShareText(survey, catalog) {
  const text = buildShareText(survey, catalog);
  try {
    await navigator.clipboard.writeText(text);
    return { ok: true, text };
  } catch {
    return { ok: false, text };
  }
}

export function shareTelegram(survey, catalog) {
  const text = buildShareText(survey, catalog);
  const url = `https://t.me/share/url?url=${encodeURIComponent("https://www.bestpaints-bp.ru/")}&text=${encodeURIComponent(text)}`;
  window.open(url, "_blank");
}

export function shareWhatsApp(survey, catalog) {
  const text = buildShareText(survey, catalog);
  const url = `https://wa.me/?text=${encodeURIComponent(text)}`;
  window.open(url, "_blank");
}

export async function nativeShare(survey, catalog) {
  const text = buildShareText(survey, catalog);
  if (!navigator.share) return { ok: false, text };
  try {
    await navigator.share({ title: "Замер BestPaints", text });
    return { ok: true, text };
  } catch {
    return { ok: false, text };
  }
}
