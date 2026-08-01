/** Замер и смета из чертежей заказчика — AI-распознавание + применение к стенам. */

import { uid } from "./calc.js";
import { compressImageFile } from "./photos.js";

const API = "/bestpaints/api/parse-drawing";

export function drawingsPanelHtml(state = {}) {
  const last = state.lastParse;
  const conf = last?.confidence != null ? Math.round(last.confidence * 100) : null;
  return `
    <div class="drawings-card" id="drawings-card">
      <div class="scale-head">
        <strong>Чертёж заказчика → замер</strong>
        <span class="hint">Фасад / план с размерами · AI читает длины, высоты, проёмы</span>
      </div>
      <div class="field">
        <label>Фото или скан чертежа (JPG/PNG)</label>
        <input type="file" id="dw-file" accept="image/*" />
      </div>
      <div class="field">
        <label>Подсказка (необязательно)</label>
        <input id="dw-hint" value="${escAttr(state.hint || "")}" placeholder="напр. размеры в мм, фасад со двора" />
      </div>
      <div class="scale-actions">
        <button type="button" class="btn primary" id="dw-parse">Распознать чертёж</button>
      </div>
      <div id="dw-status" class="hint" style="margin-top:8px">
        ${
          last
            ? `Последний разбор: ${last.walls?.length || 0} стен · ${last.openings?.length || 0} проёмов${conf != null ? ` · ~${conf}%` : ""}`
            : "Загрузите чертёж — после проверки размеры попадут в плоскости замера."
        }
      </div>
      <div id="dw-result" class="dw-result" style="${last ? "" : "display:none"}"></div>
    </div>
  `;
}

function escAttr(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;");
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderResult(el, data) {
  if (!el || !data) return;
  const walls = (data.walls || [])
    .map(
      (w, i) => `<tr>
      <td><label style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-dw-wall="${i}" checked style="width:auto"/> ${esc(w.label)}</label></td>
      <td>${w.length ?? "—"} × ${w.height ?? "—"} м · ${esc(w.shape)}</td>
      <td>${Math.round((w.confidence || 0) * 100)}%</td>
    </tr>`
    )
    .join("");
  const opens = (data.openings || [])
    .map(
      (o, i) => `<tr>
      <td><label style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-dw-open="${i}" checked style="width:auto"/> ${esc(o.label)}</label></td>
      <td>${esc(o.wallLabel)} · ${o.width}×${o.height} м</td>
    </tr>`
    )
    .join("");
  el.style.display = "block";
  el.innerHTML = `
    <div class="callout ok" style="margin-top:10px">
      <b>${esc(data.drawingType || "чертёж")}</b>
      ${data.notes ? ` — ${esc(data.notes)}` : ""}
      ${data.scaleHint ? `<div class="hint">Масштаб: ${esc(data.scaleHint)}</div>` : ""}
    </div>
    <table class="table" style="margin-top:8px;font-size:.85rem">
      <thead><tr><th>Стена</th><th>Размер</th><th>AI</th></tr></thead>
      <tbody>${walls || "<tr><td colspan=3>Нет стен</td></tr>"}</tbody>
    </table>
    ${
      opens
        ? `<table class="table" style="font-size:.85rem"><thead><tr><th>Проём</th><th>Размер</th></tr></thead><tbody>${opens}</tbody></table>`
        : ""
    }
    <label class="choice" style="display:flex;gap:8px;margin:10px 0;align-items:center">
      <input type="checkbox" id="dw-replace" checked style="width:auto"/>
      <span>Заменить текущие плоскости (иначе добавить)</span>
    </label>
    <button type="button" class="btn primary block" id="dw-apply">Применить к замеру</button>
  `;
}

export function applyDrawingParse(building, data, { replace = true, wallIdx = null, openIdx = null } = {}) {
  if (!building?.measure || !data) return { walls: 0, openings: 0 };
  const m = building.measure;
  const selectedWalls = (data.walls || []).filter((_, i) => !wallIdx || wallIdx.has(i));
  const selectedOpens = (data.openings || []).filter((_, i) => !openIdx || openIdx.has(i));

  const newWalls = selectedWalls.map((w) => ({
    id: uid(),
    label: w.label || "Стена",
    shape: w.shape || "rect",
    length: w.length != null ? String(w.length) : "",
    height: w.height != null ? String(w.height) : "",
    ridge: w.ridge != null ? String(w.ridge) : "",
    height2: w.height2 != null ? String(w.height2) : "",
    areaManual: "",
    zone: w.zone === "interior" ? "interior" : "facade",
    material: building.material || "",
    condition: "",
    coatingWant: "",
    note: "из чертежа",
    photos: [],
    flags: {},
    damageArea: "",
    endsLength: "",
    soffitArea: "",
    fasciaArea: "",
    warmSeam: "",
    trimLength: "",
    doborLength: "",
    attention: {},
  }));

  if (replace && newWalls.length) m.walls = newWalls;
  else if (newWalls.length) m.walls = [...(m.walls || []), ...newWalls];

  const byLabel = new Map((m.walls || []).map((w) => [String(w.label).toLowerCase(), w]));
  const openings = [];
  for (const o of selectedOpens) {
    const key = String(o.wallLabel || "").toLowerCase();
    const wall =
      byLabel.get(key) ||
      (m.walls || []).find((w) => key && String(w.label).toLowerCase().includes(key)) ||
      (m.walls || [])[0];
    openings.push({
      id: uid(),
      wallId: wall?.id || "",
      label: o.label || "Проём",
      width: String(o.width),
      height: String(o.height),
      kind: o.kind || "window",
      needsWarm: false,
      note: "из чертежа",
    });
  }
  if (replace) m.openings = openings;
  else m.openings = [...(m.openings || []), ...openings];

  const ex = data.extras || {};
  if (ex.soffitArea != null) m.soffitArea = String(ex.soffitArea);
  if (ex.fasciaArea != null) m.fasciaArea = String(ex.fasciaArea);
  if (ex.endsLength != null) m.endsLength = String(ex.endsLength);
  if (ex.overhangArea != null) m.overhangArea = String(ex.overhangArea);

  if (data.suggestedHouseType && ["new", "non_film", "film"].includes(data.suggestedHouseType)) {
    building.houseType = data.suggestedHouseType;
  }
  if (
    data.suggestedMaterial &&
    ["beam", "log", "hand_log", "imit", "block", "board", "other"].includes(data.suggestedMaterial)
  ) {
    building.material = data.suggestedMaterial;
  }

  building.photos = building.photos || [];
  if (data._previewDataUrl && !building.photos.some((p) => p.fromDrawing)) {
    building.photos.unshift({
      id: uid(),
      dataUrl: data._previewDataUrl,
      note: "Чертёж заказчика",
      fromDrawing: true,
    });
  }

  return { walls: newWalls.length, openings: openings.length };
}

export function bindDrawingsPanel(root, { getBuilding, getState, setState, onApplied, toast } = {}) {
  const card = root.querySelector("#drawings-card");
  if (!card) return;
  if (card.dataset.bound === "1") return;
  card.dataset.bound = "1";

  let lastParse = getState?.()?.lastParse || null;
  if (lastParse) renderResult(root.querySelector("#dw-result"), lastParse);

  const setBusy = (busy, msg) => {
    const btn = root.querySelector("#dw-parse");
    if (btn) {
      btn.disabled = busy;
      btn.textContent = busy ? "Распознаём…" : "Распознать чертёж";
    }
    const st = root.querySelector("#dw-status");
    if (st && msg) st.textContent = msg;
  };

  root.querySelector("#dw-hint")?.addEventListener("change", (e) => {
    setState?.({ ...(getState?.() || {}), hint: e.target.value });
  });

  root.querySelector("#dw-parse")?.addEventListener("click", async () => {
    const file = root.querySelector("#dw-file")?.files?.[0];
    if (!file) {
      toast?.("Выберите файл чертежа");
      return;
    }
    const hint = root.querySelector("#dw-hint")?.value || "";
    setBusy(true, "Сжимаем и отправляем на распознавание…");
    try {
      const compressed = await compressImageFile(file);
      const dataUrl = typeof compressed === "string" ? compressed : compressed?.dataUrl;
      if (!dataUrl) throw new Error("Не удалось прочитать изображение");

      const res = await fetch(API, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ imageDataUrl: dataUrl, hint }),
      });
      if (res.status === 401) {
        location.href = "/bestpaints/login";
        return;
      }
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = payload.detail;
        const msg = typeof detail === "string" ? detail : payload.message || "Ошибка распознавания";
        throw new Error(msg);
      }

      lastParse = { ...payload, _previewDataUrl: dataUrl };
      setState?.({ hint, lastParse });
      renderResult(root.querySelector("#dw-result"), lastParse);
      setBusy(
        false,
        `Готово: ${lastParse.walls?.length || 0} стен · ${lastParse.openings?.length || 0} проёмов — проверьте и примените`
      );
    } catch (e) {
      console.error(e);
      setBusy(false, e.message || String(e));
      toast?.(e.message || "Ошибка распознавания");
    }
  });

  root.addEventListener("click", (e) => {
    const btn = e.target.closest("#dw-apply");
    if (!btn || !root.contains(btn)) return;
    if (!lastParse) {
      toast?.("Сначала распознайте чертёж");
      return;
    }
    const wallIdx = new Set(
      [...root.querySelectorAll("[data-dw-wall]:checked")].map((el) => Number(el.dataset.dwWall))
    );
    const openIdx = new Set(
      [...root.querySelectorAll("[data-dw-open]:checked")].map((el) => Number(el.dataset.dwOpen))
    );
    const replace = !!root.querySelector("#dw-replace")?.checked;
    const b = getBuilding?.();
    const r = applyDrawingParse(b, lastParse, { replace, wallIdx, openIdx });
    onApplied?.(r, lastParse);
  });
}
