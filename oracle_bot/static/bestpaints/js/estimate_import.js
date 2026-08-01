/** Импорт уже готовой сметы (отправленной клиенту раньше другим способом) → новая сделка. */

import { compressImageFile } from "./photos.js";
import { emptySurvey, buildEstimate, uid } from "./calc.js";
import * as store from "./storage.js";

const PARSE_API = "/bestpaints/api/parse-estimate";
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

/** Один ряд позиции сметы: имя / кол-во / ед. / цена. */
function lineRowHtml(line) {
  const id = line.id || uid();
  return `
  <div class="custom-line" data-import-line="${esc(id)}">
    <input data-cf="name" placeholder="Название работы/материала" value="${esc(line.name || "")}" />
    <input data-cf="qty" type="number" min="0" step="0.1" placeholder="Кол-во" value="${esc(line.qty ?? 1)}" />
    <input data-cf="unit" placeholder="ед." value="${esc(line.unit || "шт")}" />
    <input data-cf="price" type="number" min="0" step="100" placeholder="Цена" value="${esc(line.price ?? "")}" />
    <button type="button" class="btn ghost sm" data-line-del title="Удалить">✕</button>
  </div>`;
}

export function importEstimateHtml() {
  return `
  <div class="crm-create" id="ie-upload-step">
    <h3>Загрузить готовую смету</h3>
    <p class="hint">
      Для клиента, которому смету уже считали и отправляли другим способом (WhatsApp/Telegram/бумага) —
      до этой CRM. Загрузите фото/скан/файл сметы — AI попробует прочитать клиента, сумму и позиции.
      Всё, что не распознается, можно дозаполнить руками на следующем шаге.
    </p>
    <label>Файлы (фото/скан сметы, DOCX, текст — можно несколько)
      <input type="file" id="ie-files" accept="image/*,.docx,.txt,.md,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" multiple />
    </label>
    <label>Подсказка для AI (необязательно)<input id="ie-hint" placeholder="например: смета для Иванова, дом из бруса" /></label>
    <div class="crm-actions">
      <button type="button" class="btn primary" id="ie-recognize">Распознать смету</button>
      <button type="button" class="btn ghost" id="ie-skip">Заполнить вручную, без AI</button>
    </div>
    <div id="ie-upload-status" class="hint" style="margin-top:8px"></div>
  </div>
  <div id="ie-review-wrap"></div>`;
}

function reviewFormHtml(meta, data) {
  const client = data?.client || {};
  const lines = data?.lines?.length ? data.lines : [{ name: "", qty: 1, unit: "шт", price: "" }];
  const lidOpts = optionsHtml(meta?.staff?.lidarubs, { emptyLabel: "" });
  const mgrOpts = optionsHtml(meta?.staff?.managers, { emptyLabel: "Без менеджера" });
  const svOpts = optionsHtml(meta?.staff?.surveyors, { emptyLabel: "Не назначен (авто из графика)" });
  const today = meta?.today || new Date().toISOString().slice(0, 10);
  return `
  <div class="crm-create" id="ie-review-form">
    <h3>Проверьте и дозаполните</h3>
    ${
      data?.confidence != null
        ? `<div class="callout ${data.confidence >= 0.6 ? "ok" : "danger"}">
        AI-распознавание ~${Math.round((data.confidence || 0) * 100)}%.
        ${data.notes ? `<div class="hint" style="margin-top:6px">${esc(data.notes)}</div>` : ""}
        Проверьте цифры и позиции ниже — это должно совпадать с тем, что уже отправляли клиенту.
      </div>`
        : ""
    }
    <label>Название сделки<input name="title" required placeholder="Как в CRM" value="${esc(data?.title || client.name || "")}" /></label>
    <div class="crm-form-row">
      <label>Клиент<input name="client_name" value="${esc(client.name || "")}" autocomplete="name" /></label>
      <label>Телефон<input name="client_phone" type="tel" value="${esc(client.phone || "")}" autocomplete="tel" /></label>
    </div>
    <label>Адрес<input name="address" value="${esc(client.address || "")}" /></label>
    <label>Дата (для карточки)<input name="measure_date" type="date" value="${esc(today)}" /></label>

    <div class="crm-form-row">
      <label>Лидоруб<select name="lidarub_id" required>${lidOpts}</select></label>
      <label>Менеджер<select name="manager_id">${mgrOpts}</select></label>
    </div>
    <label>Замерщик<select name="surveyor_id">${svOpts}</select></label>

    <h4 class="subhead" style="margin:14px 0 6px">Позиции сметы</h4>
    <div id="ie-lines">${lines.map(lineRowHtml).join("")}</div>
    <button type="button" class="btn ghost sm" id="ie-add-line">+ Позиция</button>

    <div class="crm-form-row" style="margin-top:12px">
      <label>Сумма до скидки, ₽<input id="ie-subtotal" type="number" min="0" step="100" value="${esc(data?.subtotal ?? "")}" /></label>
      <label>Скидка, %<input id="ie-discount" type="number" min="0" max="100" step="0.5" value="${esc(data?.discountPct ?? 0)}" /></label>
    </div>
    <div class="hint" id="ie-total-hint" style="margin:4px 0 8px"></div>
    <label>Заметка / источник (для истории сделки)<textarea id="ie-source-note" rows="2" placeholder="напр. фото сметы из WhatsApp от 20.07">${esc(data?.notes || "")}</textarea></label>

    <button type="button" class="btn primary block" id="ie-submit">Создать сделку из сметы</button>
    <div id="ie-submit-status" class="hint" style="margin-top:8px"></div>
  </div>`;
}

function readLines(root) {
  return [...root.querySelectorAll("[data-import-line]")]
    .map((row) => ({
      id: row.getAttribute("data-import-line"),
      name: row.querySelector("[data-cf='name']")?.value || "",
      qty: num(row.querySelector("[data-cf='qty']")?.value, 1),
      unit: row.querySelector("[data-cf='unit']")?.value || "шт",
      price: num(row.querySelector("[data-cf='price']")?.value, 0),
    }))
    .filter((l) => l.name.trim());
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

/** Собрать минимальный survey (для конструктора/кабинета/презентации) из данных импорта. */
function buildImportedSurvey({ title, client, lines, discountPct }) {
  const survey = emptySurvey();
  survey.title = title || "";
  survey.client = { ...survey.client, ...client };
  survey.buildings[0].name = title || survey.buildings[0].name;
  survey.estimate.discountPct = num(discountPct, 0);
  survey.estimate.customLines = lines.map((l) => ({
    id: uid(),
    name: l.name,
    qty: String(l.qty),
    unit: l.unit || "шт",
    price: String(l.price),
  }));
  survey.notes = { text: "Смета создана импортом готового КП (без полного замера в конструкторе)." };
  return survey;
}

export function bindImportEstimatePanel(root, { getMeta, toast, onCreated, actorRole } = {}) {
  const uploadStatus = root.querySelector("#ie-upload-status");
  const reviewWrap = root.querySelector("#ie-review-wrap");

  const setUploadBusy = (busy, msg) => {
    const btn = root.querySelector("#ie-recognize");
    if (btn) {
      btn.disabled = busy;
      btn.textContent = busy ? "Распознаём…" : "Распознать смету";
    }
    if (uploadStatus && msg != null) uploadStatus.textContent = msg;
  };

  async function showReview(data) {
    const meta = await getMeta();
    reviewWrap.innerHTML = reviewFormHtml(meta, data);
    bindReview(reviewWrap, meta);
    reviewWrap.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  root.querySelector("#ie-recognize")?.addEventListener("click", async () => {
    const input = root.querySelector("#ie-files");
    const files = [...(input?.files || [])];
    if (!files.length) {
      toast?.("Выберите фото/файл сметы");
      return;
    }
    const hint = root.querySelector("#ie-hint")?.value || "";
    setUploadBusy(true, "Читаем файлы и отправляем на распознавание…");
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
      setUploadBusy(false, `Готово: ${data.lines?.length || 0} позиций · ${data.client?.name || "без клиента"} — проверьте ниже`);
      await showReview(data);
    } catch (e) {
      console.error(e);
      setUploadBusy(false, e.message || String(e));
      toast?.(e.message || "Ошибка распознавания");
    }
  });

  root.querySelector("#ie-skip")?.addEventListener("click", () => {
    setUploadBusy(false, "Заполните поля ниже вручную");
    showReview(null);
  });

  function bindReview(wrap, meta) {
    const linesWrap = wrap.querySelector("#ie-lines");
    const subtotalInput = wrap.querySelector("#ie-subtotal");
    const discountInput = wrap.querySelector("#ie-discount");
    const totalHint = wrap.querySelector("#ie-total-hint");

    const recalcTotal = () => {
      const lineSum = readLines(wrap).reduce((s, l) => s + l.qty * l.price, 0);
      const sub = subtotalInput.value !== "" ? num(subtotalInput.value) : lineSum;
      const disc = num(discountInput.value, 0);
      const total = Math.round(sub * (1 - disc / 100));
      if (subtotalInput.value === "" && lineSum > 0) subtotalInput.value = String(Math.round(lineSum));
      totalHint.textContent = `Сумма по позициям: ${Math.round(lineSum).toLocaleString("ru-RU")} ₽ · Итого клиенту (со скидкой): ${total.toLocaleString("ru-RU")} ₽`;
    };

    linesWrap.addEventListener("input", recalcTotal);
    linesWrap.addEventListener("click", (e) => {
      const del = e.target.closest("[data-line-del]");
      if (!del) return;
      del.closest("[data-import-line]")?.remove();
      recalcTotal();
    });
    wrap.querySelector("#ie-add-line")?.addEventListener("click", () => {
      linesWrap.insertAdjacentHTML("beforeend", lineRowHtml({ name: "", qty: 1, unit: "шт", price: "" }));
      recalcTotal();
    });
    subtotalInput.addEventListener("input", recalcTotal);
    discountInput.addEventListener("input", recalcTotal);
    recalcTotal();

    wrap.querySelector("#ie-submit")?.addEventListener("click", async () => {
      const form = wrap.querySelector("#ie-review-form");
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
      const lines = readLines(wrap);
      const clientName = form.querySelector("[name=client_name]")?.value.trim() || "";
      const clientPhone = form.querySelector("[name=client_phone]")?.value.trim() || "";
      const address = form.querySelector("[name=address]")?.value.trim() || "";
      const discountPct = num(discountInput.value, 0);
      const subtotal = num(subtotalInput.value, lines.reduce((s, l) => s + l.qty * l.price, 0));
      const total = Math.round(subtotal * (1 - discountPct / 100));

      const survey = buildImportedSurvey({
        title,
        client: { name: clientName, phone: clientPhone, address },
        lines,
        discountPct,
      });
      let est = null;
      try {
        est = buildEstimate(survey, {});
      } catch {
        est = null;
      }
      survey._estimateSnapshot = {
        subtotal: est?.subtotal ?? subtotal,
        discountPct,
        total: est?.total ?? total,
        areas: est?.areas || {},
        area_m2: est?.areas?.paintTotal || 0,
      };

      const btn = wrap.querySelector("#ie-submit");
      const status = wrap.querySelector("#ie-submit-status");
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
          subtotal,
          discount_pct: discountPct,
          total,
          area_m2: survey._estimateSnapshot.area_m2 || 0,
          survey_local_id: survey.id,
          source_note: wrap.querySelector("#ie-source-note")?.value || "",
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
              body: JSON.stringify({ survey, created_from: "import_estimate", actor_id: actorRole || "lidarub" }),
            });
            const cabData = await cabRes.json().catch(() => ({}));
            if (cabRes.ok) cabinetLink = cabData.link || "";
          } catch {
            /* кабинет можно открыть позже из карточки сделки */
          }
        }

        status.innerHTML = `<span style="color:var(--ok,#6fcf97)">Готово!</span> Сделка «${esc(obj.title)}» создана.
          ${cabinetLink ? `<div style="margin-top:6px">Кабинет клиента: <a href="${esc(cabinetLink)}" target="_blank" rel="noopener">${esc(cabinetLink)}</a></div>` : ""}`;
        toast?.("Сделка создана из готовой сметы");
        onCreated?.(obj);
      } catch (e) {
        console.error(e);
        status.textContent = e.message || String(e);
        toast?.(e.message || "Ошибка создания сделки");
      } finally {
        btn.disabled = false;
        btn.textContent = "Создать сделку из сметы";
      }
    });
  }
}
