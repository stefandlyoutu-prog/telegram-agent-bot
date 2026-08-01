/** Кабинет клиента BestPaints — вход по телефону + правка сметы/конструктора. */

import {
  TECHNOLOGIES,
  HOUSE_TYPES,
  CONDITIONS,
  recommendTechs,
  defaultTechId,
} from "../data/tech-matrix.js";
import {
  money,
  buildEstimate,
  calcWallArea,
  migrateSurvey,
  syncAreasFromLists,
  listAllowedPaints,
} from "./calc.js";
import { pitchForPaint, pitchForTech } from "../data/pitch.js";
import { openClientReport } from "./report.js";

const app = document.getElementById("app");
let catalog = null;
let state = {
  token: "",
  phone: "",
  accessCode: "",
  bundle: null,
  survey: null,
  error: "",
  savedMsg: "",
  busy: false,
  tab: "tech",
};

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function magicTokenFromPath() {
  const m = location.pathname.match(/\/bestpaints\/c\/([^/]+)/);
  if (m) return decodeURIComponent(m[1]);
  return new URLSearchParams(location.search).get("token") || "";
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || res.statusText || "Ошибка";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

function activeBuilding(s) {
  const list = s.buildings || [];
  return list.find((b) => b.id === s.activeBuildingId) || list[0];
}

function withSnapshot(survey) {
  const s = migrateSurvey(JSON.parse(JSON.stringify(survey)));
  for (const b of s.buildings || []) syncAreasFromLists(b);
  const est = buildEstimate(s, catalog);
  s._estimateSnapshot = {
    subtotal: est.subtotal,
    discountPct: est.discountPct,
    total: est.total,
    vat: est.vat,
    areas: est.areas,
    area_m2: est.areas?.paintTotal,
  };
  return s;
}

function renderLogin() {
  app.innerHTML = `
  <div class="cab-shell cab-login">
    <div class="cab-hero">
      <div class="logo" style="color:#d4b56a;font-weight:700;letter-spacing:.04em">BESTPAINTS</div>
      <h1>Кабинет клиента</h1>
      <p>Войдите по телефону с замера — смотрите смету и выбирайте варианты ЛКМ и технологий.</p>
    </div>
    <div class="cab-card">
      ${state.error ? `<div class="cab-error">${esc(state.error)}</div>` : ""}
      <label class="field">Телефон
        <input id="cab-phone" type="tel" inputmode="tel" placeholder="+7…" value="${esc(state.phone)}" />
      </label>
      ${
        state.token
          ? `<p class="cab-muted">Вход по персональной ссылке — подтвердите телефон.</p>`
          : `<label class="field">Код доступа (из сообщения менеджера)
        <input id="cab-code" inputmode="numeric" placeholder="6 цифр" value="${esc(state.accessCode)}" />
      </label>`
      }
      <button class="btn primary block" id="cab-login" style="margin-top:12px" ${state.busy ? "disabled" : ""}>
        ${state.busy ? "Входим…" : "Войти в кабинет"}
      </button>
    </div>
  </div>`;
  app.querySelector("#cab-login").onclick = async () => {
    state.phone = app.querySelector("#cab-phone").value;
    state.accessCode = app.querySelector("#cab-code")?.value || "";
    state.busy = true;
    state.error = "";
    render();
    try {
      await api("/bestpaints/api/client/login", {
        method: "POST",
        body: JSON.stringify({
          phone: state.phone,
          token: state.token,
          access_code: state.accessCode,
        }),
      });
      await loadMe();
    } catch (e) {
      state.error = e.message || String(e);
    } finally {
      state.busy = false;
      render();
    }
  };
}

async function loadMe() {
  const bundle = await api("/bestpaints/api/client/me");
  state.bundle = bundle;
  state.survey = migrateSurvey(bundle.survey || {});
  if (!state.survey.buildings?.length) throw new Error("Смета ещё не загружена — попросите замерщика открыть кабинет");
}

function ensureValid(b) {
  const rec = recommendTechs(b.houseType, b.condition, b.material);
  if (!rec.some((t) => t.id === Number(b.tech?.techId))) {
    b.tech.techId = defaultTechId(b.houseType, b.condition, b.material);
  }
  const paints = listAllowedPaints(catalog, {
    houseType: b.houseType,
    condition: b.condition,
    techId: b.tech.techId,
    coatingWant: b.tech.coatingWant || "",
    materialId: b.material,
  });
  if (b.tech.paintId && !paints.some((p) => p.id === b.tech.paintId)) {
    b.tech.paintId = paints[0]?.id || "";
  }
}

function renderCabinet() {
  const s = state.survey;
  const b = activeBuilding(s);
  ensureValid(b);
  syncAreasFromLists(b);
  const est = buildEstimate(s, catalog);
  const facade = calcWallArea(b.measure, "facade").total;
  const tech = TECHNOLOGIES.find((t) => t.id === b.tech.techId);
  const paints = listAllowedPaints(catalog, {
    houseType: b.houseType,
    condition: b.condition,
    techId: b.tech.techId,
    coatingWant: b.tech.coatingWant || "",
    materialId: b.material,
  });
  const rec = recommendTechs(b.houseType, b.condition, b.material);
  const paintPitch = pitchForPaint(b.tech.paintId);
  const techPitch = pitchForTech(b.tech.techId);
  const obj = state.bundle.object || {};

  app.innerHTML = `
  <div class="cab-shell">
    <div class="cab-hero">
      <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start">
        <div>
          <div style="color:#d4b56a;font-weight:700">BESTPAINTS · ваш кабинет</div>
          <h1>${esc(obj.title || "Смета по объекту")}</h1>
          <p>${esc(obj.address || "")}<br/>${esc(state.bundle.cabinet?.client_name || "")} · ${esc(state.bundle.cabinet?.client_phone || "")}</p>
        </div>
        <button class="btn ghost" id="cab-logout" style="background:rgba(255,255,255,.1);color:#fff;border:1px solid rgba(255,255,255,.2)">Выйти</button>
      </div>
      <div class="cab-kpi">
        <div><span class="cab-muted">К покраске</span><b>${esc(String(est.areas.paintTotal))} м²</b></div>
        <div><span class="cab-muted">К оплате</span><b>${money(est.total)}</b></div>
      </div>
    </div>

    ${state.error ? `<div class="cab-error">${esc(state.error)}</div>` : ""}
    ${state.savedMsg ? `<div class="cab-ok">${esc(state.savedMsg)}</div>` : ""}

    <div class="cab-card">
      <h2>Почему это решение</h2>
      <p><strong>${esc(paintPitch.headline)}</strong> — ${esc(paintPitch.wow)}</p>
      <p class="cab-muted" style="margin-top:8px">${esc(techPitch.why)}</p>
    </div>

    <div class="cab-card">
      <div class="zp-role-tabs" style="margin-bottom:12px">
        ${[
          ["tech", "Технология"],
          ["paint", "ЛКМ"],
          ["state", "Состояние"],
          ["sum", "Смета"],
        ]
          .map(
            ([id, label]) =>
              `<button type="button" class="crm-role-chip ${state.tab === id ? "on" : ""}" data-tab="${id}">${label}</button>`
          )
          .join("")}
      </div>

      ${
        state.tab === "state"
          ? `
        <label class="field">Тип покрытия сейчас
          <select id="cab-htype">
            ${HOUSE_TYPES.map((t) => `<option value="${t.id}" ${b.houseType === t.id ? "selected" : ""}>${esc(t.title)}</option>`).join("")}
          </select>
        </label>
        <label class="field">Состояние
          <select id="cab-cond">
            ${CONDITIONS.map((c) => `<option value="${c.id}" ${b.condition === c.id ? "selected" : ""}>${esc(c.title)}</option>`).join("")}
          </select>
        </label>
        <label class="field">Желаемый цвет
          <input id="cab-colors" value="${esc(b.colors || "")}" placeholder="RAL / темнее / как сейчас" />
        </label>
        <label class="field">Скидка, %
          <input id="cab-disc" type="number" min="0" max="30" step="0.5" value="${esc(s.estimate?.discountPct ?? 0)}" />
        </label>`
          : ""
      }

      ${
        state.tab === "tech"
          ? `<p class="cab-muted">Доступны только технологии для вашего дома · фасад ${facade.toFixed(0)} м²</p>
        <div class="cab-choice">
          ${rec
            .map(
              (t) => `<button type="button" class="${b.tech.techId === t.id ? "selected" : ""}" data-tech="${t.id}">
            <strong>${esc(t.title)}${t.isBase ? " ★" : ""}</strong>
            <span>${esc(t.desc)}</span>
          </button>`
            )
            .join("")}
        </div>
        <p class="cab-muted" style="margin-top:10px">Сейчас: <b>${esc(tech?.title || "—")}</b></p>`
          : ""
      }

      ${
        state.tab === "paint"
          ? `<p class="cab-muted">Только допустимые ЛКМ · ${paints.length} вариантов</p>
        <div class="cab-choice">
          ${paints
            .map((p) => {
              const item = p.items.find((i) => i.tech === b.tech.techId);
              const sum = item ? money(item.price * facade) : "—";
              return `<button type="button" class="${b.tech.paintId === p.id ? "selected" : ""}" data-paint="${esc(p.id)}">
              <strong>${esc(p.brand)} · ${esc(p.name)}</strong>
              <span>${p.opacity === "opaque" ? "Укрывной" : "Полупрозрачный"} · ${item ? money(item.price) + "/м²" : ""} → <b>${sum}</b></span>
            </button>`;
            })
            .join("") || "<p class='cab-error'>Нет ЛКМ для этой технологии — смените технологию или состояние</p>"}
        </div>`
          : ""
      }

      ${
        state.tab === "sum"
          ? `<table class="table">
          <thead><tr><th>Работа</th><th>Сумма</th></tr></thead>
          <tbody>
            ${est.lines
              .map((l) => `<tr><td>${esc(l.name)}</td><td class="sum">${money(l.sum)}</td></tr>`)
              .join("")}
          </tbody>
        </table>
        <div class="totals" style="margin-top:10px">
          <div class="row"><span>Итого</span><span>${money(est.subtotal)}</span></div>
          <div class="row"><span>Скидка ${est.discountPct}%</span><span>− ${money(est.subtotal - est.afterDiscount)}</span></div>
          <div class="row"><span>НДС 5%</span><span>${money(est.vat)}</span></div>
          <div class="row total"><span>К оплате</span><span>${money(est.total)}</span></div>
        </div>`
          : ""
      }
    </div>
  </div>
  <div class="cab-sticky">
    <button class="btn primary" id="cab-save" ${state.busy ? "disabled" : ""}>Сохранить варианты</button>
    <button class="btn" id="cab-pdf">PDF-презентация</button>
  </div>`;

  app.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.onclick = () => {
      state.tab = btn.dataset.tab;
      render();
    };
  });
  app.querySelector("#cab-logout").onclick = async () => {
    await api("/bestpaints/api/client/logout", { method: "POST", body: "{}" });
    state.bundle = null;
    state.survey = null;
    render();
  };
  app.querySelectorAll("[data-tech]").forEach((btn) => {
    btn.onclick = () => {
      b.tech.techId = Number(btn.dataset.tech);
      ensureValid(b);
      state.savedMsg = "";
      render();
    };
  });
  app.querySelectorAll("[data-paint]").forEach((btn) => {
    btn.onclick = () => {
      b.tech.paintId = btn.dataset.paint;
      state.savedMsg = "";
      render();
    };
  });
  const bindSel = (sel, fn) => {
    const el = app.querySelector(sel);
    if (!el) return;
    el.onchange = () => {
      fn(el.value);
      ensureValid(b);
      state.savedMsg = "";
      render();
    };
  };
  bindSel("#cab-htype", (v) => {
    b.houseType = v;
    b.tech.techId = defaultTechId(b.houseType, b.condition, b.material);
  });
  bindSel("#cab-cond", (v) => {
    b.condition = v;
    b.tech.techId = defaultTechId(b.houseType, b.condition, b.material);
  });
  app.querySelector("#cab-colors")?.addEventListener("change", (e) => {
    b.colors = e.target.value;
  });
  app.querySelector("#cab-disc")?.addEventListener("change", (e) => {
    s.estimate = s.estimate || {};
    s.estimate.discountPct = Number(e.target.value) || 0;
    render();
  });

  app.querySelector("#cab-save").onclick = async () => {
    state.busy = true;
    state.error = "";
    state.savedMsg = "";
    render();
    try {
      const payload = withSnapshot(state.survey);
      const res = await api("/bestpaints/api/client/survey", {
        method: "PUT",
        body: JSON.stringify({ survey: payload }),
      });
      state.survey = migrateSurvey(res.survey || payload);
      state.savedMsg =
        (res.changes || []).length
          ? `Сохранено · зафиксировано изменений: ${res.changes.length}`
          : "Сохранено (без изменений полей)";
      state.bundle.version = res.version;
    } catch (e) {
      state.error = e.message || String(e);
    } finally {
      state.busy = false;
      render();
    }
  };
  app.querySelector("#cab-pdf").onclick = () => openClientReport(withSnapshot(state.survey), catalog);
}

function render() {
  if (!catalog) {
    app.innerHTML = `<p style="padding:24px;color:#5a6b60">Загрузка…</p>`;
    return;
  }
  if (!state.survey) renderLogin();
  else renderCabinet();
}

async function boot() {
  state.token = magicTokenFromPath();
  catalog = await fetch("/bestpaints/data/catalog.json").then((r) => r.json());
  try {
    await loadMe();
  } catch {
    /* need login */
  }
  render();
}

boot();
