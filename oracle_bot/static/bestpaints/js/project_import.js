/** Импорт проекта дома (архитектурная документация — планы/фасады/развёртки стен, обычно PDF)
 * → новая сделка со стенами, предзаполненными из площадей проекта.
 *
 * Схема результата парсинга та же, что у отчёта замерщика (reports.js), поэтому применение к survey
 * переиспользует applyReportParse — стены/материал/этажность и т.д. заполняются одинаково.
 */

import { compressImageFile } from "./photos.js";
import { emptySurvey, uid } from "./calc.js";
import { applyReportParse } from "./reports.js";
import * as store from "./storage.js";

const PARSE_API = "/bestpaints/api/parse-project";
const IMPORT_API = "/bestpaints/api/objects/import-estimate";
const CABINET_API = (id) => `/bestpaints/api/objects/${encodeURIComponent(id)}/cabinet`;

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function num(v, def = 0) {
  const n = Number(String(v ?? "").replace(",", "."));
  return Number.isFinite(n) ? n : def;
}

function optionsHtml(list, { emptyLabel } = {}) {
  const opts = emptyLabel ? [`<option value="">${esc(emptyLabel)}</option>`] : [];
  for (const p of list || []) {
    opts.push(`<option value="${esc(p.id)}">${esc(p.name)}</option>`);
  }
  return opts.join("");
}

function wallRowHtml(w) {
  const id = w.id || uid();
  return `
  <div class="custom-line wall-line" data-wall-row="${esc(id)}">
    <input data-cf="name" placeholder="Имя стены (Стена01, СтенаА…)" value="${esc(w.label ?? "")}" />
    <input data-cf="qty" type="number" min="0" step="0.01" placeholder="Площадь, м²" value="${esc(w.areaManual ?? "")}" />
    <button type="button" class="btn ghost sm" data-line-del title="Убрать">✕</button>
  </div>`;
}

export function importProjectHtml() {
  return `
  <div class="crm-create" id="ip-upload-step">
    <h3>Загрузить проект дома</h3>
    <p class="hint">
      Для клиента, на объект которого уже есть проектная документация (архитектурный проект/чертежи —
      обычно PDF с планами этажей и развёртками стен). AI найдёт площади стен/фасадов и контекст дома
      (этажность, площадь комнат, кровля) — замерщик проверит размеры на месте, конструктор досчитает смету.
    </p>
    <label>Файлы проекта (PDF с чертежами, фото листов, DOCX — можно несколько)
      <input type="file" id="ip-files" accept="application/pdf,.pdf,image/*,.docx,.txt,.md,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" multiple />
    </label>
    <label>Подсказка для AI (необязательно)<input id="ip-hint" placeholder="например: дом №2, брус 200х200" /></label>
    <div class="crm-actions">
      <button type="button" class="btn primary" id="ip-recognize">Распознать проект</button>
      <button type="button" class="btn ghost" id="ip-skip">Заполнить вручную, без AI</button>
    </div>
    <div id="ip-upload-status" class="hint" style="margin-top:8px"></div>
  </div>
  <div id="ip-review-wrap"></div>`;
}

function reviewFormHtml(meta, data) {
  const client = data?.client || {};
  const building = data?.building || {};
  const walls = data?.walls?.length ? data.walls : [{ label: "", areaManual: "" }];
  const lidOpts = optionsHtml(meta?.staff?.lidarubs, { emptyLabel: "" });
  const mgrOpts = optionsHtml(meta?.staff?.managers, { emptyLabel: "Без менеджера" });
  const svOpts = optionsHtml(meta?.staff?.surveyors, { emptyLabel: "Не назначен (авто из графика)" });
  const today = meta?.today || new Date().toISOString().slice(0, 10);
  const totalArea = walls.reduce((s, w) => s + (num(w.areaManual, 0) || 0), 0);
  return `
  <div class="crm-create" id="ip-review-form">
    <h3>Проверьте и дозаполните</h3>
    ${
      data?.confidence != null
        ? `<div class="callout ${data.confidence >= 0.6 ? "ok" : "danger"}">
          AI-распознавание ~${Math.round((data.confidence || 0) * 100)}%.
          ${data.notes ? `<div class="hint" style="margin-top:6px">${esc(data.notes)}</div>` : ""}
          Стены/площади проверит замерщик на месте — это черновой список из проекта.
        </div>`
        : ""
    }
    <label>Название сделки<input name="title" required placeholder="Например: Дом №2, Иванов" value="${esc(data?.title || building.name || client.name || "")}" /></label>
    <div class="crm-form-row">
      <label>Клиент<input name="client_name" value="${esc(client.name || "")}" autocomplete="name" placeholder="в проектах обычно нет — заполните" /></label>
      <label>Телефон<input name="client_phone" type="tel" value="${esc(client.phone || "")}" autocomplete="tel" /></label>
    </div>
    <label>Адрес<input name="address" value="${esc(client.address || "")}" /></label>
    <label>Дата (для карточки)<input name="measure_date" type="date" value="${esc(today)}"/></label>

    <div class="crm-form-row">
      <label>Лидоруб<select name="lidarub_id" required>${lidOpts}</select></label>
      <label>Менеджер<select name="manager_id">${mgrOpts}</select></label>
    </div>
    <label>Замерщик<select name="surveyor_id">${svOpts}</select></label>

    <h4 class="subhead" style="margin:14px 0 6px">Стены / фасады из проекта</h4>
    <p class="hint">Площади — как в проекте; замерщик уточнит на месте. Можно убрать/добавить/поправить.</p>
    <div id="ip-walls">${walls.map(wallRowHtml).join("")}</div>
    <button type="button" class="btn ghost sm" id="ip-add-wall">+ Стена</button>
    <div class="hint" id="ip-total-hint" style="margin:8px 0"></div>

    <label>Заметка / источник (для истории сделки)<textarea id="ip-source-note" rows="2" placeholder="напр. проект дома №2 от 15.07.2022, PDF от клиента">${esc(data?.notes ? data.notes.slice(0, 300) : "")}</textarea></label>

    <button type="button" class="btn primary block" id="ip-submit">Создать сделку из проекта</button>
    <div id="ip-submit-status" class="hint" style="margin-top:8px"></div>
  </div>`;
}

function readWalls(root) {
  return [...root.querySelectorAll("[data-wall-row]")]
    .map((row) => ({
      label: row.querySelector("[data-cf='name']")?.value.trim() || "",
      areaManual: num(row.querySelector("[data-cf='qty']")?.value, 0),
    }))
    .filter((w) => w.label && w.areaManual > 0);
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
  const mime =
    file.type ||
    (lower.endsWith(".pdf")
      ? "application/pdf"
      : lower.endsWith(".docx")
        ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        : "text/plain");
  return { name, mime, dataBase64: b64 };
}

export function bindImportProjectPanel(root, { getMeta, toast, onCreated, actorRole } = {}) {
  const uploadStatus = root.querySelector("#ip-upload-status");
  const reviewWrap = root.querySelector("#ip-review-wrap");

  const setUploadBusy = (busy, msg) => {
    const btn = root.querySelector("#ip-recognize");
    if (btn) {
      btn.disabled = busy;
      btn.textContent = busy ? "Распознаём… (может занять до минуты)" : "Распознать проект";
    }
    if (uploadStatus && msg != null) uploadStatus.textContent = msg;
  };

  async function showReview(data) {
    const meta = await getMeta();
    reviewWrap.innerHTML = reviewFormHtml(meta, data);
    bindReview(reviewWrap, data);
    reviewWrap.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  root.querySelector("#ip-recognize")?.addEventListener("click", async () => {
    const input = root.querySelector("#ip-files");
    const files = [...(input?.files || [])];
    if (!files.length) {
      toast?.("Выберите файлы проекта (PDF/фото)");
      return;
    }
    const hint = root.querySelector("#ip-hint")?.value || "";
    setUploadBusy(true, "Читаем чертежи и ищем площади стен…");
    try {
      const payloadFiles = [];
      for (const f of files) payloadFiles.push(await fileToPayload(f));
      const res = await fetch(PARSE_API, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: payloadFiles, hint }),
      });
      if (res.status === 401) {
        location.href = "/bestpaints/login";
        return;
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = data.detail;
        throw new Error(typeof detail === "string" ? detail : data.message || "Ошибка распознавания");
      }
      setUploadBusy(false, `Готово: ${data.walls?.length || 0} стен найдено — проверьте ниже`);
      await showReview(data);
    } catch (e) {
      console.error(e);
      setUploadBusy(false, e.message || String(e));
      toast?.(e.message || "Ошибка распознавания");
    }
  });

  root.querySelector("#ip-skip")?.addEventListener("click", () => {
    setUploadBusy(false, "Заполните поля ниже вручную");
    showReview(null);
  });

  function bindReview(wrap, parsedData) {
    const wallsWrap = wrap.querySelector("#ip-walls");
    const totalHint = wrap.querySelector("#ip-total-hint");

    const recalcTotal = () => {
      const total = readWalls(wrap).reduce((s, w) => s + w.areaManual, 0);
      totalHint.textContent = `Стен: ${readWalls(wrap).length} · суммарная площадь фасадов: ${Math.round(total).toLocaleString("ru-RU")} м²`;
    };

    wallsWrap.addEventListener("input", recalcTotal);
    wallsWrap.addEventListener("click", (e) => {
      const del = e.target.closest("[data-line-del]");
      if (!del) return;
      del.closest("[data-wall-row]")?.remove();
      recalcTotal();
    });
    wrap.querySelector("#ip-add-wall")?.addEventListener("click", () => {
      wallsWrap.insertAdjacentHTML("beforeend", wallRowHtml({ label: "", areaManual: "" }));
      recalcTotal();
    });
    recalcTotal();

    wrap.querySelector("#ip-submit")?.addEventListener("click", async () => {
      const form = wrap.querySelector("#ip-review-form");
      const title = form.querySelector("[name=title]")?.value.trim();
      const lidarubId = form.querySelector("[name=lidarub_id]")?.value || "";
      if (!title) {
        toast?.("Укажите название сделки");
        return;
      }
      if (!lidarubId) {
        toast?.("Выберите лидоруба — кто ведёт эту сделку");
        return;
      }
      const walls = readWalls(wrap);
      const clientName = form.querySelector("[name=client_name]")?.value.trim() || "";
      const clientPhone = form.querySelector("[name=client_phone]")?.value.trim() || "";
      const address = form.querySelector("[name=address]")?.value.trim() || "";

      const survey = emptySurvey();
      const building = survey.buildings[0];
      applyReportParse(
        survey,
        building,
        {
          ...(parsedData || {}),
          client: { name: clientName, phone: clientPhone, address, surveyor: parsedData?.client?.surveyor || "" },
          walls: walls.map((w) => ({ label: w.label, areaManual: w.areaManual, shape: "custom", zone: "facade" })),
        },
        { replace: true }
      );
      survey.title = title;

      const btn = wrap.querySelector("#ip-submit");
      const status = wrap.querySelector("#ip-submit-status");
      btn.disabled = true;
      btn.textContent = "Создаём…";
      try {
        const payload = {
          title,
          address,
          client_name: clientName,
          client_phone: clientPhone,
          measure_date: form.querySelector("[name=measure_date]")?.value || "",
          lidarub_id: lidarubId,
          manager_id: form.querySelector("[name=manager_id]")?.value || "",
          surveyor_id: form.querySelector("[name=surveyor_id]")?.value || "",
          survey_local_id: survey.id,
          source_note: wrap.querySelector("#ip-source-note")?.value || "",
          source_kind: "project",
          actor_role: actorRole || "lidarub",
        };
        const res = await fetch(IMPORT_API, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (res.status === 401) {
          location.href = "/bestpaints/login";
          return;
        }
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = data.detail;
          throw new Error(typeof detail === "string" ? detail : data.message || "Не удалось создать сделку");
        }
        const obj = data.object;
        store.upsert(survey);

        let cabinetLink = "";
        if (clientPhone) {
          try {
            const cabRes = await fetch(CABINET_API(obj.id), {
              method: "POST",
              credentials: "same-origin",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ survey, created_from: "import_project", actor_id: actorRole || "lidarub" }),
            });
            const cabData = await cabRes.json().catch(() => ({}));
            if (cabRes.ok) cabinetLink = cabData.link || "";
          } catch {
            /* кабинет можно открыть позже из карточки сделки */
          }
        }

        status.innerHTML = `<span style="color:var(--ok,#6fcf97)">Готово!</span> Сделка «${esc(obj.title)}» создана, стен: ${walls.length}.
          Технологию/краску и итоговую смету досчитайте в конструкторе на карточке сделки.
          ${cabinetLink ? `<div style="margin-top:6px">Кабинет клиента: <a href="${esc(cabinetLink)}" target="_blank" rel="noopener">${esc(cabinetLink)}</a></div>` : ""}`;
        toast?.("Сделка создана из проекта дома");
        onCreated?.(obj);
      } catch (e) {
        console.error(e);
        status.textContent = e.message || String(e);
        toast?.(e.message || "Ошибка создания сделки");
      } finally {
        btn.disabled = false;
        btn.textContent = "Создать сделку из проекта";
      }
    });
  }
}
