import {
  HOUSE_TYPES,
  CONDITIONS,
  TECHNOLOGIES,
  FORBIDDEN,
  MATERIAL_OPTIONS,
  ROUND_COEF,
  SEMI_LADDER,
  recommendTechs,
  defaultTechId,
} from "../data/tech-matrix.js";
import { EXTRA_WORKS, ATTENTION_ELEMENTS, STEPS, PHASE_LABELS, WALL_FLAGS, SCAFFOLD_OPTIONS, ATTENTION_TO_EXTRA } from "../data/extras.js";
import { OBJECT_KINDS, ROOF_TYPES, WALL_SHAPES, WORK_ZONES } from "../data/objects.js";
import { tipBlock } from "../data/tips.js";
import { houseSvg, techCompareHtml, paintLiters } from "./house3d.js";
import { openClientReport } from "./report.js";
import { readiness, readinessHtml } from "./quality.js";
import { shareTelegram, shareWhatsApp, copyShareText, nativeShare } from "./share.js";
import { compressImageFile, photosHtml, wallPhotosHtml } from "./photos.js";
import { bindKeypad } from "./keypad.js";
import { scalePanelHtml, bindScalePanel } from "./scale.js";
import { softDelete, listTrash, removeTrash, getTrash, askDelete, clearTrash } from "./trash.js";
import {
  emptySurvey,
  emptyBuilding,
  money,
  listPaintOptions,
  buildEstimate,
  syncWarmTotal,
  syncAreasFromLists,
  coefForMaterial,
  wallAreaOf,
  wallEndsAreaOf,
  calcWallArea,
  formulaHtml,
  totalAreas,
  migrateSurvey,
  getActiveBuilding,
  applyKindPreset,
  num,
  uid,
} from "./calc.js";

/** Помехи, которые удобно считать на каждой стороне фасада */
const WALL_ATTENTION = ATTENTION_ELEMENTS.filter((el) =>
  ["lights", "antennas", "ac", "chimneys", "wiring", "garlands", "decor", "cable_duct"].includes(el.id)
);
import * as store from "./storage.js";
import {
  fetchMeta,
  mountHomeCrm,
  mountDetail,
  homeCrmSectionHtml,
  doAction,
} from "./crm.js";

const PREVIEW_COLORS = [
  { id: "#c4a35a", label: "Золото" },
  { id: "#8b5a2b", label: "Орех" },
  { id: "#5c4033", label: "Венге" },
  { id: "#d4c4a8", label: "Белёный" },
  { id: "#6b7c3d", label: "Мох" },
  { id: "#8fbf7a", label: "Салат" },
  { id: "#4a5560", label: "Графит" },
  { id: "#b85c38", label: "Терракота" },
];

const COATING_WANT = [
  { id: "", label: "Покрытие — как у дома" },
  { id: "semi", label: "Хочет полупрозрачный" },
  { id: "opaque", label: "Хочет укрывной" },
];

const WALL_CONDITIONS = [
  { id: "", label: "Состояние — как у дома" },
  { id: "good", label: "Хорошее" },
  { id: "medium", label: "Среднее" },
  { id: "bad", label: "Плохое" },
];

const $ = (sel, root = document) => root.querySelector(sel);
const app = $("#app");

let catalog = null;
let view = "home";
let step = 0;
let survey = null;
let crmObjectId = null;
let crmMetaCache = null;

async function init() {
  catalog = await fetch("./data/catalog.json").then((r) => r.json());
  const params = new URLSearchParams(location.search);
  const id = params.get("id");
  const crmId = params.get("crm");
  if (crmId) {
    crmObjectId = crmId;
    view = "crm";
  } else if (id) {
    const s = store.get(id);
    if (s) {
      survey = migrateSurvey(s);
      view = "wizard";
      const stepParam = Number(params.get("step"));
      step = Number.isFinite(stepParam) ? Math.max(0, Math.min(STEPS.length - 1, stepParam)) : 0;
    }
  }
  // Хуки для обучающего ролика / автотестов
  window.__BP__ = {
    getStep: () => step,
    setStep: (n) => {
      step = Math.max(0, Math.min(STEPS.length - 1, Number(n) || 0));
      view = "wizard";
      render();
    },
    goHome: () => goHome(),
    openId: (sid) => openSurvey(sid),
    openCrm: (oid) => openCrm(oid),
  };
  render();
}

function active() {
  return getActiveBuilding(survey);
}

function goHome() {
  view = "home";
  survey = null;
  crmObjectId = null;
  crmMetaCache = null;
  history.replaceState({}, "", location.pathname);
  render();
}

function openCrm(oid) {
  crmObjectId = oid;
  view = "crm";
  survey = null;
  history.replaceState({}, "", `?crm=${encodeURIComponent(oid)}`);
  render();
}

async function getCrmMeta() {
  if (crmMetaCache) return crmMetaCache;
  crmMetaCache = await fetchMeta();
  return crmMetaCache;
}


function openSurvey(id) {
  survey = migrateSurvey(store.get(id) || emptySurvey());
  view = "wizard";
  step = 0;
  history.replaceState({}, "", `?id=${survey.id}`);
  store.upsert(survey);
  render();
}

function newSurvey() {
  survey = emptySurvey();
  store.upsert(survey);
  openSurvey(survey.id);
}

function surveyLabel(s) {
  return (
    (s.title || "").trim() ||
    (s.contract?.objectName || "").trim() ||
    (s.client?.name || "").trim() ||
    (s.client?.address || "").trim() ||
    "Новый объект"
  );
}

function cloneBuilding(src) {
  const copy = JSON.parse(JSON.stringify(src));
  copy.id = uid();
  copy.name = `${src.name} (копия)`;
  copy.photos = [];
  for (const w of copy.measure?.walls || []) w.id = uid();
  for (const o of copy.measure?.openings || []) o.id = uid();
  return copy;
}

function toast(msg, ms = 2200) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.classList.remove("with-undo");
  el.innerHTML = "";
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), ms);
}

/** Toast with «Отменить» restore action (8s). */
function toastUndo(msg, undoFn) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.classList.add("with-undo");
  el.innerHTML = `<span class="toast-msg">${escapeHtml(msg)}</span><button type="button" class="toast-undo">Отменить</button>`;
  el.classList.add("show");
  clearTimeout(toast._t);
  const btn = el.querySelector(".toast-undo");
  const hide = () => el.classList.remove("show");
  btn.onclick = () => {
    hide();
    try {
      undoFn();
      toast("Восстановлено");
    } catch (e) {
      toast("Не удалось восстановить");
    }
  };
  toast._t = setTimeout(hide, 8000);
}

/** Visible step block (alert often invisible in PWA / behind keyboard). */
function showNavHint(msg) {
  let el = document.getElementById("nav-hint");
  if (!el) {
    el = document.createElement("div");
    el.id = "nav-hint";
    el.className = "nav-hint callout danger no-print";
    const bar = document.querySelector(".nav-bar");
    if (bar) bar.parentNode.insertBefore(el, bar);
    else document.body.appendChild(el);
  }
  el.hidden = false;
  el.innerHTML = `<strong>Нельзя идти дальше:</strong> ${escapeHtml(msg)}`;
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function clearNavHint() {
  const el = document.getElementById("nav-hint");
  if (el) el.hidden = true;
}

function blockLeave(msg, opts = {}) {
  toast(msg, 5000);
  showNavHint(msg);
  const focus = opts.focus;
  if (focus) {
    const el = typeof focus === "string" ? document.querySelector(focus) : focus;
    if (el) {
      el.classList.add("field-error");
      const wrap = el.closest(".field") || el;
      wrap.classList?.add("field-error-wrap");
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      try {
        el.focus({ preventScroll: true });
      } catch {
        try {
          el.focus();
        } catch {
          /* ignore */
        }
      }
      clearTimeout(blockLeave._t);
      blockLeave._t = setTimeout(() => {
        el.classList.remove("field-error");
        wrap.classList?.remove("field-error-wrap");
      }, 3200);
    }
  }
  return false;
}

function bindPhotos(root, building) {
  const input = root.querySelector("[data-photo-input]");
  if (!input) return;
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const photo = await compressImageFile(file);
      if (!building.photos) building.photos = [];
      building.photos.push(photo);
      save();
      render();
      toast("Фото добавлено");
    } catch {
      toast("Не удалось загрузить фото");
    }
    input.value = "";
  };
  root.querySelectorAll("[data-ph-del]").forEach((btn) => {
    btn.onclick = async () => {
      const photo = (building.photos || []).find((p) => p.id === btn.dataset.phDel);
      if (!photo) return;
      await softDelete({
        what: "фото строения",
        type: "building_photo",
        payload: cloneDeep(photo),
        meta: { surveyId: survey.id, buildingId: building.id },
        toastUndo,
        applyRemove: () => {
          building.photos = (building.photos || []).filter((p) => p.id !== photo.id);
          save();
          render();
        },
        applyRestore: (payload) => {
          const b = survey.buildings.find((x) => x.id === building.id) || building;
          if (!b.photos) b.photos = [];
          if (!b.photos.some((p) => p.id === payload.id)) b.photos.push(payload);
          save();
          render();
        },
      });
    };
  });
}

function cloneDeep(value) {
  try {
    return structuredClone(value);
  } catch {
    return JSON.parse(JSON.stringify(value));
  }
}

function save() {
  if (!survey) return;
  store.upsert(survey);
}

function setDeep(path, value) {
  const parts = path.split(".");
  let obj = survey;
  // allow building.* to mean active building
  if (parts[0] === "building") {
    obj = active();
    parts.shift();
  }
  if (path === "site.generator") value = value === true || value === "1" || value === "true";
  for (let i = 0; i < parts.length - 1; i++) obj = obj[parts[i]];
  obj[parts[parts.length - 1]] = value;
  save();
}

function areaBadgeHtml() {
  const areas = totalAreas(survey);
  const b = active();
  syncAreasFromLists(b);
  return `
    <div class="area-badge">
      <div class="ab-main">
        <span>${escapeHtml(b.name)} · к покраске</span>
        <b>${(num(b.measure.facadeArea) + num(b.measure.interiorArea)).toFixed(1)} м²</b>
      </div>
      <div class="ab-sub">
        фасад ${num(b.measure.facadeArea).toFixed(1)}
        ${b.zones?.interior ? ` · интерьер ${num(b.measure.interiorArea).toFixed(1)}` : ""}
        ${areas.soffit ? ` · подшива Σ ${areas.soffit}` : ""}
        ${areas.ceiling ? ` · потолки Σ ${areas.ceiling}` : ""}
        ${survey.buildings.length > 1 ? ` · строений: ${survey.buildings.length} (всего ${areas.paintTotal} м²)` : ""}
      </div>
    </div>
  `;
}

function buildingsBarHtml() {
  return `
    <div class="buildings-bar no-print">
      <div class="buildings-tabs">
        ${survey.buildings
          .map(
            (b) => `
          <button type="button" class="b-tab ${b.id === survey.activeBuildingId ? "active" : ""}" data-bid="${b.id}">
            ${escapeHtml(b.name)}
          </button>`
          )
          .join("")}
      </div>
      <div class="buildings-actions">
        <button type="button" class="btn ghost" id="btn-dup-building" title="Дублировать">⧉</button>
        <button type="button" class="btn ghost" id="btn-add-building">+ Строение</button>
      </div>
    </div>
  `;
}

function render() {
  if (view === "home") renderHome();
  else if (view === "crm") renderCrm();
  else renderWizard();
}

function renderCrm() {
  mountDetail({
    root: app,
    objectId: crmObjectId,
    toast,
    onBack: () => goHome(),
    getMeta: getCrmMeta,
    onOpenSurvey: async (obj) => {
      // Сделка Лидоруба уже с данными → сразу шаг 2 «Строение»
      const startAtBuilding = () => {
        survey = migrateSurvey(store.get(survey.id) || survey);
        view = "wizard";
        step = 1; // Строение
        history.replaceState({}, "", `?id=${survey.id}&step=1&crm=${encodeURIComponent(obj.id)}`);
        store.upsert(survey);
        render();
      };
      let sid = obj.survey_local_id;
      if (sid && store.get(sid)) {
        survey = migrateSurvey(store.get(sid));
        startAtBuilding();
        return;
      }
      const s = emptySurvey();
      s.title = obj.title || "";
      s.client = s.client || {};
      s.client.name = obj.client_name || "";
      s.client.phone = obj.client_phone || "";
      s.client.address = obj.address || "";
      s.notes = s.notes || {};
      if (typeof s.notes === "object") {
        s.notes.qualification = obj.qualification || "";
        s.notes.crmId = obj.id;
        s.notes.measureDate = obj.measure_date || "";
      }
      if (s.contract) s.contract.objectName = obj.title || "";
      store.upsert(s);
      survey = s;
      try {
        await doAction(obj.id, "link_survey", { survey_local_id: s.id });
      } catch (e) {
        toast(String(e.message || e));
      }
      startAtBuilding();
    },
  });
}


function renderHome() {
  const list = store.loadAll().slice().sort((a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""));
  const trash = listTrash();
  app.innerHTML = `
    <header class="topbar">
      <div class="brand">
        <strong>BestPaints</strong>
        <span>CRM · замер · смета</span>
      </div>
    </header>
    ${homeCrmSectionHtml()}

    <details class="local-fold">
      <summary>Локальные замеры на устройстве (${list.length})</summary>
      <p class="hint">Офлайн-конструктор. Воронка статусов — во вкладке «Сделки» выше.</p>
      <button class="btn ghost block" id="btn-new" style="margin:10px 0">+ Локальный замер</button>
      <div class="survey-list">
      ${
        list.length
          ? list
              .map((s) => {
                migrateSurvey(s);
                const a = totalAreas(s);
                const r = readiness(s);
                const n = s.buildings?.length || 1;
                return `
        <article class="survey-item">
          <div>
            <h3>${escapeHtml(surveyLabel(s))}
              <span class="pct-pill ${r.canLeave ? "ok" : ""}">${r.pct}%</span>
            </h3>
            <p>${escapeHtml(s.client?.name || "Клиент не указан")}
              · ${escapeHtml(s.client?.address || "Адрес не указан")}
              · ${n} ${n === 1 ? "строение" : "строения"}
              · ${a.paintTotal} м² · ${fmtDate(s.updatedAt)}</p>
          </div>
          <div class="survey-actions">
            <button class="btn" data-open="${s.id}">Открыть</button>
            <button class="btn ghost" data-del="${s.id}" title="Удалить">✕</button>
          </div>
        </article>`;
              })
              .join("")
          : `<div class="empty soft mini">Пока пусто</div>`
      }
      </div>
    </details>

    ${
      trash.length
        ? `<details class="trash-panel">
      <summary>Корзина · ${trash.length}</summary>
      <div class="trash-list">
        ${trash
          .map(
            (t) => `
          <div class="trash-item">
            <div>
              <strong>${escapeHtml(t.label)}</strong>
              <p class="hint">${escapeHtml(typeLabel(t.type))} · ${fmtDate(new Date(t.deletedAt).toISOString())}</p>
            </div>
            <div class="survey-actions">
              <button type="button" class="btn" data-restore="${t.id}">Восстановить</button>
              <button type="button" class="btn ghost" data-purge="${t.id}" title="Удалить навсегда">✕</button>
            </div>
          </div>`
          )
          .join("")}
      </div>
      <button type="button" class="btn ghost block" id="btn-clear-trash" style="margin-top:8px">Очистить корзину</button>
    </details>`
        : ""
    }

    <p class="footer-note">
      <a href="/bestpaints/docs/TOMORROW_PLAYBOOK.html" target="_blank" rel="noopener">Шпаргалка</a>
      · <a href="/bestpaints/docs/BestPaints_Obuchenie_v5.pdf?v=20260728a" target="_blank" rel="noopener">PDF</a>
      · <a href="/bestpaints/logout">Выйти</a>
    </p>
  `;
  $("#btn-new").onclick = () => newSurvey();
  app.querySelectorAll("[data-open]").forEach((btn) => {
    btn.onclick = () => openSurvey(btn.dataset.open);
  });
  app.querySelectorAll("[data-del]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.dataset.del;
      const s = store.get(id);
      if (!s) return;
      const name = surveyLabel(s);
      await softDelete({
        what: `объект «${name}»`,
        type: "survey",
        payload: cloneDeep(s),
        toastUndo,
        applyRemove: () => {
          store.remove(id);
          render();
        },
        applyRestore: (payload) => {
          store.upsert(payload);
          render();
        },
      });
    };
  });
  app.querySelectorAll("[data-restore]").forEach((btn) => {
    btn.onclick = () => restoreFromTrash(btn.dataset.restore);
  });
  app.querySelectorAll("[data-purge]").forEach((btn) => {
    btn.onclick = async () => {
      const ok = await askDelete("Удалить из корзины навсегда? Восстановить уже не получится.", {
        title: "Удалить навсегда?",
        confirmLabel: "Удалить навсегда",
        hint: false,
      });
      if (!ok) return;
      removeTrash(btn.dataset.purge);
      toast("Удалено навсегда");
      render();
    };
  });
  $("#btn-clear-trash")?.addEventListener("click", async () => {
    const ok = await askDelete("Очистить всю корзину? Восстановить будет нельзя.", {
      title: "Очистить корзину?",
      confirmLabel: "Очистить",
      hint: false,
    });
    if (!ok) return;
    clearTrash();
    toast("Корзина пуста");
    render();
  });

  mountHomeCrm({
    root: app,
    toast,
    getMeta: getCrmMeta,
    onOpenDetail: (oid) => openCrm(oid),
  });
}

function typeLabel(type) {
  return (
    {
      survey: "Объект",
      building: "Строение",
      wall: "Сторона / плоскость",
      opening: "Проём",
      building_photo: "Фото строения",
      wall_photo: "Фото стороны",
      custom_line: "Строка сметы",
    }[type] || type
  );
}

function restoreFromTrash(trashId) {
  const entry = getTrash(trashId);
  if (!entry) {
    toast("Уже нет в корзине");
    return;
  }
  const { type, payload, meta } = entry;
  try {
    if (type === "survey") {
      store.upsert(payload);
    } else if (type === "building") {
      const s = ensureSurveyForTrash(meta?.surveyId);
      if (!s) return;
      if (!s.buildings) s.buildings = [];
      if (!s.buildings.some((b) => b.id === payload.id)) s.buildings.push(payload);
      s.activeBuildingId = payload.id;
      store.upsert(s);
      if (survey?.id === s.id) {
        survey = s;
        render();
        removeTrash(trashId);
        toast("Строение восстановлено");
        return;
      }
    } else if (type === "wall") {
      const s = ensureSurveyForTrash(meta?.surveyId);
      const b = s?.buildings?.find((x) => x.id === meta.buildingId);
      if (!b) {
        toast("Сначала восстановите объект/строение");
        return;
      }
      if (!b.measure.walls) b.measure.walls = [];
      if (!b.measure.walls.some((w) => w.id === payload.id)) b.measure.walls.push(payload);
      syncAreasFromLists(b);
      store.upsert(s);
      if (survey?.id === s.id) survey = s;
    } else if (type === "opening") {
      const s = ensureSurveyForTrash(meta?.surveyId);
      const b = s?.buildings?.find((x) => x.id === meta.buildingId);
      if (!b) {
        toast("Сначала восстановите объект/строение");
        return;
      }
      if (!b.measure.openings) b.measure.openings = [];
      if (!b.measure.openings.some((o) => o.id === payload.id)) b.measure.openings.push(payload);
      syncAreasFromLists(b);
      store.upsert(s);
      if (survey?.id === s.id) survey = s;
    } else if (type === "building_photo") {
      const s = ensureSurveyForTrash(meta?.surveyId);
      const b = s?.buildings?.find((x) => x.id === meta.buildingId);
      if (!b) return toast("Строение не найдено");
      if (!b.photos) b.photos = [];
      if (!b.photos.some((p) => p.id === payload.id)) b.photos.push(payload);
      store.upsert(s);
      if (survey?.id === s.id) survey = s;
    } else if (type === "wall_photo") {
      const s = ensureSurveyForTrash(meta?.surveyId);
      const b = s?.buildings?.find((x) => x.id === meta.buildingId);
      const wall = b?.measure?.walls?.find((w) => w.id === meta.wallId);
      if (!wall) return toast("Сторона не найдена");
      if (!wall.photos) wall.photos = [];
      if (!wall.photos.some((p) => p.id === payload.id)) wall.photos.push(payload);
      store.upsert(s);
      if (survey?.id === s.id) survey = s;
    } else if (type === "custom_line") {
      const s = ensureSurveyForTrash(meta?.surveyId);
      if (!s) return;
      if (!s.estimate) s.estimate = {};
      if (!s.estimate.customLines) s.estimate.customLines = [];
      if (!s.estimate.customLines.some((x) => x.id === payload.id)) s.estimate.customLines.push(payload);
      store.upsert(s);
      if (survey?.id === s.id) survey = s;
    } else {
      toast("Неизвестный тип");
      return;
    }
    removeTrash(trashId);
    toast("Восстановлено");
    render();
  } catch (e) {
    toast("Не удалось восстановить");
  }
}

function ensureSurveyForTrash(surveyId) {
  if (survey?.id === surveyId) return survey;
  const s = store.get(surveyId);
  if (!s) {
    toast("Объект удалён — сначала восстановите объект из корзины");
    return null;
  }
  return s;
}

function renderWizard() {
  migrateSurvey(survey);
  const b = active();
  const stepMeta = STEPS[step];
  const stepId = stepMeta.id;
  const ready = readiness(survey);

  app.innerHTML = `
    <header class="topbar">
      <div class="brand">
        <strong>${escapeHtml(surveyLabel(survey))}</strong>
        <span>${escapeHtml(stepMeta.coach)}</span>
      </div>
      <div class="topbar-right">
        <span class="pct-pill ${ready.canLeave ? "ok" : ""}" title="Готовность замера">${ready.pct}%</span>
        <button class="btn ghost" id="btn-home">К списку</button>
      </div>
    </header>

    <div class="progress-track no-print"><i style="width:${((step + 1) / STEPS.length) * 100}%"></i></div>

    <nav class="steps">
      ${STEPS.map(
        (st, i) => `
        <button class="step-pill ${i === step ? "active" : ""} ${i < step ? "done" : ""}" data-step="${i}">
          ${st.icon}. ${st.title}
        </button>`
      ).join("")}
    </nav>

    ${stepId !== "client" ? buildingsBarHtml() : ""}
    ${!["client", "building"].includes(stepId) ? areaBadgeHtml() : ""}
    ${phaseBannerHtml(stepMeta)}

    <section class="card" id="step-body"></section>

    <div id="nav-hint" class="nav-hint callout danger no-print" hidden></div>
    <div class="nav-bar no-print">
      <div class="nav-inner">
        <button class="btn" id="btn-prev" ${step === 0 ? "disabled" : ""}>Назад</button>
        <button class="btn primary" id="btn-next">${
          step === STEPS.length - 1 ? "Готово" : nextLabel(stepId)
        }</button>
      </div>
    </div>
  `;

  clearNavHint();
  $("#btn-home").onclick = goHome;
  $("#btn-prev").onclick = () => {
    step = Math.max(0, step - 1);
    render();
  };
  $("#btn-next").onclick = () => {
    flushVisibleFields();
    if (!canLeaveStep(stepId)) return;
    if (step === STEPS.length - 1) {
      save();
      goHome();
      return;
    }
    step = Math.min(STEPS.length - 1, step + 1);
    render();
  };
  app.querySelectorAll("[data-step]").forEach((btn) => {
    btn.onclick = () => {
      const target = Number(btn.dataset.step);
      if (target > step) {
        flushVisibleFields();
        if (!canLeaveStep(stepId)) return;
      }
      step = target;
      render();
    };
  });
  app.querySelectorAll("[data-bid]").forEach((btn) => {
    btn.onclick = () => {
      survey.activeBuildingId = btn.dataset.bid;
      save();
      render();
    };
  });
  $("#btn-add-building")?.addEventListener("click", () => {
    const nb = emptyBuilding({
      name: `Строение ${survey.buildings.length + 1}`,
      kind: "garage",
    });
    survey.buildings.push(nb);
    survey.activeBuildingId = nb.id;
    save();
    step = STEPS.findIndex((s) => s.id === "building");
    if (step < 0) step = 1;
    render();
  });
  $("#btn-dup-building")?.addEventListener("click", () => {
    const nb = cloneBuilding(active());
    survey.buildings.push(nb);
    survey.activeBuildingId = nb.id;
    save();
    toast("Строение скопировано");
    render();
  });

  const body = $("#step-body");
  const map = {
    client: renderClient,
    building: renderBuilding,
    walls: renderWalls,
    openings: renderOpenings,
    more: renderMore,
    tech: renderTech,
    site: renderSite,
    estimate: renderEstimate,
  };
  map[stepId](body);
  bindKeypad(body);
}

function nextLabel(stepId) {
  return (
    {
      client: "К строению →",
      building: "К замеру →",
      walls: "К допам →",
      more: "В конструктор →",
      tech: "К договору →",
      site: "К смете →",
    }[stepId] || "Далее"
  );
}

function phaseBannerHtml(stepMeta) {
  const label = PHASE_LABELS[stepMeta.phase] || "";
  if (!label) return "";
  return `<div class="phase-banner no-print"><span>${escapeHtml(label)}</span> · шаг ${STEPS.findIndex((s) => s.id === stepMeta.id) + 1} из ${STEPS.length}</div>`;
}

function flushVisibleFields() {
  document.querySelectorAll("#step-body [data-path]").forEach((el) => {
    let val = el.type === "checkbox" ? el.checked : el.value;
    if (el.dataset.bool === "1") val = val === "true" || val === true;
    setDeep(el.dataset.path, val);
  });
}

function canLeaveStep(stepId) {
  if (stepId === "client") {
    if (!survey.title?.trim()) {
      return blockLeave("Укажите название проекта.", { focus: "#fld-title" });
    }
    if (!survey.client.name?.trim()) {
      return blockLeave("Укажите заказчика.", { focus: "#fld-client" });
    }
    if (!survey.client.address?.trim()) {
      return blockLeave("Укажите адрес объекта.", { focus: "#fld-address" });
    }
    if (!survey.contract.objectName?.trim()) {
      survey.contract.objectName = survey.title.trim();
    }
    return true;
  }
  if (stepId === "building") {
    const b = active();
    if (!b.name?.trim()) {
      setBuildingFlow(b, 1);
      save();
      paintBuildingFlow(document.getElementById("step-body") || document, 1);
      return blockLeave("Укажите название строения.", {
        focus: '[data-path="building.name"]',
      });
    }
    if (!b.zones?.facade && !b.zones?.interior) {
      setBuildingFlow(b, 2);
      save();
      paintBuildingFlow(document.getElementById("step-body") || document, 2);
      return blockLeave("Выберите зону работ: снаружи и/или внутри.", {
        focus: '[data-zone="facade"]',
      });
    }
    return true;
  }
  if (stepId === "walls") {
    syncAreasFromLists(active());
    if (num(active().measure.wallsArea) <= 0) {
      const len = document.querySelector('.wall-card.active [data-f="length"]');
      const h = document.querySelector('.wall-card.active [data-f="height"]');
      const focus = len && !String(len.value || "").trim() ? len : h || len;
      return blockLeave(
        "Замерьте хотя бы одну сторону: длина и высота (м) или «своя площадь». Калькулятор масштаба сам по себе не даёт м² — после расчёта нажмите «→ в длину активной плоскости».",
        { focus }
      );
    }
    return true;
  }
  return true;
}

function bindFields(root) {
  root.querySelectorAll("[data-path]").forEach((el) => {
    const path = el.dataset.path;
    const handler = () => {
      let val = el.type === "checkbox" ? el.checked : el.value;
      if (el.dataset.bool === "1") val = val === "true" || val === true;
      setDeep(path, val);
      if (path.includes("warm") || path.endsWith("warmMinus")) {
        syncWarmTotal(active().measure);
        const totalEl = root.querySelector("[data-path='building.measure.warmSeamTotal']");
        if (totalEl) totalEl.value = active().measure.warmSeamTotal;
        save();
        refreshBadge();
      }
      if (path.includes("endsArea") || path.includes("soffit") || path.includes("ceiling") || path.includes("roundCoef")) {
        refreshBadge();
      }
    };
    el.addEventListener("input", handler);
    el.addEventListener("change", handler);
  });
}

function vizCard(building, opts = {}) {
  const color = building.previewColor || "#c4a35a";
  const interactive = !!opts.interactive;
  return `
    <div class="viz-card ${interactive ? "pickable" : ""}" data-viz-bid="${building.id}">
      ${houseSvg(building, {
        width: 360,
        height: 210,
        color,
        interactive,
        activeWallId: opts.activeWallId || building.activeWallId || "",
      })}
      <div class="color-row no-print">
        <span class="hint">${interactive ? "Нажмите сторону на схеме" : "Цвет"} · ${escapeHtml(building.name)}</span>
        <div class="swatches">
          ${PREVIEW_COLORS.map(
            (c) => `
            <button type="button" class="swatch ${color === c.id ? "on" : ""}" data-color="${c.id}" data-for="${building.id}" title="${c.label}" style="background:${c.id}"></button>`
          ).join("")}
          <label class="swatch custom" title="Свой">
            <input type="color" value="${esc(color)}" data-color-custom data-for="${building.id}" />
          </label>
        </div>
      </div>
    </div>
  `;
}

function ensureActiveWall(b) {
  const walls = b.measure?.walls || [];
  if (!walls.length) {
    b.activeWallId = "";
    return null;
  }
  if (b._wallCollapsed) return null;
  if (!walls.some((w) => w.id === b.activeWallId)) {
    b.activeWallId = walls[0].id;
  }
  return walls.find((w) => w.id === b.activeWallId) || walls[0];
}

function setActiveWall(wallId) {
  const b = active();
  b.activeWallId = wallId;
  b._wallCollapsed = false;
  save();
  paintWallsList();
  refreshWallViz();
}

function nextWallAfter(b, wallId) {
  const walls = b.measure?.walls || [];
  const i = walls.findIndex((w) => w.id === wallId);
  if (i < 0) return null;
  const after = walls.slice(i + 1);
  const before = walls.slice(0, i);
  return (
    after.find((w) => wallAreaOf(w) <= 0) ||
    before.find((w) => wallAreaOf(w) <= 0) ||
    after[0] ||
    null
  );
}

function collapseActiveWall() {
  const b = active();
  const curId = b.activeWallId;
  const next = nextWallAfter(b, curId);
  if (next) {
    setActiveWall(next.id);
    document.getElementById("walls-list")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }
  b.activeWallId = "";
  b._wallCollapsed = true;
  save();
  paintWallsList();
  refreshWallViz();
}

function syncWallAttentionToSurvey(b) {
  if (!survey.attention) survey.attention = {};
  for (const el of WALL_ATTENTION) {
    const sum = (b.measure?.walls || []).reduce((s, w) => s + num(w.attention?.[el.id]), 0);
    if (sum > 0) survey.attention[el.id] = sum;
  }
}

function wallOpeningsOf(b, wallId) {
  return (b.measure.openings || []).filter((o) => o.wallId === wallId);
}

function wallBundleHtml(w, b) {
  const endsA = wallEndsAreaOf(w);
  const ops = wallOpeningsOf(b, w.id);
  const att = w.attention || {};
  const next = nextWallAfter(b, w.id);
  const doneLabel = next
    ? `Готово · ${escapeHtml(next.label || "следующая сторона")} →`
    : "Готово · свернуть";
  return `
    <section class="wall-bundle">
      <h4 class="wall-bundle-title">На этой стороне · сразу всё</h4>
      <p class="hint wall-bundle-hint">Торцы, проёмы, наличники и помехи — чтобы не обходить дом по кругу.</p>

      <div class="wall-bundle-block">
        <label class="wall-check">
          <input type="checkbox" data-wf="endsOn" ${w.endsOn || num(w.endsCount) || num(w.endsLength) ? "checked" : ""} />
          Торцы / перерубы
        </label>
        <div class="wall-ends-grid" ${!(w.endsOn || num(w.endsCount) || num(w.endsLength)) ? "hidden" : ""} data-ends-box>
          <div class="field"><label>Выступ, м</label>
            <input data-wf="endsDepth" value="${esc(w.endsDepth ?? "0.2")}" inputmode="decimal" placeholder="0.2"></div>
          <div class="field"><label>Кол-во торцов</label>
            <input data-wf="endsCount" value="${esc(w.endsCount)}" inputmode="numeric" placeholder="2"></div>
          <div class="field"><label>Или длина, пог.м</label>
            <input data-wf="endsLength" value="${esc(w.endsLength)}" inputmode="decimal" placeholder="авто × высота"></div>
          <div class="field"><label>Вручную, м²</label>
            <input data-wf="endsAreaManual" value="${esc(w.endsAreaManual)}" inputmode="decimal"></div>
          <label class="wall-check span2">
            <input type="checkbox" data-wf="endsWithSides" ${w.endsWithSides ? "checked" : ""} />
            С боками (+площадь, ×3)
          </label>
          <div class="wall-ends-sum">Площадь торцов: <b data-ends-sum>${endsA ? endsA.toFixed(2) : "—"}</b> м²</div>
        </div>
      </div>

      <div class="wall-bundle-block">
        <div class="wall-bundle-row">
          <strong>Проёмы на стороне</strong>
          <div class="wall-bundle-actions">
            <button type="button" class="btn ghost sm" data-wall-add-op="Окно">+ окно</button>
            <button type="button" class="btn ghost sm" data-wall-add-op="${b.kind === "garage" ? "Ворота" : "Дверь"}">+ ${b.kind === "garage" ? "ворота" : "дверь"}</button>
          </div>
        </div>
        <div class="wall-ops-inline" data-wall-ops>
          ${
            ops.length
              ? ops
                  .map((o) => {
                    const oa = Math.round(num(o.width) * num(o.height) * 100) / 100;
                    return `
              <div class="wall-op-row" data-oid="${o.id}">
                <input class="wall-op-label" data-of="label" value="${esc(o.label)}" />
                <input data-of="width" value="${esc(o.width)}" inputmode="decimal" placeholder="Ш, м" />
                <input data-of="height" value="${esc(o.height)}" inputmode="decimal" placeholder="В, м" />
                <span class="wall-op-area">${oa ? oa.toFixed(1) : "—"}</span>
                <button type="button" class="btn ghost sm" data-wall-op-del="${o.id}" title="Удалить">✕</button>
              </div>`;
                  })
                  .join("")
              : `<p class="hint soft">Нет проёмов — добавьте окно/дверь на этой стороне</p>`
          }
        </div>
      </div>

      <div class="wall-bundle-block">
        <div class="field">
          <label>Наличники на стороне, пог.м</label>
          <input data-wf="trimLength" value="${esc(w.trimLength)}" inputmode="decimal" placeholder="суммируется в допы">
        </div>
      </div>

      <div class="wall-bundle-block">
        <strong>Помехи на стороне</strong>
        <div class="wall-att-grid">
          ${WALL_ATTENTION.map((el) => {
            const v = att[el.id] || 0;
            return `
            <div class="wall-att-item">
              <span>${el.label}</span>
              <div class="counter sm">
                <button type="button" data-wall-att-dec="${el.id}">−</button>
                <input data-wall-att="${el.id}" value="${v}" inputmode="numeric">
                <button type="button" data-wall-att-inc="${el.id}">+</button>
              </div>
            </div>`;
          }).join("")}
        </div>
      </div>

      <button type="button" class="btn primary block wall-collapse-btn" data-wall-collapse>${doneLabel}</button>
    </section>`;
}

function refreshWallViz() {
  const card = document.querySelector(".viz-card.pickable");
  if (!card) return;
  const b = active();
  const wrap = document.createElement("div");
  wrap.innerHTML = vizCard(b, { interactive: true, activeWallId: b.activeWallId });
  card.replaceWith(wrap.firstElementChild);
  bindVizColors(document.getElementById("step-body") || app);
  bindFaceClicks(document.getElementById("step-body") || app);
}

function bindFaceClicks(root) {
  root.querySelectorAll(".house-face[data-wall-id]").forEach((el) => {
    el.onclick = (e) => {
      e.stopPropagation();
      const id = el.getAttribute("data-wall-id");
      if (id) setActiveWall(id);
    };
  });
}

function bindVizColors(root) {
  const remount = (b) => {
    const card = root.querySelector(`.viz-card[data-viz-bid="${b.id}"]`);
    if (!card) {
      refreshBadge();
      return;
    }
    const interactive = card.classList.contains("pickable");
    const wrap = document.createElement("div");
    wrap.innerHTML = vizCard(b, {
      interactive,
      activeWallId: b.activeWallId,
    });
    card.replaceWith(wrap.firstElementChild);
    bindVizColors(root);
    if (interactive) bindFaceClicks(root);
  };
  root.querySelectorAll("[data-color]").forEach((btn) => {
    btn.onclick = () => {
      const bid = btn.dataset.for;
      const b = survey.buildings.find((x) => x.id === bid) || active();
      b.previewColor = btn.dataset.color;
      save();
      remount(b);
    };
  });
  root.querySelectorAll("[data-color-custom]").forEach((custom) => {
    custom.oninput = () => {
      const bid = custom.dataset.for;
      const b = survey.buildings.find((x) => x.id === bid) || active();
      b.previewColor = custom.value;
      save();
      remount(b);
    };
  });
}

function refreshBadge() {
  const badge = app.querySelector(".area-badge");
  if (badge) {
    const wrap = document.createElement("div");
    wrap.innerHTML = areaBadgeHtml();
    badge.replaceWith(wrap.firstElementChild);
  }
  const viz = app.querySelector(".viz-card");
  if (viz) {
    const parent = viz.parentElement;
    const interactive = viz.classList.contains("pickable");
    const wrap2 = document.createElement("div");
    wrap2.innerHTML = vizCard(active(), {
      interactive,
      activeWallId: active().activeWallId,
    });
    viz.replaceWith(wrap2.firstElementChild);
    if (parent) {
      bindVizColors(parent);
      if (interactive) bindFaceClicks(parent);
    }
  }
  const pill = app.querySelector(".topbar .pct-pill");
  if (pill && survey) {
    const r = readiness(survey);
    pill.textContent = `${r.pct}%`;
    pill.classList.toggle("ok", r.canLeave);
  }
  app.querySelectorAll(".formula-card").forEach((el) => {
    const zone = el.dataset.formulaZone || "facade";
    const wrap = document.createElement("div");
    wrap.innerHTML = formulaHtml(active(), zone);
    el.replaceWith(wrap.firstElementChild);
  });
}

/* ——— 1. Проект (пошагово) ——— */
function renderClient(root) {
  const c = survey.client;
  const title = survey.title || "";
  const hasTitle = Boolean(title.trim());
  const hasClient = Boolean((c.name || "").trim());
  const hasAddress = Boolean((c.address || "").trim());

  root.innerHTML = `
    <h2 class="section-title">Новый проект</h2>
    <p class="section-sub">Поля открываются по очереди — сначала название, потом клиент, потом адрес.</p>
    ${tipBlock("client")}

    <div class="flow-step open" data-flow="title">
      <div class="flow-step-num">1</div>
      <div class="flow-step-body">
        <div class="field">
          <label>Название проекта</label>
          <input data-path="title" id="fld-title" value="${esc(title)}" placeholder="Например: Дом на Ленинской" autocomplete="off">
        </div>
      </div>
    </div>

    <div class="flow-step ${hasTitle ? "open" : "locked"}" data-flow="client" id="flow-client">
      <div class="flow-step-num">2</div>
      <div class="flow-step-body">
        <div class="field">
          <label>Заказчик</label>
          <input data-path="client.name" id="fld-client" value="${esc(c.name)}" placeholder="ФИО" ${hasTitle ? "" : "disabled"}>
        </div>
        ${
          hasClient
            ? `<div class="grid two reveal">
          <div class="field"><label>Телефон</label><input data-path="client.phone" value="${esc(c.phone)}" placeholder="+7…" inputmode="tel"></div>
          <div class="field"><label>Замерщик</label><input data-path="client.surveyor" value="${esc(c.surveyor)}" placeholder="Ваше имя"></div>
        </div>`
            : ""
        }
      </div>
    </div>

    <div class="flow-step ${hasClient ? "open" : "locked"}" data-flow="address" id="flow-address">
      <div class="flow-step-num">3</div>
      <div class="flow-step-body">
        <div class="field">
          <label>Адрес объекта</label>
          <input data-path="client.address" id="fld-address" value="${esc(c.address)}" placeholder="Посёлок / КП / улица / участок" ${hasClient ? "" : "disabled"}>
        </div>
        ${
          hasAddress
            ? `<div class="field reveal">
          <label>Email (необязательно)</label>
          <input data-path="client.email" value="${esc(c.email)}" placeholder="для сметы" inputmode="email">
        </div>
        <div class="callout ok reveal">Проект готов — дальше строение и замер.</div>`
            : ""
        }
      </div>
    </div>
  `;

  bindFields(root);

  const titleEl = $("#fld-title", root);
  const clientEl = $("#fld-client", root);
  const addressEl = $("#fld-address", root);

  const syncTitleContract = () => {
    const t = (survey.title || "").trim();
    if (t && !survey.contract.objectName?.trim()) survey.contract.objectName = t;
    save();
  };

  titleEl?.addEventListener("input", () => {
    // Не вызываем render() на каждом символе — ломает набор названия.
    syncTitleContract();
    const open = Boolean(titleEl.value.trim());
    const block = $("#flow-client", root);
    block?.classList.toggle("open", open);
    block?.classList.toggle("locked", !open);
    if (clientEl) clientEl.disabled = !open;
  });
  titleEl?.addEventListener("change", () => {
    syncTitleContract();
    render();
  });
  titleEl?.addEventListener("blur", () => {
    if (titleEl.value.trim()) {
      syncTitleContract();
      render();
    }
  });

  clientEl?.addEventListener("change", () => render());
  clientEl?.addEventListener("blur", () => {
    if (clientEl.value.trim()) render();
  });
  addressEl?.addEventListener("change", () => render());
  addressEl?.addEventListener("blur", () => {
    if (addressEl.value.trim()) render();
  });
}

/* ——— 2. Строение ——— */
function buildingFlowOf(b) {
  const n = Number(b?._buildingFlow);
  return Number.isFinite(n) && n >= 1 && n <= 4 ? n : 1;
}

function setBuildingFlow(b, n) {
  b._buildingFlow = Math.max(1, Math.min(4, Number(n) || 1));
}

function paintBuildingFlow(root, openN) {
  root.querySelectorAll(".flow-step[data-flow]").forEach((s) => {
    s.classList.toggle("open", Number(s.dataset.flow) === openN);
  });
}

function flowNextBtn(next, label) {
  return `<button type="button" class="btn primary flow-next" data-flow-next="${esc(String(next))}">${esc(label)}</button>`;
}

function renderBuilding(root) {
  const b = active();
  const roof = ROOF_TYPES.find((r) => r.id === b.roofType) || ROOF_TYPES[0];
  const flow = buildingFlowOf(b);

  root.innerHTML = `
    <div class="building-toolbar">
      <h2 class="section-title" style="margin:0">Строение</h2>
      ${
        survey.buildings.length > 1
          ? `<button type="button" class="btn ghost" id="btn-del-building">Удалить строение</button>`
          : ""
      }
    </div>
    <p class="section-sub">Что красим на участке. После этого — замер сторон. Выбор не прыгает сам — жмите «Далее».</p>
    ${tipBlock("building")}

    <div class="flow-step ${flow === 1 ? "open" : ""}" data-flow="1">
      <button type="button" class="flow-step-num" data-flow-tog="1">1</button>
      <div class="flow-step-main">
        <button type="button" class="flow-step-cap" data-flow-tog="1">Тип объекта</button>
        <div class="flow-step-body">
          <div class="field">
            <label>Название строения</label>
            <input data-path="building.name" value="${esc(b.name)}" placeholder="Дом / Баня / Гараж…">
          </div>
          <label class="hint" style="display:block;margin:12px 0 8px">Тип объекта</label>
          <div class="choice-grid compact">
            ${OBJECT_KINDS.map(
              (k) => `
              <button type="button" class="choice ${b.kind === k.id ? "selected" : ""}" data-kind="${k.id}">
                <strong>${k.title}</strong><span>${k.hint}</span>
              </button>`
            ).join("")}
          </div>
          ${flowNextBtn(2, "Далее →")}
        </div>
      </div>
    </div>

    <div class="flow-step ${flow === 2 ? "open" : ""}" data-flow="2">
      <button type="button" class="flow-step-num" data-flow-tog="2">2</button>
      <div class="flow-step-main">
        <button type="button" class="flow-step-cap" data-flow-tog="2">Зоны работ · фасад и/или интерьер</button>
        <div class="flow-step-body">
          <div class="zone-toggles">
            ${WORK_ZONES.map(
              (z) => `
              <label class="choice zone-check ${b.zones?.[z.id] ? "selected" : ""}">
                <input type="checkbox" data-zone="${z.id}" ${b.zones?.[z.id] ? "checked" : ""}>
                <span><strong>${z.title}</strong><br><span class="hint">${z.hint}</span></span>
              </label>`
            ).join("")}
          </div>
          <p class="hint">Стены — на шаге «Замер». Подшива, лобовая, столбы, потолки — на шаге «Допы».</p>
          ${
            b.kind === "fence"
              ? `<label class="check-inline" style="margin-top:12px;display:flex">
                  <input type="checkbox" id="fence-both" ${b.fenceBothSides ? "checked" : ""}>
                  Красим забор с двух сторон (×2 к площади)
                </label>`
              : `<label class="check-inline" style="margin-top:12px;display:flex">
                  <input type="checkbox" id="plinth-skip" ${b.plinthSkip ? "checked" : ""}>
                  Цоколь камень/кирпич — не красим
                </label>
                ${b.plinthSkip ? `<div class="field" style="margin-top:8px"><label>Заметка по цоколю</label><input data-path="building.measure.plinthNote" value="${esc(b.measure.plinthNote)}" placeholder="высота / материал"></div>` : ""}`
          }
          ${flowNextBtn(3, "Далее →")}
        </div>
      </div>
    </div>

    <div class="flow-step ${flow === 3 ? "open" : ""}" data-flow="3">
      <button type="button" class="flow-step-num" data-flow-tog="3">3</button>
      <div class="flow-step-main">
        <button type="button" class="flow-step-cap" data-flow-tog="3">Крыша / силуэт</button>
        <div class="flow-step-body">
          <div class="choice-grid compact">
            ${ROOF_TYPES.map(
              (r) => `
              <button type="button" class="choice ${b.roofType === r.id ? "selected" : ""}" data-roof="${r.id}">
                <strong>${r.title}</strong><span>${r.tip}</span>
              </button>`
            ).join("")}
          </div>
          <div class="callout ok" id="roof-tip">${escapeHtml(roof.tip)}</div>
          ${flowNextBtn(4, "Далее →")}
        </div>
      </div>
    </div>

    <div class="flow-step ${flow === 4 ? "open" : ""}" data-flow="4">
      <button type="button" class="flow-step-num" data-flow-tog="4">4</button>
      <div class="flow-step-main">
        <button type="button" class="flow-step-cap" data-flow-tog="4">Покрытие и материал</button>
        <div class="flow-step-body">
          <div class="choice-grid">
            ${HOUSE_TYPES.map(
              (t) => `
              <button type="button" class="choice ${b.houseType === t.id ? "selected" : ""}" data-htype="${t.id}">
                <strong>${t.title}</strong><span>${t.hint}</span>
              </button>`
            ).join("")}
          </div>
          <div class="grid two" style="margin-top:14px">
            <div class="field">
              <label>Материал</label>
              <select data-path="building.material" id="mat-select">
                ${MATERIAL_OPTIONS.map(
                  (m) => `<option value="${m.id}" ${b.material === m.id ? "selected" : ""}>${m.label}</option>`
                ).join("")}
              </select>
            </div>
            <div class="field">
              <label>Сечение / Ø</label>
              <input data-path="building.materialSize" value="${esc(b.materialSize)}" placeholder="200×200 / Ø240">
            </div>
          </div>
          <div class="callout" id="k-hint"></div>
          <p class="hint" style="margin:12px 0 4px">Длину и высоту сторон вводите на следующем шаге «Замер» — здесь габариты не нужны.</p>
          ${vizCard(b)}
          ${photosHtml(b)}
          ${flowNextBtn("walls", "К замеру →")}
        </div>
      </div>
    </div>
  `;

  bindFields(root);
  bindVizColors(root);
  bindPhotos(root, b);
  updateKHint();

  const openFlow = (n) => {
    setBuildingFlow(b, n);
    save();
    paintBuildingFlow(root, buildingFlowOf(b));
  };

  root.querySelectorAll("[data-flow-tog]").forEach((btn) => {
    btn.onclick = () => openFlow(btn.getAttribute("data-flow-tog"));
  });
  root.querySelectorAll("[data-flow-next]").forEach((btn) => {
    btn.onclick = () => {
      const next = btn.getAttribute("data-flow-next");
      if (next === "walls") {
        flushVisibleFields();
        const leaveId = "building";
        if (!canLeaveStep(leaveId)) return;
        const idx = STEPS.findIndex((s) => s.id === "walls");
        if (idx >= 0) {
          step = idx;
          render();
        } else {
          $("#btn-next")?.click();
        }
        return;
      }
      openFlow(next);
      root.querySelector(`.flow-step[data-flow="${next}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
  });

  $("#btn-del-building", root)?.addEventListener("click", async () => {
    if (survey.buildings.length <= 1) return;
    const target = active();
    const snap = cloneDeep(target);
    await softDelete({
      what: `строение «${target.name || "без названия"}»`,
      type: "building",
      payload: snap,
      meta: { surveyId: survey.id },
      toastUndo,
      applyRemove: () => {
        survey.buildings = survey.buildings.filter((x) => x.id !== target.id);
        survey.activeBuildingId = survey.buildings[0].id;
        save();
        render();
      },
      applyRestore: (payload) => {
        if (!survey.buildings.some((x) => x.id === payload.id)) {
          survey.buildings.push(payload);
        }
        survey.activeBuildingId = payload.id;
        save();
        render();
      },
    });
  });

  root.querySelectorAll("[data-kind]").forEach((btn) => {
    btn.onclick = () => {
      setBuildingFlow(active(), 1);
      applyKindPreset(active(), btn.dataset.kind);
      active().measure.roundCoef = coefForMaterial(active().material);
      save();
      render();
    };
  });
  root.querySelectorAll("[data-roof]").forEach((btn) => {
    btn.onclick = () => {
      const cur = active();
      setBuildingFlow(cur, 3);
      cur.roofType = btn.dataset.roof;
      if (["gable", "broken"].includes(btn.dataset.roof)) {
        const walls = cur.measure.walls || [];
        const ends = walls.filter((w) => /главн|задн|фронтон|а\b|в\b/i.test(w.label || ""));
        const targets = ends.length >= 2 ? ends.slice(0, 2) : [walls[0], walls[2]].filter(Boolean);
        for (const w of targets) {
          if (w && !num(w.length)) w.shape = "gable";
        }
      }
      save();
      // без полного render — только подсветка и подсказка
      root.querySelectorAll("[data-roof]").forEach((el) => {
        el.classList.toggle("selected", el.dataset.roof === btn.dataset.roof);
      });
      const tip = ROOF_TYPES.find((r) => r.id === btn.dataset.roof);
      const tipEl = root.querySelector("#roof-tip");
      if (tipEl && tip) tipEl.textContent = tip.tip;
    };
  });
  root.querySelectorAll("[data-htype]").forEach((btn) => {
    btn.onclick = () => {
      const cur = active();
      setBuildingFlow(cur, 4);
      cur.houseType = btn.dataset.htype;
      cur.tech.techId = defaultTechId(cur.houseType, cur.condition, cur.material);
      save();
      root.querySelectorAll("[data-htype]").forEach((el) => {
        el.classList.toggle("selected", el.dataset.htype === btn.dataset.htype);
      });
    };
  });
  root.querySelectorAll("[data-zone]").forEach((inp) => {
    inp.onchange = () => {
      active().zones[inp.dataset.zone] = inp.checked;
      inp.closest(".zone-check")?.classList.toggle("selected", inp.checked);
      save();
    };
  });
  $("#fence-both", root)?.addEventListener("change", (e) => {
    active().fenceBothSides = e.target.checked;
    syncAreasFromLists(active());
    save();
    refreshBadge();
    toast(e.target.checked ? "Площадь забора ×2" : "Одна сторона");
  });
  $("#plinth-skip", root)?.addEventListener("change", (e) => {
    setBuildingFlow(active(), 2);
    active().plinthSkip = e.target.checked;
    save();
    render();
  });
  $("#mat-select", root)?.addEventListener("change", () => {
    active().measure.roundCoef = coefForMaterial(active().material);
    save();
    updateKHint();
  });
}

function updateKHint() {
  const el = $("#k-hint");
  if (!el) return;
  const b = active();
  const k = coefForMaterial(b.material);
  const names = {
    beam: "брус — почти плоские стены",
    log: "оцилиндровка — K увеличивает площадь",
    hand_log: "рубленое — сложный профиль, мин. 2 прохода",
    imit: "имитация / планкен — обычно K=1",
    block: "блок-хаус — небольшой запас K",
    board: "доска / вагонка — K=1",
    other: "проверьте K вручную на шаге стен",
  };
  el.innerHTML = `<b>K = ${k}</b> — ${names[b.material] || ""}. Для забора K обычно 1.`;
}

/* ——— 2. Замер сторон ——— */
function renderWalls(root) {
  const b = active();
  ensureActiveWall(b);
  const roof = ROOF_TYPES.find((r) => r.id === b.roofType);
  const kMatch = ROUND_COEF.find((c) => c.value != null && Number(b.measure.roundCoef) === c.value);
  const kCustom = !kMatch;

  root.innerHTML = `
    <h2 class="section-title">Замер · ${escapeHtml(b.name)}</h2>
    <p class="section-sub">Обход по часовой: выберите сторону → размеры → фото. ${roof ? escapeHtml(roof.title) : ""}</p>
    ${tipBlock("walls")}
    ${b.zones?.facade ? formulaHtml(b, "facade") : ""}
    ${b.zones?.interior ? formulaHtml(b, "interior") : ""}

    <div class="side-strip" id="side-strip"></div>
    ${vizCard(b, { interactive: true, activeWallId: b.activeWallId })}

    <div id="walls-list" class="walls-list"></div>

    <details class="premium-details">
      <summary>K и масштаб по проекту</summary>
      <div class="grid two" style="margin-top:10px">
        <div class="field">
          <label>Коэффициент K (фасад)</label>
          <select id="coef-preset">
            ${ROUND_COEF.map((c) => {
              const sel =
                c.id === "custom"
                  ? kCustom
                    ? "selected"
                    : ""
                  : c.value != null && Number(b.measure.roundCoef) === c.value
                    ? "selected"
                    : "";
              return `<option value="${c.id}" ${sel}>${c.label}</option>`;
            }).join("")}
          </select>
        </div>
        <div class="field">
          <label>Свой K</label>
          <input id="coef-custom" value="${esc(b.measure.roundCoef)}" inputmode="decimal">
        </div>
      </div>
      ${scalePanelHtml(survey._scale || {})}
    </details>

    <div class="callout compact" style="margin-top:12px">
      Σ плоскостей <b id="walls-sum">0</b> м²
      · фасад ${calcWallArea(b.measure, "facade").walls.toFixed(1)}
      · интерьер ${calcWallArea(b.measure, "interior").walls.toFixed(1)}
    </div>
    ${
      num(b.measure.wallsArea) <= 0
        ? `<div class="callout danger compact" id="walls-need-measure">
            Чтобы идти дальше — введите <b>длину</b> и <b>высоту</b> хотя бы одной стороны (или свою площадь).
            Проёмы и торцы заполняйте на каждой стороне здесь же.
          </div>`
        : ""
    }
  `;

  paintWallsList();
  bindVizColors(root);
  bindFaceClicks(root);
  bindScalePanel(root, {
    onChange: (state) => {
      survey._scale = state;
      save();
    },
    onToWall: (meters) => {
      const wall = ensureActiveWall(active());
      if (!wall) return;
      wall.length = String(meters);
      syncAreasFromLists(active());
      save();
      paintWallsList();
      refreshBadge();
      toast(`Длина «${wall.label}» = ${meters} м`);
    },
    onToOpen: (meters) => {
      if (!active().measure.openings?.length) addOpening("Окно");
      const o = active().measure.openings[0];
      o.width = String(meters);
      syncAreasFromLists(active());
      save();
      toast(`Ширина проёма = ${meters} м`);
    },
  });

  $("#coef-preset", root).onchange = (e) => {
    const opt = ROUND_COEF.find((c) => c.id === e.target.value);
    if (opt?.value != null) {
      b.measure.roundCoef = opt.value;
      $("#coef-custom", root).value = opt.value;
      save();
      refreshBadge();
      updateWallsSum();
    }
  };
  $("#coef-custom", root).oninput = (e) => {
    b.measure.roundCoef = num(e.target.value, 1);
    const sel = $("#coef-preset", root);
    if (sel) sel.value = "custom";
    save();
    refreshBadge();
    updateWallsSum();
  };
}

function paintSideStrip() {
  const strip = $("#side-strip");
  if (!strip) return;
  const b = active();
  const walls = b.measure.walls || [];
  ensureActiveWall(b);
  strip.innerHTML = `
    ${walls
      .map((w, i) => {
        const done = wallAreaOf(w) > 0;
        const on = w.id === b.activeWallId;
        return `<button type="button" class="side-chip ${on ? "on" : ""} ${done ? "done" : ""}" data-pick="${w.id}">
          <i>${i + 1}</i><span>${escapeHtml(w.label || "Сторона")}</span>${done ? "<em>✓</em>" : ""}${w.note?.trim() ? "<em title=\"есть комментарий\">💬</em>" : ""}
        </button>`;
      })
      .join("")}
    <button type="button" class="side-chip add" id="btn-add-wall">+</button>
  `;
  strip.querySelectorAll("[data-pick]").forEach((btn) => {
    btn.onclick = () => setActiveWall(btn.dataset.pick);
  });
  $("#btn-add-wall", strip).onclick = () => {
    const nb = {
      id: uid(),
      label: `Плоскость ${walls.length + 1}`,
      shape: "rect",
      length: "",
      height: "",
      height2: "",
      ridge: "",
      areaManual: "",
      zone: b.zones?.facade ? "facade" : "interior",
      note: "",
      material: "",
      condition: "",
      coatingWant: "",
      flags: {},
      damageArea: "",
      photos: [],
    };
    b.measure.walls.push(nb);
    b.activeWallId = nb.id;
    save();
    paintWallsList();
    refreshWallViz();
  };
}

function paintWallsList() {
  const list = $("#walls-list");
  if (!list) return;
  const b = active();
  const walls = b.measure.walls;
  ensureActiveWall(b);
  const zoneOpts = WORK_ZONES.filter((z) => b.zones?.[z.id]);
  paintSideStrip();

  list.innerHTML = walls
    .map((w, i) => {
      const area = wallAreaOf(w);
      const hasPhoto = (w.photos || []).length > 0;
      const on = w.id === b.activeWallId;
      if (!on) {
        return `
        <button type="button" class="wall-card collapsed ${hasPhoto ? "has-photo" : ""} ${area ? "measured" : ""} ${w.note?.trim() ? "has-note" : ""}" data-pick="${w.id}">
          <span class="wc-idx">${i + 1}</span>
          <span class="wc-name">${escapeHtml(w.label || "Сторона")}${w.note?.trim() ? " · 💬" : ""}</span>
          <span class="wc-meta">${WALL_SHAPES.find((s) => s.id === w.shape)?.title || ""} · ${area ? area.toFixed(1) + " м²" : "—"}</span>
          <span class="wc-go">›</span>
        </button>`;
      }
      return `
      <article class="wall-card active ${hasPhoto ? "has-photo" : "need-photo"}" data-wid="${w.id}">
        <div class="wall-card-head">
          <span class="wc-idx on">${i + 1}</span>
          <input class="wall-label" data-f="label" value="${esc(w.label)}" placeholder="Название стороны">
          <button type="button" class="btn ghost sm" data-wall-collapse title="Свернуть без удаления">Свернуть</button>
          <button type="button" class="btn ghost" data-del="${w.id}" ${walls.length <= 1 ? "disabled" : ""} title="Удалить сторону">✕</button>
        </div>
        <p class="wall-step-hint">${sideHint(i, b.kind)}</p>
        <div class="wall-meta">
          <select data-f="shape">
            ${WALL_SHAPES.map(
              (s) => `<option value="${s.id}" ${w.shape === s.id ? "selected" : ""}>${s.title}</option>`
            ).join("")}
          </select>
          <select data-f="zone">
            ${(zoneOpts.length ? zoneOpts : WORK_ZONES)
              .map(
                (z) =>
                  `<option value="${z.id}" ${(w.zone || "facade") === z.id ? "selected" : ""}>${z.title}</option>`
              )
              .join("")}
          </select>
        </div>
        <div class="wall-card-grid ${w.shape === "custom" ? "custom" : ""}">
          ${
            w.shape === "custom"
              ? `<div class="field" style="grid-column:1/-2"><label>Площадь, м²</label>
                 <input data-f="areaManual" value="${esc(w.areaManual)}" inputmode="decimal"></div>`
              : `
            <div class="field"><label>Длина, м</label><input data-f="length" value="${esc(w.length)}" inputmode="decimal" placeholder="12.5"></div>
            <div class="field"><label>${w.shape === "trap" ? "Высота 1, м" : "Высота, м"}</label>
              <input data-f="height" value="${esc(w.height)}" inputmode="decimal" placeholder="3.2"></div>
            ${
              w.shape === "gable"
                ? `<div class="field"><label>До конька, м</label><input data-f="ridge" value="${esc(w.ridge)}" inputmode="decimal" placeholder="5.5"></div>`
                : ""
            }
            ${
              w.shape === "trap"
                ? `<div class="field"><label>Высота 2, м</label><input data-f="height2" value="${esc(w.height2)}" inputmode="decimal" placeholder="4.0"></div>`
                : ""
            }`
          }
          <div class="wall-area"><span>Площадь</span><b>${area ? area.toFixed(1) : "—"} м²</b></div>
        </div>
        <div class="field wall-comment">
          <label>Комментарий к стороне</label>
          <textarea data-f="note" rows="2" placeholder="Напр.: гниль у цоколя · снять гирлянду · цвет темнее">${esc(w.note)}</textarea>
        </div>
        <div class="flag-row">
          ${WALL_FLAGS.map((f) => `
            <button type="button" class="flag-chip ${w.flags?.[f.id] ? "on" : ""}" data-flag="${f.id}">${f.label}</button>
          `).join("")}
        </div>
        ${
          w.flags?.rot || w.flags?.wet
            ? `<div class="field"><label>Площадь ремонта, м²</label><input data-f="damageArea" value="${esc(w.damageArea)}" inputmode="decimal" placeholder="идёт в смету"></div>`
            : ""
        }
        ${wallPhotosHtml(w)}
        ${wallBundleHtml(w, b)}
        <details class="wall-extra">
          <summary>Материал стороны (если отличается)</summary>
          <div class="wall-meta materials">
            <select data-f="material">
              <option value="">Как у строения</option>
              ${MATERIAL_OPTIONS.map(
                (m) => `<option value="${m.id}" ${w.material === m.id ? "selected" : ""}>${m.label}</option>`
              ).join("")}
            </select>
            <select data-f="condition">
              ${WALL_CONDITIONS.map(
                (c) => `<option value="${c.id}" ${w.condition === c.id ? "selected" : ""}>${c.label}</option>`
              ).join("")}
            </select>
            <select data-f="coatingWant">
              ${COATING_WANT.map(
                (c) => `<option value="${c.id}" ${w.coatingWant === c.id ? "selected" : ""}>${c.label}</option>`
              ).join("")}
            </select>
          </div>
        </details>
      </article>`;
    })
    .join("");

  list.querySelectorAll("[data-pick]").forEach((btn) => {
    btn.onclick = () => setActiveWall(btn.dataset.pick);
  });

  list.querySelectorAll(".wall-card.active").forEach((card) => {
    const id = card.dataset.wid;
    card.querySelectorAll("[data-f]").forEach((inp) => {
      const ev = inp.tagName === "SELECT" ? "change" : "input";
      inp.addEventListener(ev, () => {
        const wall = b.measure.walls.find((x) => x.id === id);
        if (!wall) return;
        wall[inp.dataset.f] = inp.value;
        syncAreasFromLists(b);
        save();
      if (inp.dataset.f === "shape" || inp.dataset.f === "zone") {
          paintWallsList();
          refreshWallViz();
        } else if (inp.dataset.f === "note") {
          paintSideStrip();
        } else {
          const areaEl = card.querySelector(".wall-area b");
          if (areaEl) {
            const a = wallAreaOf(wall);
            areaEl.textContent = `${a ? a.toFixed(1) : "—"} м²`;
          }
          const endsEl = card.querySelector("[data-ends-sum]");
          if (endsEl) {
            const ea = wallEndsAreaOf(wall);
            endsEl.textContent = ea ? ea.toFixed(2) : "—";
          }
          updateWallsSum();
          refreshBadge();
          paintSideStrip();
        }
      });
    });
  });
  list.querySelectorAll("[data-del]").forEach((btn) => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const wall = b.measure.walls.find((w) => w.id === btn.dataset.del);
      if (!wall || b.measure.walls.length <= 1) return;
      const snap = cloneDeep(wall);
      const idx = b.measure.walls.findIndex((w) => w.id === wall.id);
      await softDelete({
        what: `сторону «${wall.label || "плоскость"}»`,
        type: "wall",
        payload: snap,
        meta: { surveyId: survey.id, buildingId: b.id, index: idx },
        toastUndo,
        applyRemove: () => {
          b.measure.walls = b.measure.walls.filter((w) => w.id !== wall.id);
          ensureActiveWall(b);
          syncAreasFromLists(b);
          save();
          paintWallsList();
          refreshWallViz();
          refreshBadge();
        },
        applyRestore: (payload, meta) => {
          if (!b.measure.walls.some((w) => w.id === payload.id)) {
            const at = Math.min(meta?.index ?? b.measure.walls.length, b.measure.walls.length);
            b.measure.walls.splice(at, 0, payload);
          }
          b.activeWallId = payload.id;
          ensureActiveWall(b);
          syncAreasFromLists(b);
          save();
          paintWallsList();
          refreshWallViz();
          refreshBadge();
        },
      });
    };
  });
  list.querySelectorAll("[data-flag]").forEach((btn) => {
    btn.onclick = () => {
      const card = btn.closest(".wall-card.active");
      const id = card?.dataset.wid;
      const wall = b.measure.walls.find((x) => x.id === id);
      if (!wall) return;
      if (!wall.flags) wall.flags = {};
      wall.flags[btn.dataset.flag] = !wall.flags[btn.dataset.flag];
      save();
      paintWallsList();
      refreshBadge();
    };
  });
  list.querySelectorAll("[data-wall-collapse]").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      collapseActiveWall();
    };
  });
  list.querySelectorAll(".wall-card.active [data-wf]").forEach((inp) => {
    const card = inp.closest(".wall-card.active");
    const id = card?.dataset.wid;
    const ev = inp.type === "checkbox" || inp.tagName === "SELECT" ? "change" : "input";
    inp.addEventListener(ev, () => {
      const wall = b.measure.walls.find((x) => x.id === id);
      if (!wall) return;
      const key = inp.dataset.wf;
      if (inp.type === "checkbox") wall[key] = inp.checked;
      else wall[key] = inp.value;
      if (key === "endsOn" && inp.checked && !wall.endsDepth) wall.endsDepth = "0.2";
      syncAreasFromLists(b);
      save();
      if (key === "endsOn") {
        paintWallsList();
        return;
      }
      const sumEl = card.querySelector("[data-ends-sum]");
      if (sumEl) {
        const a = wallEndsAreaOf(wall);
        sumEl.textContent = a ? a.toFixed(2) : "—";
      }
      updateWallsSum();
      refreshBadge();
    });
  });
  list.querySelectorAll("[data-wall-add-op]").forEach((btn) => {
    btn.onclick = () => {
      const card = btn.closest(".wall-card.active");
      const wallId = card?.dataset.wid || b.activeWallId;
      b.measure.openings.push({
        id: uid(),
        label: btn.dataset.wallAddOp || "Окно",
        width: "",
        height: "",
        zone: b.zones?.facade ? "facade" : "interior",
        wallId: wallId || "",
        needsWarm: false,
        note: "",
      });
      syncAreasFromLists(b);
      save();
      paintWallsList();
      refreshBadge();
    };
  });
  list.querySelectorAll("[data-wall-op-del]").forEach((btn) => {
    btn.onclick = () => {
      b.measure.openings = (b.measure.openings || []).filter((o) => o.id !== btn.dataset.wallOpDel);
      syncAreasFromLists(b);
      save();
      paintWallsList();
      refreshBadge();
    };
  });
  list.querySelectorAll(".wall-op-row [data-of]").forEach((inp) => {
    inp.addEventListener("input", () => {
      const row = inp.closest(".wall-op-row");
      const op = (b.measure.openings || []).find((o) => o.id === row?.dataset.oid);
      if (!op) return;
      op[inp.dataset.of] = inp.value;
      syncAreasFromLists(b);
      save();
      const area = Math.round(num(op.width) * num(op.height) * 100) / 100;
      const areaEl = row.querySelector(".wall-op-area");
      if (areaEl) areaEl.textContent = area ? area.toFixed(1) : "—";
      updateWallsSum();
      refreshBadge();
    });
  });
  list.querySelectorAll("[data-wall-att-inc], [data-wall-att-dec], [data-wall-att]").forEach((el) => {
    const apply = () => {
      const card = el.closest(".wall-card.active");
      const wall = b.measure.walls.find((x) => x.id === card?.dataset.wid);
      if (!wall) return;
      if (!wall.attention) wall.attention = {};
      if (el.dataset.wallAttInc) {
        wall.attention[el.dataset.wallAttInc] = num(wall.attention[el.dataset.wallAttInc]) + 1;
      } else if (el.dataset.wallAttDec) {
        wall.attention[el.dataset.wallAttDec] = Math.max(0, num(wall.attention[el.dataset.wallAttDec]) - 1);
      } else if (el.dataset.wallAtt) {
        wall.attention[el.dataset.wallAtt] = num(el.value);
      }
      syncWallAttentionToSurvey(b);
      save();
      if (el.dataset.wallAttInc || el.dataset.wallAttDec) paintWallsList();
    };
    if (el.tagName === "BUTTON") el.onclick = apply;
    else el.onchange = apply;
  });
  list.querySelectorAll("[data-wall-photo]").forEach((inp) => {
    inp.onchange = async () => {
      const file = inp.files?.[0];
      if (!file) return;
      const wall = b.measure.walls.find((x) => x.id === inp.dataset.wallPhoto);
      if (!wall) return;
      try {
        const photo = await compressImageFile(file);
        if (!wall.photos) wall.photos = [];
        wall.photos.push(photo);
        save();
        paintWallsList();
        toast("Фото стороны");
      } catch {
        toast("Не удалось загрузить фото");
      }
      inp.value = "";
    };
  });
  list.querySelectorAll("[data-wall-ph-del]").forEach((btn) => {
    btn.onclick = async () => {
      const wall = b.measure.walls.find((x) => x.id === btn.dataset.wallPhDel);
      if (!wall) return;
      const photo = (wall.photos || []).find((p) => p.id === btn.dataset.pid);
      if (!photo) return;
      await softDelete({
        what: `фото стороны «${wall.label || ""}»`,
        type: "wall_photo",
        payload: cloneDeep(photo),
        meta: { surveyId: survey.id, buildingId: b.id, wallId: wall.id },
        toastUndo,
        applyRemove: () => {
          wall.photos = (wall.photos || []).filter((p) => p.id !== photo.id);
          save();
          paintWallsList();
        },
        applyRestore: (payload) => {
          const w = b.measure.walls.find((x) => x.id === wall.id);
          if (!w) return;
          if (!w.photos) w.photos = [];
          if (!w.photos.some((p) => p.id === payload.id)) w.photos.push(payload);
          save();
          paintWallsList();
        },
      });
    };
  });
  updateWallsSum();
  bindKeypad(list);
}

function sideHint(i, kind) {
  if (kind === "fence") return "Пролёт: длина × высота щита";
  const hints = [
    "Главный фасад · к входу / дороге",
    "Правый · стоя лицом к входу",
    "Задний · часто с фронтоном",
    "Левый · замыкаете круг",
    "Доп. плоскость · эркер, пристрой, мансарда",
  ];
  return hints[Math.min(i, hints.length - 1)];
}

function updateWallsSum() {
  const el = $("#walls-sum");
  if (!el) return;
  const b = active();
  syncAreasFromLists(b);
  const area = num(b.measure.wallsArea);
  el.textContent = area.toFixed(1);
  const need = $("#walls-need-measure");
  if (need) need.hidden = area > 0;
  if (area > 0) clearNavHint();
}

/* ——— 3. Проёмы ——— */
function renderOpenings(root) {
  const b = active();
  if (!b.measure.openings) b.measure.openings = [];
  root.innerHTML = `
    <h2 class="section-title">Проёмы</h2>
    <p class="section-sub">Вычитаем из стен. Гараж — не забыть ворота.</p>
    ${tipBlock("openings")}
    <div id="openings-list" class="walls-list"></div>
    <div class="grid two" style="margin-top:8px">
      <button type="button" class="btn" id="btn-add-win">+ Окно</button>
      <button type="button" class="btn" id="btn-add-door">+ Дверь / ворота</button>
    </div>
    <h3 class="subhead">Торцы</h3>
    <p class="hint">Лучше заполнять на каждой стороне (шаг «Стены») — здесь сумма. Можно поправить вручную, если сторон ещё нет.</p>
    <div class="grid two">
      <div class="field">
        <label>Sтор, м²</label>
        <input data-path="building.measure.endsArea" value="${esc(b.measure.endsArea)}" inputmode="decimal">
        <span class="field-tip">Σ по сторонам или вручную</span>
      </div>
      <div class="field">
        <label>Lтор, пог.м</label>
        <input data-path="building.measure.endsLength" value="${esc(b.measure.endsLength)}" inputmode="decimal">
      </div>
    </div>
    <div class="callout ok">Проёмы: <b id="op-sum">0</b> м²</div>
    ${b.zones?.facade ? formulaHtml(b, "facade") : ""}
  `;
  bindFields(root);
  paintOpenings();
  $("#btn-add-win", root).onclick = () => addOpening("Окно");
  $("#btn-add-door", root).onclick = () => addOpening(b.kind === "garage" ? "Ворота" : "Дверь");
}

function addOpening(label) {
  const b = active();
  b.measure.openings.push({
    id: uid(),
    label,
    width: "",
    height: "",
    zone: b.zones?.facade ? "facade" : "interior",
    wallId: b.activeWallId || "",
    needsWarm: false,
    note: "",
  });
  save();
  paintOpenings();
}

function paintOpenings() {
  const list = $("#openings-list");
  if (!list) return;
  const b = active();
  const ops = b.measure.openings;
  const zoneOpts = WORK_ZONES.filter((z) => b.zones?.[z.id]);

  if (!ops.length) {
    list.innerHTML = `<div class="empty soft">Добавьте окна/двери или пропустите.</div>`;
  } else {
    list.innerHTML = ops
      .map((o) => {
        const area = Math.round(num(o.width) * num(o.height) * 100) / 100;
        return `
        <article class="wall-card" data-oid="${o.id}">
          <div class="wall-card-head">
            <input class="wall-label" data-f="label" value="${esc(o.label)}">
            <button type="button" class="btn ghost" data-odel="${o.id}">✕</button>
          </div>
          <div class="wall-meta">
            <select data-f="zone">
              ${(zoneOpts.length ? zoneOpts : WORK_ZONES)
                .map(
                  (z) =>
                    `<option value="${z.id}" ${(o.zone || "facade") === z.id ? "selected" : ""}>${z.title}</option>`
                )
                .join("")}
            </select>
            <select data-f="wallId">
              <option value="">Сторона — не указана</option>
              ${(b.measure.walls || [])
                .map(
                  (w) =>
                    `<option value="${w.id}" ${o.wallId === w.id ? "selected" : ""}>${escapeHtml(w.label || "Сторона")}</option>`
                )
                .join("")}
            </select>
          </div>
          <div class="wall-card-grid">
            <div class="field"><label>Ширина, м</label><input data-f="width" value="${esc(o.width)}" inputmode="decimal"></div>
            <div class="field"><label>Высота, м</label><input data-f="height" value="${esc(o.height)}" inputmode="decimal"></div>
            <div class="wall-area"><span>Вычесть</span><b>${area || "—"} м²</b></div>
          </div>
          <label class="check-inline">
            <input type="checkbox" data-f="needsWarm" ${o.needsWarm ? "checked" : ""}>
            Тёплый шов у этого проёма
          </label>
          <div class="field" style="margin-top:8px">
            <label>Комментарий</label>
            <input data-f="note" value="${esc(o.note)}" placeholder="напр. панорамное, замена...">
          </div>
          <details class="obsada-box">
            <summary>Обсада / наличник</summary>
            <label class="check-inline">
              <input type="checkbox" data-f="obsadaProtrudes" ${o.obsadaProtrudes ? "checked" : ""}>
              Выступает за стены
            </label>
            <div class="grid two" style="margin-top:8px">
              <div class="field"><label>Ширина бок</label><input data-f="obsadaSide" value="${esc(o.obsadaSide)}" inputmode="decimal" placeholder="мм/м"></div>
              <div class="field"><label>Верх</label><input data-f="obsadaTop" value="${esc(o.obsadaTop)}" inputmode="decimal"></div>
              <div class="field"><label>Низ</label><input data-f="obsadaBottom" value="${esc(o.obsadaBottom)}" inputmode="decimal"></div>
            </div>
          </details>
        </article>`;
      })
      .join("");
  }

  list.querySelectorAll(".wall-card").forEach((card) => {
    const id = card.dataset.oid;
    card.querySelectorAll("[data-f]").forEach((inp) => {
      const ev = inp.type === "checkbox" || inp.tagName === "SELECT" ? "change" : "input";
      inp.addEventListener(ev, () => {
        const o = b.measure.openings.find((x) => x.id === id);
        if (!o) return;
        o[inp.dataset.f] = inp.type === "checkbox" ? inp.checked : inp.value;
        syncAreasFromLists(b);
        if (inp.dataset.f === "needsWarm") recountWarmFromOpenings(b);
        save();
        if (["width", "height", "zone", "label", "wallId", "needsWarm"].includes(inp.dataset.f)) {
          paintOpenings();
        }
        refreshBadge();
      });
    });
  });
  list.querySelectorAll("[data-odel]").forEach((btn) => {
    btn.onclick = async () => {
      const opening = b.measure.openings.find((o) => o.id === btn.dataset.odel);
      if (!opening) return;
      const snap = cloneDeep(opening);
      const idx = b.measure.openings.findIndex((o) => o.id === opening.id);
      await softDelete({
        what: `проём «${opening.label || "окно/дверь"}»`,
        type: "opening",
        payload: snap,
        meta: { surveyId: survey.id, buildingId: b.id, index: idx },
        toastUndo,
        applyRemove: () => {
          b.measure.openings = b.measure.openings.filter((o) => o.id !== opening.id);
          syncAreasFromLists(b);
          save();
          paintOpenings();
          refreshBadge();
        },
        applyRestore: (payload, meta) => {
          if (!b.measure.openings.some((o) => o.id === payload.id)) {
            const at = Math.min(meta?.index ?? b.measure.openings.length, b.measure.openings.length);
            b.measure.openings.splice(at, 0, payload);
          }
          syncAreasFromLists(b);
          save();
          paintOpenings();
          refreshBadge();
        },
      });
    };
  });
  const sumEl = $("#op-sum");
  if (sumEl) {
    syncAreasFromLists(b);
    sumEl.textContent = num(b.measure.openingsArea).toFixed(2);
  }
}


function recountWarmFromOpenings(b) {
  const n = (b.measure.openings || []).filter((o) => o.needsWarm).length;
  // only auto-fill if empty or previously auto
  if (!b.measure.warmWindows || b.measure._warmFromOpenings) {
    b.measure.warmWindows = n ? String(n * 4) : ""; // ~4 пог.м на проём — оценка
    b.measure._warmFromOpenings = true;
    syncWarmTotal(b.measure);
  }
}

/* ——— 4. Ещё ——— */
function renderMore(root) {
  const b = active();
  const m = b.measure;
  const el = (title, hint, fields, open = false) => `
    <details class="el-card" ${open ? "open" : ""}>
      <summary>
        <span><strong>${title}</strong>${hint ? `<em>${hint}</em>` : ""}</span>
      </summary>
      <div class="el-card-body grid two">${fields}</div>
    </details>`;
  const field = (label, path, mode = "decimal") =>
    `<div class="field"><label>${label}</label><input data-path="${path}" value="${esc(m[path.split(".").pop()] ?? "")}" inputmode="${mode}"></div>`;

  const opCount = (m.openings || []).length;
  const opArea = num(m.openingsArea);
  const endsA = num(m.endsArea);
  root.innerHTML = `
    <h2 class="section-title">Элементы объекта</h2>
    <p class="section-sub">Стены, проёмы и торцы — на шаге «Замер». Здесь подшива, шов и остальные объёмы.</p>
    ${tipBlock("more")}
    <div class="callout compact">
      С замера: проёмы <b>${opCount}</b> шт${opArea ? ` · ${opArea.toFixed(1)} м²` : ""}
      ${endsA ? ` · торцы ${endsA.toFixed(2)} м²` : ""}
      ${b.zones?.facade ? "" : ""}
    </div>
    ${
      b.zones?.facade
        ? `
    <p class="crm-chip-label">Снаружи (фасад)</p>
    ${el("Торцы (правка суммы)", endsA ? `${endsA} м²` : "со сторон", `
      ${field("Sтор, м²", "building.measure.endsArea")}
      ${field("Lтор, пог.м", "building.measure.endsLength")}
    `)}
    ${el("Подшива", m.soffitArea ? `${m.soffitArea} м²` : "", field("Подшива, м²", "building.measure.soffitArea"))}
    ${el("Лобовая доска", m.fasciaArea ? `${m.fasciaArea} м²` : "", field("Лобовая, м²", "building.measure.fasciaArea"))}
    ${el("Свесы / крыльцо / лестница", "", `
      ${field("Свесы, м²", "building.measure.overhangArea")}
      ${field("Крыльцо / вход, м²", "building.measure.porchArea")}
      ${field("Лестница, м²", "building.measure.stairsArea")}
    `)}
    ${el("Наличники и доборы", "", `
      ${field("Наличники, пог.м", "building.measure.trimLength")}
      ${field("Доборы, пог.м", "building.measure.doborLength")}
      ${field("Раскладка / уголок, пог.м", "building.measure.layoutLength")}
    `)}
    ${el("Водосток / отлив / ограждения", "", `
      ${field("Водосток, пог.м", "building.measure.gutterLength")}
      ${field("Отлив, пог.м", "building.measure.sillLength")}
      ${field("Ограждения, м²", "building.measure.railingsArea")}
      ${field("Балки / элементы, пог.м", "building.measure.beamsLength")}
      ${
        b.kind === "fence"
          ? field("Столбы забора, шт", "building.measure.fencePosts", "numeric")
          : ""
      }
    `)}
    ${el("Тёплый шов", m.warmSeamTotal ? `итого ${m.warmSeamTotal}` : "", `
      ${field("Горизонтальный", "building.measure.warmHorizontal")}
      ${field("Змейка", "building.measure.warmSnake")}
      ${field("Трещины", "building.measure.warmCracks")}
      ${field("Окна", "building.measure.warmWindows")}
      ${field("Минус", "building.measure.warmMinus")}
      <div class="field"><label>Итого шов</label><input data-path="building.measure.warmSeamTotal" value="${esc(m.warmSeamTotal)}" readonly></div>
      <div class="field">
        <label>Конопатка</label>
        <select data-path="building.measure.caulk">
          <option value="unknown" ${m.caulk === "unknown" ? "selected" : ""}>Не ясно</option>
          <option value="yes" ${m.caulk === "yes" ? "selected" : ""}>Есть</option>
          <option value="no" ${m.caulk === "no" ? "selected" : ""}>Нет</option>
        </select>
      </div>
      <div class="field">
        <label>Старый герметик</label>
        <select data-path="building.measure.oldSealant">
          <option value="unknown" ${m.oldSealant === "unknown" ? "selected" : ""}>Не ясно</option>
          <option value="yes" ${m.oldSealant === "yes" ? "selected" : ""}>Есть</option>
          <option value="no" ${m.oldSealant === "no" ? "selected" : ""}>Нет</option>
        </select>
      </div>
    `)}`
        : `<div class="callout">Снаружи не отмечено — включите «Снаружи (фасад)» на шаге «Строение».</div>`
    }

    ${
      b.zones?.interior || b.kind === "terrace"
        ? `
    <p class="crm-chip-label" style="margin-top:16px">Внутри / терраса</p>
    ${el("Потолки и полы", "", `
      ${field("Потолки, м²", "building.measure.ceilingArea")}
      ${field("Полы, м²", "building.measure.floorArea")}
    `, true)}
    ${el("Терраса / вход", "", `
      ${field("Крыльцо / настил, м²", "building.measure.porchArea")}
      ${field("Лестница, м²", "building.measure.stairsArea")}
      ${field("Ограждения / перила, м²", "building.measure.railingsArea")}
    `)}`
        : `<div class="callout" style="margin-top:12px">Интерьер не отмечен — включите «Внутри (интерьер)» на шаге «Строение», если красим внутри.</div>`
    }
  `;

  bindFields(root);
  // warm seam auto total if helpers exist
  root.querySelectorAll("[data-path^='building.measure.warm']").forEach((inp) => {
    inp.addEventListener("change", () => {
      try {
        if (typeof syncWarmTotal === "function") syncWarmTotal(active().measure);
      } catch (_) {}
      save();
    });
  });
}

/* ——— 5. Технология ——— */
function renderTech(root) {
  const b = active();
  syncAreasFromLists(b);
  const facadeArea = b.zones?.facade ? calcWallArea(b.measure, "facade").total : 0;
  const interiorArea = b.zones?.interior ? calcWallArea(b.measure, "interior").total : 0;
  const rec = recommendTechs(b.houseType, b.condition, b.material);
  const paintsF = listPaintOptions(catalog, "facade");
  const paintsI = listPaintOptions(catalog, "interior");

  const fold = (title, hint, body, open = false) => `
    <details class="el-card" ${open ? "open" : ""}>
      <summary><span><strong>${title}</strong>${hint ? `<em>${hint}</em>` : ""}</span></summary>
      <div class="el-card-body">${body}</div>
    </details>`;

  root.innerHTML = `
    <h2 class="section-title calc-hero">Конструктор · ${escapeHtml(b.name)}</h2>
    <p class="section-sub">
      ${b.zones?.facade ? `Стены снаружи <b>${facadeArea.toFixed(1)} м²</b>` : "Снаружи выкл."}
      ${b.zones?.interior ? ` · внутри <b>${interiorArea.toFixed(1)} м²</b>` : ""}
      · подшива/лобовая/столбы — шаг «Допы» (как в смете).
    </p>
    ${tipBlock("tech")}

    ${fold(
      "Превью и цвет",
      b.previewColor ? "выбран" : "нажмите кружок",
      `${vizCard(b)}
      <p class="hint">Кружки меняют цвет на 3D. Текст RAL — ниже в «Состояние».</p>`,
      true
    )}

    ${fold(
      "Состояние поверхности",
      CONDITIONS.find((c) => c.id === b.condition)?.title || "",
      `
      <div class="choice-grid">
        ${CONDITIONS.map((c) => {
          const desc = c.byType[b.houseType] || "";
          return `
          <button type="button" class="choice ${b.condition === c.id ? "selected" : ""}" data-cond="${c.id}">
            <strong>${c.title}</strong><span>${desc}</span>
          </button>`;
        }).join("")}
      </div>
      <div class="grid two" style="margin-top:12px">
        <div class="field">
          <label>Влажность, %</label>
          <input data-path="building.humidity" value="${esc(b.humidity)}" inputmode="decimal">
        </div>
        <div class="field">
          <label>Цвет (текст / RAL)</label>
          <input data-path="building.colors" value="${esc(b.colors)}" placeholder="как сейчас / темнее / RAL">
        </div>
        <div class="field">
          <label>Сложность снятия покрытия</label>
          <select data-path="building.removalDifficulty">
            <option value="easy" ${b.removalDifficulty === "easy" ? "selected" : ""}>Лёгкая</option>
            <option value="normal" ${b.removalDifficulty === "normal" ? "selected" : ""}>Обычная</option>
            <option value="hard" ${b.removalDifficulty === "hard" ? "selected" : ""}>Тяжёлая</option>
            <option value="full_strip" ${b.removalDifficulty === "full_strip" ? "selected" : ""}>Полное снятие</option>
          </select>
        </div>
        <div class="field">
          <label>Старое покрытие — заметка</label>
          <input data-path="building.oldCoatingNote" value="${esc(b.oldCoatingNote)}" placeholder="отслоение, слои, тест скотчем">
        </div>
      </div>`
    )}

    ${
      b.zones?.facade
        ? fold(
            "Стены снаружи · технология и ЛКМ",
            `${facadeArea.toFixed(0)} м²`,
            `
      <div class="choice-grid">
        ${TECHNOLOGIES.map((t) => {
          const allowed = rec.some((r) => r.id === t.id);
          const note = rec.find((r) => r.id === t.id)?.note || "Нельзя";
          return `
          <button type="button" class="choice ${b.tech.techId === t.id ? "selected" : ""} ${allowed ? "" : "bad"}"
            data-tech="${t.id}" ${allowed ? "" : "disabled"}>
            <strong>${t.title}${t.isBase ? " ★" : ""}</strong>
            <span>${t.desc}</span>
            <span class="badge ${allowed ? "" : "danger"}">${allowed ? note : "Запрещено"}</span>
          </button>`;
        }).join("")}
      </div>
      <label class="hint" style="display:block;margin:12px 0 8px">ЛКМ × ${facadeArea.toFixed(0)} м²</label>
      <div class="paint-grid">
        ${paintsF
          .map((p) => {
            const item = p.items.find((i) => i.tech === b.tech.techId);
            const sum = item && facadeArea ? money(item.price * facadeArea) : "—";
            const ladder = (p.pricesByTech || p.items.map((i) => i.price))
              .map((pr, idx) => `<span class="${b.tech.techId === idx + 1 ? "on" : ""}">${idx + 1}: ${money(pr)}</span>`)
              .join("");
            return `
            <button type="button" class="paint-card ${b.tech.paintId === p.id ? "selected" : ""}" data-paint="${esc(p.id)}">
              <div class="paint-card-top">
                <span class="paint-brand">${escapeHtml(p.brand)}</span>
                <span class="paint-coat">${p.opacity === "opaque" ? "Укрывной" : "Полупрозрачный"}</span>
              </div>
              <strong class="paint-name">${escapeHtml(shortName(p.name))}</strong>
              <span class="paint-type">${escapeHtml(p.type || "")}${p.country ? ` · ${escapeHtml(p.country)}` : ""}</span>
              <span class="paint-fan">Веер: ${escapeHtml(p.fan || "—")}</span>
              <span class="paint-warranty">Гарантия техн. 4–5: <b>${p.warrantyYears45 || item?.guarantee || "—"} лет</b>${p.antisepticRequired ? " · с антисептиком" : ""}</span>
              <div class="paint-ladder">${ladder}</div>
              <span class="paint-total">${item ? `${money(item.price)}/м² → <b>${sum}</b>` : "нет цены"}</span>
            </button>`;
          })
          .join("")}
      </div>
      <div class="callout">${SEMI_LADDER.map((x) => x.tip).join(" → ")}</div>
      ${techCompareHtml(b, catalog)}`,
            true
          )
        : ""
    }

    ${
      b.zones?.interior
        ? fold(
            "Стены внутри · ЛКМ",
            `${interiorArea.toFixed(0)} м²`,
            `
      <div class="field" style="max-width:280px">
        <label>Технология интерьера</label>
        <select data-path="building.tech.techIdInterior">
          ${TECHNOLOGIES.map(
            (t) =>
              `<option value="${t.id}" ${Number(b.tech.techIdInterior) === t.id ? "selected" : ""}>${t.short}</option>`
          ).join("")}
        </select>
      </div>
      <div class="paint-grid">
        ${paintsI
          .map((p) => {
            const tid = Number(b.tech.techIdInterior) || b.tech.techId;
            const item = p.items.find((i) => i.tech === tid);
            const sum = item && interiorArea ? money(item.price * interiorArea) : "—";
            return `
            <button type="button" class="paint-card ${b.tech.paintIdInterior === p.id ? "selected" : ""}" data-paint-int="${esc(p.id)}">
              <div class="paint-card-top">
                <span class="paint-brand">${escapeHtml(p.brand)}</span>
                <span class="paint-coat">Интерьер</span>
              </div>
              <strong class="paint-name">${escapeHtml(shortName(p.name))}</strong>
              <span class="paint-fan">Веер: ${escapeHtml(p.fan || "—")}</span>
              <span class="paint-total">${item ? `${money(item.price)}/м² → <b>${sum}</b>` : "нет цены"}</span>
            </button>`;
          })
          .join("")}
      </div>`
          )
        : ""
    }

    <div class="compat-box">
      <label class="choice" style="display:flex;gap:10px;align-items:flex-start;margin:0">
        <input type="checkbox" data-path="building.tech.compatibilityTest" ${b.tech.compatibilityTest ? "checked" : ""} style="width:auto;margin-top:3px">
        <span><strong>Тест на совместимость сделан</strong></span>
      </label>
      <details class="compat-how" open>
        <summary>Что это и как проверить</summary>
        <p>На старое покрытие нельзя класть новый состав «вслепую». Тест: на незаметном участке нанести новый ЛКМ (или скотч-тест адгезии) и через время проверить — нет ли отслоения, сморщивания, непрокраса.</p>
        <p>Если тест не пройден — только полное снятие старого слоя или отказ от состава. Отметьте галочку, когда проверка на объекте сделана.</p>
      </details>
      <details><summary class="hint">Что нельзя предлагать</summary>
        <ul>${FORBIDDEN.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>
      </details>
    </div>
  `;

  bindFields(root);
  bindVizColors(root);
  // techIdInterior select stores string — coerce
  root.querySelector("[data-path='building.tech.techIdInterior']")?.addEventListener("change", (e) => {
    active().tech.techIdInterior = Number(e.target.value);
    save();
    render();
  });

  root.querySelectorAll("[data-cond]").forEach((btn) => {
    btn.onclick = () => {
      active().condition = btn.dataset.cond;
      active().tech.techId = defaultTechId(active().houseType, active().condition, active().material);
      save();
      render();
    };
  });
  root.querySelectorAll("[data-tech]").forEach((btn) => {
    btn.onclick = () => {
      active().tech.techId = Number(btn.dataset.tech);
      save();
      render();
    };
  });
  root.querySelectorAll("[data-paint]").forEach((btn) => {
    btn.onclick = () => {
      active().tech.paintId = btn.dataset.paint;
      save();
      render();
    };
  });
  root.querySelectorAll("[data-paint-int]").forEach((btn) => {
    btn.onclick = () => {
      active().tech.paintIdInterior = btn.dataset.paintInt;
      save();
      render();
    };
  });
}

function shortName(name) {
  return name.replace(/\s*-\s*(фасад|интерьер).*$/i, "").trim();
}

/* ——— 6. Объект ——— */
function renderSite(root) {
  const s = survey.site;
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
  const c = survey.contract;
  root.innerHTML = `
    <h2 class="section-title">Участок и быт бригады</h2>
    <p class="section-sub">Доступ, электричество, быт — влияет на смету и выезд бригады.</p>
    ${tipBlock("site")}

    <h3 class="subhead">Доступ и высота</h3>
    <div class="choice-grid compact">
      ${SCAFFOLD_OPTIONS.map(
        (o) => `
        <button type="button" class="choice ${(s.scaffold || "none") === o.id ? "selected" : ""}" data-scaffold="${o.id}">
          <strong>${o.title}</strong>
        </button>`
      ).join("")}
    </div>
    <div class="grid two" style="margin-top:10px">
      <div class="field"><label>Макс. высота работ, м</label><input data-path="site.maxHeight" value="${esc(s.maxHeight)}" inputmode="decimal" placeholder="3 / 6 / 9…"></div>
      <div class="field"><label>Подъезд / доступ</label><input data-path="site.accessNote" value="${esc(s.accessNote)}" placeholder="узкие ворота, грязь, склон…"></div>
    </div>

    <h3 class="subhead">Электричество и люди</h3>
    <div class="grid two">
      <div class="field"><label>Когда начать</label><input data-path="site.startWhen" value="${esc(s.startWhen)}"></div>
      <div class="field"><label>Часы работы</label><input data-path="site.workHours" value="${esc(s.workHours)}"></div>
      <div class="field"><label>кВт</label><input data-path="site.powerKw" value="${esc(s.powerKw)}"></div>
      <div class="field"><label>Откуда электричество</label><input data-path="site.powerFrom" value="${esc(s.powerFrom)}"></div>
      <div class="field">
        <label>Электричества хватит?</label>
        <select data-path="site.powerOk">
          <option value="yes" ${s.powerOk === "yes" ? "selected" : ""}>Да</option>
          <option value="weak" ${s.powerOk === "weak" ? "selected" : ""}>Слабо</option>
          <option value="no" ${s.powerOk === "no" ? "selected" : ""}>Нет</option>
        </select>
      </div>
      <div class="field">
        <label>Генератор</label>
        <select data-path="site.generator">
          <option value="" ${!s.generator ? "selected" : ""}>Не нужен</option>
          <option value="1" ${s.generator ? "selected" : ""}>Нужен</option>
        </select>
      </div>
      <div class="field">
        <label>На объекте во время работ</label>
        <select data-path="site.occupancy">
          <option value="empty" ${s.occupancy === "empty" ? "selected" : ""}>Пустой</option>
          <option value="live" ${s.occupancy === "live" ? "selected" : ""}>Живут</option>
          <option value="visit" ${s.occupancy === "visit" ? "selected" : ""}>Наезжают</option>
        </select>
      </div>
      <div class="field">
        <label>Мебель</label>
        <select data-path="site.clientFurniture">
          <option value="yes" ${s.clientFurniture === "yes" ? "selected" : ""}>Клиент отодвинет</option>
          <option value="crew" ${s.clientFurniture === "crew" ? "selected" : ""}>Бригада</option>
          <option value="leave" ${s.clientFurniture === "leave" ? "selected" : ""}>Оставляем / обходим</option>
        </select>
      </div>
      <div class="field">
        <label>Жильё</label>
        <select data-path="site.housing">
          <option value="none" ${s.housing === "none" ? "selected" : ""}>Есть у заказчика</option>
          <option value="yes" ${s.housing === "yes" ? "selected" : ""}>Есть</option>
          <option value="need" ${s.housing === "need" ? "selected" : ""}>Нужна бытовка</option>
        </select>
      </div>
      <div class="field">
        <label>Туалет</label>
        <select data-path="site.toilet">
          <option value="none" ${s.toilet === "none" ? "selected" : ""}>Нет</option>
          <option value="yes" ${s.toilet === "yes" ? "selected" : ""}>Есть</option>
          <option value="need" ${s.toilet === "need" ? "selected" : ""}>Нужен биотуалет</option>
        </select>
      </div>
      <div class="field">
        <label>Душ</label>
        <select data-path="site.shower">
          <option value="none" ${s.shower === "none" ? "selected" : ""}>Нет</option>
          <option value="yes" ${s.shower === "yes" ? "selected" : ""}>Есть — фото</option>
          <option value="need" ${s.shower === "need" ? "selected" : ""}>Нужен</option>
        </select>
      </div>
      <div class="field">
        <label>Вода</label>
        <select data-path="site.water">
          <option value="none" ${s.water === "none" ? "selected" : ""}>Нет</option>
          <option value="drink" ${s.water === "drink" ? "selected" : ""}>Питьевая</option>
          <option value="tech" ${s.water === "tech" ? "selected" : ""}>Техническая</option>
          <option value="both" ${s.water === "both" ? "selected" : ""}>Оба</option>
        </select>
      </div>
      <div class="field"><label>Магазин</label><input data-path="site.shop" value="${esc(s.shop)}"></div>
    </div>

    <h3 class="subhead">Данные для договора</h3>
    <p class="hint">Как в конструкторе smeta-bestpaints — чтобы на объекте сразу закрыть бумагу.</p>
    <div class="grid two">
      <div class="field"><label>Название объекта / сметы</label><input data-path="contract.objectName" value="${esc(c.objectName)}" placeholder="Как в названии проекта"></div>
      <div class="field"><label>№ договора</label><input data-path="contract.number" value="${esc(c.number)}" placeholder="ДДММГГ-1"></div>
      <div class="field"><label>Дата договора</label><input data-path="contract.date" value="${esc(c.date)}" type="date"></div>
      <div class="field"><label>Срок, раб. дней</label><input data-path="contract.workDays" value="${esc(c.workDays)}" inputmode="numeric"></div>
      <div class="field"><label>Дата начала работ</label><input data-path="contract.startDate" value="${esc(c.startDate)}" type="date"></div>
      <div class="field"><label>Менеджер</label><input data-path="contract.managerName" value="${esc(c.managerName)}"></div>
      <div class="field"><label>Тел. менеджера</label><input data-path="contract.managerPhone" value="${esc(c.managerPhone)}" inputmode="tel"></div>
      <div class="field"><label>Тел. замерщика</label><input data-path="contract.surveyorPhone" value="${esc(c.surveyorPhone)}" inputmode="tel"></div>
      <div class="field"><label>Паспорт (серия №)</label><input data-path="contract.passport" value="${esc(c.passport)}"></div>
      <div class="field"><label>Кем и когда выдан</label><input data-path="contract.passportIssued" value="${esc(c.passportIssued)}"></div>
      <div class="field"><label>Код подразделения</label><input data-path="contract.passportCode" value="${esc(c.passportCode)}"></div>
      <div class="field"><label>Адрес регистрации</label><input data-path="contract.registration" value="${esc(c.registration)}"></div>
    </div>

    <h3 class="subhead">Что мешает на фасадах / внутри</h3>
    <div class="card flat">
      ${ATTENTION_ELEMENTS.map((el) => {
        const v = survey.attention[el.id] || 0;
        return `
        <div class="counter-row">
          <div><strong>${el.label}</strong><div class="hint">${el.unit}</div></div>
          <div class="counter">
            <button type="button" data-att-dec="${el.id}">−</button>
            <input data-att="${el.id}" value="${v}" inputmode="numeric">
            <button type="button" data-att-inc="${el.id}">+</button>
          </div>
        </div>`;
      }).join("")}
    </div>

    <button type="button" class="btn block" id="btn-att-to-extra" style="margin:10px 0">Счётчики → в доп.услуги сметы</button>

    <h3 class="subhead">Доп. услуги (кол-во)</h3>
    ${EXTRA_WORKS.map(
      (g) => `
      <details class="premium-details extras-group" ${g.group === "Прочее на объекте" ? "open" : ""}>
        <summary>${escapeHtml(g.group)}</summary>
        <div class="card flat" style="margin-top:8px">
          ${g.items
            .map((item) => {
              const q = (survey.extras?.qty || {})[item.id] || "";
              return `
              <div class="counter-row">
                <div><strong style="font-size:0.88rem">${escapeHtml(item.name)}</strong>
                <div class="hint">${money(item.price)} / ${item.unit}</div></div>
                <input style="width:72px" data-extra="${item.id}" value="${esc(q)}" inputmode="decimal" placeholder="0">
              </div>`;
            })
            .join("")}
        </div>
      </details>`
    ).join("")}
    <div class="field"><label>Заметки по объекту</label><textarea data-path="site.notes">${esc(s.notes)}</textarea></div>
  `;
  bindFields(root);
  root.querySelectorAll("[data-att-inc]").forEach((btn) => {
    btn.onclick = () => {
      survey.attention[btn.dataset.attInc] = num(survey.attention[btn.dataset.attInc]) + 1;
      save();
      render();
    };
  });
  root.querySelectorAll("[data-att-dec]").forEach((btn) => {
    btn.onclick = () => {
      survey.attention[btn.dataset.attDec] = Math.max(0, num(survey.attention[btn.dataset.attDec]) - 1);
      save();
      render();
    };
  });
  root.querySelectorAll("[data-att]").forEach((inp) => {
    inp.onchange = () => {
      survey.attention[inp.dataset.att] = num(inp.value);
      save();
    };
  });
  root.querySelectorAll("[data-extra]").forEach((inp) => {
    inp.onchange = () => {
      survey.extras.qty[inp.dataset.extra] = inp.value;
      save();
    };
  });
  root.querySelectorAll("[data-scaffold]").forEach((btn) => {
    btn.onclick = () => {
      survey.site.scaffold = btn.dataset.scaffold;
      save();
      render();
    };
  });
  $("#btn-att-to-extra", root)?.addEventListener("click", () => {
    let n = 0;
    for (const [att, extraId] of Object.entries(ATTENTION_TO_EXTRA)) {
      const v = num(survey.attention[att]);
      if (v > 0) {
        survey.extras.qty[extraId] = String(v);
        n++;
      }
    }
    save();
    toast(n ? `Перенесено позиций: ${n}` : "Счётчики пусты");
    render();
  });
}

function paintCustomLines(root) {
  const box = $("#custom-lines", root);
  if (!box) return;
  if (!survey.estimate.customLines) survey.estimate.customLines = [];
  const lines = survey.estimate.customLines;
  if (!lines.length) {
    box.innerHTML = `<div class="empty soft">Нет своих позиций.</div>`;
    return;
  }
  box.innerHTML = lines
    .map(
      (cl) => `
    <div class="custom-line" data-cid="${cl.id}">
      <input data-cf="name" value="${esc(cl.name)}" placeholder="Название">
      <input data-cf="qty" value="${esc(cl.qty)}" inputmode="decimal" placeholder="Кол-во">
      <input data-cf="unit" value="${esc(cl.unit || "шт")}" placeholder="Ед.">
      <input data-cf="price" value="${esc(cl.price)}" inputmode="decimal" placeholder="Цена">
      <button type="button" class="btn ghost" data-cdel="${cl.id}">✕</button>
    </div>`
    )
    .join("");
  box.querySelectorAll(".custom-line").forEach((row) => {
    const id = row.dataset.cid;
    row.querySelectorAll("[data-cf]").forEach((inp) => {
      inp.addEventListener("change", () => {
        const cl = survey.estimate.customLines.find((x) => x.id === id);
        if (!cl) return;
        cl[inp.dataset.cf] = inp.value;
        save();
        render();
      });
    });
  });
  box.querySelectorAll("[data-cdel]").forEach((btn) => {
    btn.onclick = async () => {
      const line = survey.estimate.customLines.find((x) => x.id === btn.dataset.cdel);
      if (!line) return;
      const snap = cloneDeep(line);
      const idx = survey.estimate.customLines.findIndex((x) => x.id === line.id);
      await softDelete({
        what: `позицию «${line.name || "своя строка"}»`,
        type: "custom_line",
        payload: snap,
        meta: { surveyId: survey.id, index: idx },
        toastUndo,
        applyRemove: () => {
          survey.estimate.customLines = survey.estimate.customLines.filter((x) => x.id !== line.id);
          save();
          render();
        },
        applyRestore: (payload, meta) => {
          if (!survey.estimate.customLines) survey.estimate.customLines = [];
          if (!survey.estimate.customLines.some((x) => x.id === payload.id)) {
            const at = Math.min(meta?.index ?? survey.estimate.customLines.length, survey.estimate.customLines.length);
            survey.estimate.customLines.splice(at, 0, payload);
          }
          save();
          render();
        },
      });
    };
  });
}

/* ——— 7. Смета ——— */
function renderEstimate(root) {
  if (!survey.extras) survey.extras = { qty: {} };
  if (!survey.extras.qty) survey.extras.qty = {};
  if (!survey.attention) survey.attention = {};
  if (survey.site?.housing === "need" && !survey.extras.qty.cabin_near) survey.extras.qty.cabin_near = 1;
  if (survey.site?.toilet === "need" && !survey.extras.qty.toilet_near) survey.extras.qty.toilet_near = 1;
  try {
    save();
  } catch {
    /* ignore */
  }

  const est = buildEstimate(survey, catalog);
  const a = est.areas;

  root.innerHTML = `
    <h2 class="section-title">Смета на объекте</h2>
    <p class="section-sub">Сводка по всем строениям · схема и PDF для заказчика.</p>
    ${tipBlock("estimate")}
    ${readinessHtml(survey)}
    ${survey.buildings.map((b) => (b.zones?.facade ? formulaHtml(b, "facade") : "")).join("")}
    ${survey.buildings.map((b) => (b.zones?.interior ? formulaHtml(b, "interior") : "")).join("")}

    <div class="viz-gallery">
      ${survey.buildings.map((b) => vizCard(b)).join("")}
    </div>

    <div class="callout">
      <b>${escapeHtml(survey.client.name || "Клиент")}</b> · ${escapeHtml(survey.client.address || "—")}<br>
      Строений: ${survey.buildings.length} ·
      фасад ${a.facade} м²
      ${a.interior ? ` · интерьер ${a.interior} м²` : ""}
      ${a.soffit ? ` · подшива ${a.soffit}` : ""}
      ${a.ceiling ? ` · потолки ${a.ceiling}` : ""}
      · ориентир ЛКМ ~${paintLiters(a.facade + a.interior)} л
    </div>

    <div class="field" style="max-width:200px">
      <label>Скидка, %</label>
      <input data-path="estimate.discountPct" value="${esc(survey.estimate.discountPct)}" inputmode="decimal">
    </div>

    <div style="overflow-x:auto">
      <table class="table">
        <thead><tr><th>Работа</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr></thead>
        <tbody>
          ${
            est.lines.length
              ? est.lines
                  .map(
                    (l) => `<tr>
              <td>${escapeHtml(l.name)}${l.guarantee ? `<div class="hint">гарантия ${l.guarantee} лет</div>` : ""}</td>
              <td>${l.qty} ${l.unit}</td>
              <td>${money(l.price)}</td>
              <td class="sum">${money(l.sum)}</td>
            </tr>`
                  )
                  .join("")
              : `<tr><td colspan="4">Нет строк — проверьте замер и выбор ЛКМ по строениям</td></tr>`
          }
        </tbody>
      </table>
    </div>

    <div class="totals">
      <div class="row"><span>Итого</span><span>${money(est.subtotal)}</span></div>
      <div class="row"><span>Скидка ${est.discountPct}%</span><span>− ${money(est.subtotal - est.afterDiscount)}</span></div>
      <div class="row"><span>НДС 5%</span><span>${money(est.vat)}</span></div>
      <div class="row total"><span>К оплате</span><span>${money(est.total)}</span></div>
    </div>

    <h3 class="subhead">Свои позиции</h3>
    <p class="hint">Разовое, чего нет в каталоге — сразу в смету.</p>
    <div id="custom-lines"></div>
    <button type="button" class="btn block" id="btn-add-custom" style="margin:8px 0 14px">+ Позиция</button>

    <h3 class="subhead">Этапы оплаты</h3>
    <div class="grid two">
      <div class="field"><label>Аванс, %</label><input data-path="estimate.payments.advance" value="${esc(survey.estimate.payments?.advance ?? 10)}" inputmode="decimal"></div>
      <div class="field"><label>2-й платёж, %</label><input data-path="estimate.payments.second" value="${esc(survey.estimate.payments?.second ?? 40)}" inputmode="decimal"></div>
      <div class="field"><label>3-й платёж, %</label><input data-path="estimate.payments.third" value="${esc(survey.estimate.payments?.third ?? 40)}" inputmode="decimal"></div>
      <div class="field"><label>Финальный, %</label><input data-path="estimate.payments.final" value="${esc(survey.estimate.payments?.final ?? 10)}" inputmode="decimal"></div>
    </div>
    <div class="callout ok">
      Аванс ${money((est.total * num(survey.estimate.payments?.advance, 10)) / 100)} ·
      2-й ${money((est.total * num(survey.estimate.payments?.second, 40)) / 100)} ·
      3-й ${money((est.total * num(survey.estimate.payments?.third, 40)) / 100)} ·
      финал ${money((est.total * num(survey.estimate.payments?.final, 10)) / 100)}
    </div>

    <div class="share-row no-print">
      <button class="btn primary" id="btn-pdf">PDF для клиента ★</button>
      <button class="btn" id="btn-tg">Telegram</button>
      <button class="btn" id="btn-wa">WhatsApp</button>
      <button class="btn" id="btn-copy">Копировать</button>
      <button class="btn ghost" id="btn-native">Поделиться…</button>
      <button class="btn" id="btn-export">JSON</button>
    </div>
    <p class="footer-note no-print">PDF → «Печать» → «Сохранить как PDF». Шаринг — текст сметы клиенту или в офис.</p>
  `;

  bindFields(root);
  bindVizColors(root);
  paintCustomLines(root);
  $("#btn-add-custom", root).onclick = () => {
    if (!survey.estimate.customLines) survey.estimate.customLines = [];
    survey.estimate.customLines.push({ id: uid(), name: "", qty: "1", unit: "шт", price: "" });
    save();
    paintCustomLines(root);
  };
  root.querySelector("[data-path='estimate.discountPct']")?.addEventListener("change", () => render());
  $("#btn-pdf", root).onclick = () => openClientReport(survey, catalog);
  $("#btn-tg", root).onclick = () => shareTelegram(survey, catalog);
  $("#btn-wa", root).onclick = () => shareWhatsApp(survey, catalog);
  $("#btn-copy", root).onclick = async () => {
    const r = await copyShareText(survey, catalog);
    toast(r.ok ? "Скопировано в буфер" : "Скопируйте вручную из окна");
    if (!r.ok) prompt("Скопируйте текст:", r.text);
  };
  $("#btn-native", root).onclick = async () => {
    const r = await nativeShare(survey, catalog);
    if (!r.ok) toast("Системный шаринг недоступен — используйте Telegram/WhatsApp");
  };
  $("#btn-export", root).onclick = () => store.exportJson(survey);
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function esc(str) {
  return escapeHtml(str).replace(/'/g, "&#39;");
}
function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

init();
