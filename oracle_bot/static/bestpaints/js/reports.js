/** Отчёт замерщика (бланк / DOCX / фото) → заполнение проекта и замера. */

import { uid } from "./calc.js";
import { compressImageFile } from "./photos.js";

const API = "/bestpaints/api/parse-report";

export function reportsPanelHtml(state = {}) {
  const last = state.lastReport;
  const conf = last?.confidence != null ? Math.round(last.confidence * 100) : null;
  return `
    <div class="drawings-card" id="reports-card">
      <div class="scale-head">
        <strong>Бланк в начале заявки</strong>
        <span class="hint">Фото бланка «Отчет по замеру» и/или DOCX · заполнит клиента, стены и быт</span>
      </div>
      <div class="field">
        <label>Файлы (можно несколько: фото бланка + DOCX)</label>
        <input type="file" id="rp-files" accept="image/*,.docx,.txt,.md,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" multiple />
      </div>
      <div class="field">
        <label>Подсказка</label>
        <input id="rp-hint" value="${escAttr(state.reportHint || "замерщик Морозов Степан")}" placeholder="замерщик, уточнения" />
      </div>
      <div class="scale-actions" style="display:flex;flex-wrap:wrap;gap:8px">
        <button type="button" class="btn primary" id="rp-parse">Распознать отчёт</button>
        <button type="button" class="btn ghost" id="rp-demo">Демо: Сергей / Морозов Степан</button>
      </div>
      <div id="rp-status" class="hint" style="margin-top:8px">
        ${
          last
            ? `Последний разбор: ${last.walls?.length || 0} стен · клиент ${esc(last.client?.name || "—")}${conf != null ? ` · ~${conf}%` : ""}`
            : "Загрузите бланк и/или DOCX — поля клиента, стен, быта и допов заполнятся после проверки."
        }
      </div>
      <div id="rp-result" class="dw-result" style="${last ? "" : "display:none"}"></div>
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
  const c = data.client || {};
  const b = data.building || {};
  const walls = (data.walls || [])
    .map(
      (w, i) => `<tr>
      <td><label style="display:flex;gap:6px;align-items:center"><input type="checkbox" data-rp-wall="${i}" checked style="width:auto"/> ${esc(w.label)}</label></td>
      <td>${w.areaManual != null ? `${w.areaManual} м²` : `${w.length ?? "—"} × ${w.height ?? "—"}`} · ${esc(w.shape)}</td>
      <td>${Math.round((w.confidence || 0) * 100)}%</td>
    </tr>`
    )
    .join("");
  el.style.display = "block";
  el.innerHTML = `
    <div class="callout ok" style="margin-top:10px">
      <b>${esc(data.sourceType || "отчёт")}</b>
      ${c.name ? ` — ${esc(c.name)}` : ""}
      ${c.phone ? ` · ${esc(c.phone)}` : ""}
      ${c.surveyor ? `<div class="hint">Замерщик: ${esc(c.surveyor)}</div>` : ""}
      ${c.address ? `<div class="hint">${esc(c.address)}</div>` : ""}
      ${b.material ? `<div class="hint">Материал: ${esc(b.material)} · ${esc(b.houseType || "")} · снятие: ${esc(b.removalDifficulty || "")}</div>` : ""}
      ${data.notes ? `<div class="hint" style="margin-top:6px">${esc(data.notes)}</div>` : ""}
    </div>
    <table class="table" style="margin-top:8px;font-size:.85rem">
      <thead><tr><th>Стена</th><th>Площадь / размер</th><th>AI</th></tr></thead>
      <tbody>${walls || "<tr><td colspan=3>Нет стен — будут заполнены клиент/быт/заметки</td></tr>"}</tbody>
    </table>
    <label class="choice" style="display:flex;gap:8px;margin:10px 0;align-items:center">
      <input type="checkbox" id="rp-replace" checked style="width:auto"/>
      <span>Заменить плоскости и данные клиента из отчёта</span>
    </label>
    <button type="button" class="btn primary block" id="rp-apply">Применить к проекту</button>
  `;
}

function s(v) {
  return v == null || v === "" ? "" : String(v);
}

function wallFromReport(w, building) {
  const hasLh = w.length != null && w.height != null;
  return {
    id: uid(),
    label: w.label || "Стена",
    shape: w.shape || (w.areaManual != null && !hasLh ? "custom" : "rect"),
    length: s(w.length),
    height: s(w.height),
    ridge: s(w.ridge),
    height2: s(w.height2),
    areaManual: s(w.areaManual),
    zone: w.zone === "interior" ? "interior" : "facade",
    material: building.material || "",
    condition: "",
    coatingWant: "",
    note: w.note || "из отчёта замерщика",
    photos: [],
    flags: {},
    damageArea: "",
    endsOn: !!(w.endsLength || w.endsCount),
    endsLength: s(w.endsLength),
    endsCount: s(w.endsCount),
    endsDepth: "0.2",
    endsAreaManual: "",
    endsWithSides: false,
    soffitArea: s(w.soffitArea),
    fasciaArea: "",
    overhangArea: "",
    ceilingArea: s(w.ceilingArea),
    floorArea: "",
    trimLength: s(w.trimLength),
    doborLength: s(w.doborLength),
    gutterLength: s(w.gutterLength),
    sillLength: s(w.sillLength),
    warmLength: "",
    porchArea: "",
    stairsArea: "",
    railingsArea: "",
    attention: {},
  };
}

/** Применить разобранный отчёт к survey (клиент, site, building, walls). */
export function applyReportParse(survey, building, data, { replace = true, wallIdx = null } = {}) {
  if (!survey || !building || !data) return { walls: 0, filled: [] };
  const filled = [];
  const c = data.client || {};
  const binfo = data.building || {};
  const site = data.site || {};
  const measure = data.measure || {};

  if (replace || !survey.client?.name) {
    survey.client = survey.client || {};
    if (c.name) {
      survey.client.name = c.name;
      filled.push("client.name");
    }
    if (c.phone) {
      survey.client.phone = c.phone;
      filled.push("client.phone");
    }
    if (c.address) {
      survey.client.address = c.address;
      filled.push("client.address");
    }
    if (c.surveyor) {
      survey.client.surveyor = c.surveyor;
      filled.push("client.surveyor");
    }
  } else {
    survey.client = survey.client || {};
    if (c.surveyor && !survey.client.surveyor) survey.client.surveyor = c.surveyor;
    if (c.phone && !survey.client.phone) survey.client.phone = c.phone;
    if (c.address && !survey.client.address) survey.client.address = c.address;
    if (c.name && !survey.client.name) survey.client.name = c.name;
  }

  if (!survey.title || replace) {
    const title = binfo.name || c.address || c.name;
    if (title) {
      survey.title = String(title).slice(0, 120);
      filled.push("title");
    }
  }

  if (binfo.name) building.name = binfo.name;
  if (binfo.material) building.material = binfo.material;
  if (binfo.materialSize) building.materialSize = binfo.materialSize;
  if (binfo.houseType) building.houseType = binfo.houseType;
  // "normal" — устаревшее/неверное имя середины шкалы состояния; tech-matrix.js ждёт "medium".
  if (binfo.condition) building.condition = binfo.condition === "normal" ? "medium" : binfo.condition;
  if (binfo.removalDifficulty) building.removalDifficulty = binfo.removalDifficulty;
  if (binfo.colors) building.colors = binfo.colors;
  if (binfo.oldCoatingNote) building.oldCoatingNote = binfo.oldCoatingNote;
  if (binfo.heightRidge != null) {
    building.dims = building.dims || {};
    building.dims.heightRidge = s(binfo.heightRidge);
  }
  filled.push("building");

  survey.site = survey.site || {};
  for (const k of ["startWhen", "workHours", "powerFrom", "housing", "toilet", "shower", "water", "notes"]) {
    if (site[k]) {
      if (k === "notes" && survey.site.notes && !replace) {
        if (!String(survey.site.notes).includes(site.notes)) {
          survey.site.notes = `${survey.site.notes}\n${site.notes}`.trim();
        }
      } else if (replace || !survey.site[k] || survey.site[k] === "none" || survey.site[k] === "") {
        survey.site[k] = site[k];
      }
    }
  }
  filled.push("site");

  if (data.attention && typeof data.attention === "object") {
    survey.attention = survey.attention || {};
    for (const [k, v] of Object.entries(data.attention)) {
      if (v) survey.attention[k] = v;
    }
    filled.push("attention");
  }
  if (data.extrasQty && typeof data.extrasQty === "object") {
    survey.extras = survey.extras || { qty: {} };
    survey.extras.qty = survey.extras.qty || {};
    for (const [k, v] of Object.entries(data.extrasQty)) {
      if (v) survey.extras.qty[k] = String(v);
    }
    filled.push("extras");
  }

  const m = building.measure;
  const selected = (data.walls || []).filter((_, i) => !wallIdx || wallIdx.has(i));
  const newWalls = selected.map((w) => wallFromReport(w, building));
  if (newWalls.length) {
    if (replace) m.walls = newWalls;
    else m.walls = [...(m.walls || []), ...newWalls];
    filled.push("walls");
  }

  const byLabel = new Map((m.walls || []).map((w) => [String(w.label).toLowerCase(), w]));
  const openings = [];
  for (const o of data.openings || []) {
    if (o.width == null || o.height == null) continue;
    const key = String(o.wallLabel || "").toLowerCase();
    const wall =
      byLabel.get(key) ||
      (m.walls || []).find((w) => key && String(w.label).toLowerCase().includes(key)) ||
      (m.walls || [])[0];
    openings.push({
      id: uid(),
      wallId: wall?.id || "",
      label: o.label || "Проём",
      width: s(o.width),
      height: s(o.height),
      kind: o.kind || "window",
      needsWarm: false,
      note: "из отчёта",
    });
  }
  if (openings.length) {
    if (replace) m.openings = openings;
    else m.openings = [...(m.openings || []), ...openings];
    filled.push("openings");
  }

  for (const [k, v] of Object.entries(measure)) {
    if (k === "notes") {
      if (v) {
        m.notes = replace || !m.notes ? String(v) : `${m.notes}\n${v}`.trim();
      }
      continue;
    }
    if (v != null && v !== "") {
      // layoutLength / openingsArea и др. — сумма с стен, если на стенах уже есть
      if (k === "layoutLength") {
        const fromWalls = (m.walls || []).reduce((s0, w) => s0 + (Number(String(w.layoutLength || "").replace(",", ".")) || 0), 0);
        // layoutLength нет на стене в UI — храним сумму из отчёта на measure + note
        m.layoutLength = s(fromWalls > 0 ? fromWalls : v);
      } else {
        m[k] = s(v);
      }
    }
  }
  // раскладка со стен → measure
  const layoutFromWalls = selected.reduce((acc, w) => acc + (Number(w.layoutLength) || 0), 0);
  if (layoutFromWalls > 0) m.layoutLength = s(layoutFromWalls);

  if (data.notes) {
    const noteLine = String(data.notes);
    survey.site.notes = survey.site.notes || "";
    if (!survey.site.notes.includes(noteLine.slice(0, 80))) {
      survey.site.notes = [survey.site.notes, noteLine].filter(Boolean).join("\n").trim();
    }
  }

  building.photos = building.photos || [];
  if (data._previewDataUrl && !building.photos.some((p) => p.fromReport)) {
    building.photos.unshift({
      id: uid(),
      dataUrl: data._previewDataUrl,
      note: "Отчёт замерщика",
      fromReport: true,
    });
  }

  return { walls: newWalls.length, filled };
}

async function fileToPayload(file) {
  const name = file.name || "file";
  const lower = name.toLowerCase();
  if (file.type.startsWith("image/") || /\.(jpe?g|png|webp|gif|heic)$/i.test(lower)) {
    const compressed = await compressImageFile(file);
    const dataUrl = typeof compressed === "string" ? compressed : compressed?.dataUrl;
    if (!dataUrl) throw new Error(`Не удалось прочитать ${name}`);
    return { name, imageDataUrl: dataUrl };
  }
  const buf = await file.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  const b64 = btoa(binary);
  return {
    name,
    mime: file.type || (lower.endsWith(".docx") ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "text/plain"),
    dataBase64: b64,
  };
}

export function bindReportsPanel(root, { getSurvey, getBuilding, getState, setState, onApplied, toast } = {}) {
  const card = root.querySelector("#reports-card");
  if (!card) return;
  if (card.dataset.bound === "1") return;
  card.dataset.bound = "1";

  let lastReport = getState?.()?.lastReport || null;
  if (lastReport) renderResult(root.querySelector("#rp-result"), lastReport);

  const setBusy = (busy, msg) => {
    const btn = root.querySelector("#rp-parse");
    if (btn) {
      btn.disabled = busy;
      btn.textContent = busy ? "Распознаём…" : "Распознать отчёт";
    }
    const st = root.querySelector("#rp-status");
    if (st && msg) st.textContent = msg;
  };

  root.querySelector("#rp-hint")?.addEventListener("change", (e) => {
    setState?.({ ...(getState?.() || {}), reportHint: e.target.value });
  });

  const applyLast = () => {
    if (!lastReport) {
      toast?.("Сначала распознайте отчёт");
      return;
    }
    const wallIdx = new Set(
      [...root.querySelectorAll("[data-rp-wall]:checked")].map((el) => Number(el.dataset.rpWall))
    );
    const replace = !!root.querySelector("#rp-replace")?.checked;
    const survey = getSurvey?.();
    const b = getBuilding?.();
    const r = applyReportParse(survey, b, lastReport, { replace, wallIdx });
    onApplied?.(r, lastReport);
  };

  root.querySelector("#rp-parse")?.addEventListener("click", async () => {
    const input = root.querySelector("#rp-files");
    const files = [...(input?.files || [])];
    if (!files.length) {
      toast?.("Выберите фото бланка и/или DOCX");
      return;
    }
    const hint = root.querySelector("#rp-hint")?.value || "";
    setBusy(true, "Читаем файлы и отправляем на распознавание…");
    try {
      const payloadFiles = [];
      let preview = null;
      for (const f of files) {
        const p = await fileToPayload(f);
        payloadFiles.push(p);
        if (p.imageDataUrl && !preview) preview = p.imageDataUrl;
      }
      const res = await fetch(API, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: payloadFiles, hint }),
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
      lastReport = { ...payload, _previewDataUrl: preview };
      setState?.({ reportHint: hint, lastReport });
      renderResult(root.querySelector("#rp-result"), lastReport);
      setBusy(
        false,
        `Готово: ${lastReport.walls?.length || 0} стен · ${lastReport.client?.name || "без имени"} — проверьте и примените`
      );
    } catch (e) {
      console.error(e);
      setBusy(false, e.message || String(e));
      toast?.(e.message || "Ошибка распознавания");
    }
  });

  root.querySelector("#rp-demo")?.addEventListener("click", async () => {
    setBusy(true, "Загружаем эталонный разбор…");
    try {
      const res = await fetch("/bestpaints/api/demo-report", { credentials: "same-origin" });
      if (res.status === 401) {
        location.href = "/bestpaints/login";
        return;
      }
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Нет демо");
      lastReport = payload;
      setState?.({ ...(getState?.() || {}), lastReport });
      renderResult(root.querySelector("#rp-result"), lastReport);
      setBusy(false, "Демо: Сергей · СНТ Чёрный Ручей · Морозов Степан — примените к проекту");
      toast?.("Эталон загружен — нажмите «Применить»");
    } catch (e) {
      setBusy(false, e.message || String(e));
      toast?.(e.message || "Ошибка демо");
    }
  });

  root.addEventListener("click", (e) => {
    if (e.target.closest("#rp-apply") && root.contains(e.target.closest("#rp-apply"))) {
      applyLast();
    }
  });
}
