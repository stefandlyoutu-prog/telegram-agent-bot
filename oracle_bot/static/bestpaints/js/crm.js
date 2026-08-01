/** BestPaints CRM — сделки Лидоруба, статусы, чек-листы, график. */

import { importEstimateHtml, bindImportEstimatePanel } from "./estimate_import.js";

const API = "/bestpaints/api";
const CRM_ROLE_KEY = "bp_crm_role_v1";

/** Роль в кабинете (общий пароль): кто создаёт сделки. */
export function getCrmRole() {
  const r = (localStorage.getItem(CRM_ROLE_KEY) || "surveyor").trim().toLowerCase();
  return ["lidarub", "surveyor", "manager", "admin"].includes(r) ? r : "surveyor";
}

export function setCrmRole(role) {
  localStorage.setItem(CRM_ROLE_KEY, role);
}

export function canCreateDeals() {
  return ["lidarub", "admin"].includes(getCrmRole());
}

function monthPeriodOptions() {
  const out = [];
  const now = new Date();
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const ym = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleString("ru-RU", { month: "long", year: "numeric" });
    out.push([`m:${ym}`, label.charAt(0).toUpperCase() + label.slice(1)]);
  }
  return out;
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(`${API}${path}`, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
  } catch (e) {
    throw new Error(`Сеть: ${e && e.message ? e.message : "нет связи с сервером"}`);
  }
  if (res.status === 401) {
    location.href = "/bestpaints/login";
    throw new Error("login");
  }
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    let detail = data && (data.detail || data.message);
    if (typeof detail !== "string") {
      detail = detail != null ? JSON.stringify(detail) : "";
    }
    const raw = data && typeof data.raw === "string" ? data.raw.replace(/\s+/g, " ").trim().slice(0, 120) : "";
    const hint = detail || res.statusText || raw || "ошибка сервера";
    throw new Error(`HTTP ${res.status}: ${hint}`);
  }
  return data;
}

export async function fetchMeta() {
  return api("/meta");
}

export async function fetchObjects(status) {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const data = await api(`/objects${q}`);
  return data.objects || [];
}

export async function createObject(payload) {
  return api("/objects", { method: "POST", body: JSON.stringify(payload) });
}

export async function fetchObject(id) {
  return api(`/objects/${encodeURIComponent(id)}`);
}

export async function doAction(id, action, extra = {}) {
  return api(`/objects/${encodeURIComponent(id)}/action`, {
    method: "POST",
    body: JSON.stringify({ action, ...extra }),
  });
}

export async function fetchSchedule(date) {
  const q = date ? `?date=${encodeURIComponent(date)}` : "";
  return api(`/schedule${q}`);
}

export async function setSchedule(payload) {
  return api("/schedule", { method: "POST", body: JSON.stringify(payload) });
}

export async function upsertStaffPerson(payload) {
  return api("/staff/person", { method: "POST", body: JSON.stringify(payload) });
}

export async function deleteStaffPerson(role, id) {
  return api(`/staff/person/${encodeURIComponent(role)}/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function fetchAnalytics(period = "30d") {
  return api(`/analytics?period=${encodeURIComponent(period)}`);
}

export async function fetchPayroll(period = "30d") {
  return api(`/payroll?period=${encodeURIComponent(period)}`);
}

function moneyFmt(n) {
  const v = Math.round(Number(n) || 0);
  return v.toLocaleString("ru-RU") + " ₽";
}

function nickOf(p) {
  const u = String(p?.tg_username || "").replace(/^@/, "");
  return u ? `@${u}` : "";
}

function personLine(p) {
  const nick = nickOf(p);
  const link = p?.tg_id ? " · связан" : nick ? "" : " · укажите @ник";
  return `${esc(p?.name || p?.id || "?")}${nick ? ` · <span class="crm-nick">${esc(nick)}</span>` : ""}${esc(link)}`;
}

/** Кнопки следующего шага по статусу */
const NEXT_ACTIONS = {
  created: [], // назначение — отдельная панель (график / список / новый)
  assigned: [
    { action: "accept", label: "Взял в работу", primary: true },
  ],
  accepted: [{ action: "confirm_visit", label: "Выезд подтверждён", primary: true }],
  visit_confirmed: [
    { action: "start_measure", label: "На адресе · начинаю замер", primary: true },
    { action: "open_survey", label: "Открыть конструктор (со строения)", ghost: true },
  ],
  on_site: [
    { action: "open_survey", label: "Конструктор / смета", primary: true },
    { action: "sign_on_site", label: "Заключил на адресе", primary: true },
    { action: "decline_on_site", label: "Не заключил", danger: true },
  ],
  contract_signed: [
    { action: "close", label: "Закрыть сделку", primary: true },
  ],
  contract_declined: [
    { action: "assign_manager", label: "Отдать менеджеру (защита ТЗ)", primary: true },
  ],
  manager_assigned: [
    { action: "manager_accept", label: "Менеджер взял в работу", primary: true },
    { action: "open_survey", label: "Смотреть замер", ghost: true },
  ],
  manager_accepted: [
    { action: "sign_on_site", label: "Менеджер заключил", primary: true },
    { action: "close", label: "Закрыть", ghost: true },
  ],
  closed: [
    { action: "reopen", label: "Вернуть в работу", primary: true },
  ],
};

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTs(ts) {
  if (!ts) return "";
  try {
    return new Date(ts * 1000).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export function statusPill(obj) {
  const color = obj.status_color || "#9aada2";
  return `<span class="crm-pill" style="--crm-c:${esc(color)}">${esc(obj.status_label || obj.status)}</span>`;
}

export function boardHtml(objects) {
  if (!objects.length) {
    return `<div class="empty crm-empty">Пока нет сделок. Создайте здесь или через бота <code>/zamer</code>.</div>`;
  }
  return `<div class="crm-list">${objects
    .map(
      (o) => `
    <button type="button" class="crm-card" data-crm-open="${esc(o.id)}">
      <div class="crm-card-top">
        <strong>${esc(o.title)}</strong>
        ${o.deal_source === "import_estimate" ? `<span class="crm-pill" style="--crm-c:#8e7cc3">Импорт</span>` : ""}
        ${statusPill(o)}
      </div>
      <div class="crm-card-meta">
        ${esc(o.address || "без адреса")}
        ${o.measure_date ? ` · ${esc(o.measure_date)}` : ""}
        ${o.surveyor_name ? ` · ${esc(o.surveyor_name)}` : ""}
        ${Number(o.amount_total) > 0 ? ` · <span class="crm-money">${esc(moneyFmt(o.amount_total))}</span>` : ""}
        ${Number(o.discount_pct) > 0 ? ` · −${esc(String(o.discount_pct))}%` : ""}
        ${o.escalated_at ? ` · <span class="crm-escalated">эскалация</span>` : ""}
      </div>
    </button>`
    )
    .join("")}</div>`;
}

const CREATE_DRAFT_KEY = "bp_crm_create_draft_v1";

function loadCreateDraft() {
  try {
    return JSON.parse(sessionStorage.getItem(CREATE_DRAFT_KEY) || "null");
  } catch {
    return null;
  }
}

function saveCreateDraft(form) {
  if (!form) return;
  const fd = new FormData(form);
  const data = Object.fromEntries(fd.entries());
  try {
    sessionStorage.setItem(CREATE_DRAFT_KEY, JSON.stringify(data));
  } catch {
    /* ignore */
  }
}

function clearCreateDraft() {
  try {
    sessionStorage.removeItem(CREATE_DRAFT_KEY);
  } catch {
    /* ignore */
  }
}

export function createFormHtml(meta) {
  const draft = loadCreateDraft() || {};
  const surv = (meta?.staff?.surveyors || [])
    .map((s) => {
      const sel = draft.surveyor_id && draft.surveyor_id === s.id ? "selected" : "";
      return `<option value="${esc(s.id)}" ${sel}>${esc(s.name)}${nickOf(s) ? " " + nickOf(s) : ""}</option>`;
    })
    .join("");
  const today = draft.measure_date || meta?.today || "";
  const duty = (meta?.on_duty_surveyors || []).map((s) => s.name).join(", ") || "никого в графике";
  const v = (k) => esc(draft[k] || "");
  return `
  <form class="crm-create" id="crm-create-form" method="post" action="#" novalidate>
    <h3>Новая сделка</h3>
    <p class="hint">Сегодня на смене: ${esc(duty)}</p>
    <label>Название<input name="title" required placeholder="Как в CRM" value="${v("title")}" autocomplete="off" /></label>
    <label>Квалификация<textarea name="qualification" rows="2" placeholder="Кратко">${v("qualification")}</textarea></label>
    <label>Адрес<input name="address" required value="${v("address")}" autocomplete="off" /></label>
    <label>Дата замера<input name="measure_date" type="date" value="${esc(today)}" /></label>
    <div class="crm-form-row">
      <label>Клиент<input name="client_name" value="${v("client_name")}" autocomplete="name" /></label>
      <label>Телефон<input name="client_phone" type="tel" value="${v("client_phone")}" autocomplete="tel" /></label>
    </div>
    <label>Замерщик
      <select name="surveyor_id" id="crm-create-surveyor">
        <option value="">Авто из графика</option>
        ${surv}
      </select>
    </label>
    <button type="button" class="btn primary block" id="crm-create-submit">Создать</button>
  </form>`;
}

function chipHtml(person, role, onDutyIds) {
  const on = onDutyIds.has(person.id);
  const nick = nickOf(person);
  return `<button type="button" class="crm-chip ${on ? "on" : ""}" data-sch-toggle="${esc(role)}:${esc(person.id)}" title="${esc(nick || "без ника")}">
    <span class="crm-chip-name">${esc(person.name)}</span>
    <span class="crm-chip-nick">${esc(nick || "—")}</span>
  </button>`;
}

export function schedulePanelHtml(meta, day) {
  const d = day || meta?.today || "";
  const onS = new Set((meta?.on_duty_surveyors || []).map((x) => x.id));
  const onM = new Set((meta?.on_duty_managers || []).map((x) => x.id));
  const surv = meta?.staff?.surveyors || [];
  const mgr = meta?.staff?.managers || [];
  return `
  <div class="crm-panel-inner">
    <div class="crm-panel-head">
      <div>
        <h3>График смен</h3>
        <p class="hint">Нажмите имя — в смене / вне смены. Бот: <code>/grafik_fill</code></p>
      </div>
      <input type="date" id="crm-sch-date" value="${esc(d)}" class="crm-date" />
    </div>
    <div class="crm-chip-block">
      <div class="crm-chip-label">Замерщики</div>
      <div class="crm-chips">${surv.map((p) => chipHtml(p, "surveyor", onS)).join("") || "<span class='hint'>Добавьте в «Команда»</span>"}</div>
    </div>
    <div class="crm-chip-block">
      <div class="crm-chip-label">Менеджеры</div>
      <div class="crm-chips">${mgr.map((p) => chipHtml(p, "manager", onM)).join("") || "<span class='hint'>Добавьте в «Команда»</span>"}</div>
    </div>
    <div class="crm-row-actions">
      <button type="button" class="btn primary" id="crm-sch-fill">Всех на день</button>
      <button type="button" class="btn ghost" id="crm-sch-clear">Очистить</button>
    </div>
  </div>`;
}

function teamRowHtml(p, role) {
  const nick = nickOf(p);
  const linked = p.tg_id ? `<span class="crm-linked" title="Telegram связан">●</span>` : "";
  return `
  <article class="crm-team-row" data-role="${esc(role)}" data-id="${esc(p.id)}">
    <div class="crm-team-info">
      <strong>${esc(p.name)} ${linked}</strong>
      <span>${esc(nick || "нет @ника")}${p.phone ? " · " + esc(p.phone) : ""}</span>
    </div>
    <div class="crm-team-btns">
      <button type="button" class="btn ghost sm" data-team-edit>Изменить</button>
      <button type="button" class="btn ghost sm" data-team-del title="Удалить">✕</button>
    </div>
  </article>`;
}

export function teamPanelHtml(meta) {
  const staff = meta?.staff || {};
  const roles = [
    ["lidarubs", "lidarub", "Лидорубы"],
    ["surveyors", "surveyor", "Замерщики"],
    ["managers", "manager", "Менеджеры"],
  ];
  return `
  <div class="crm-panel-inner">
    <div class="crm-panel-head">
      <div>
        <h3>Команда</h3>
        <p class="hint">Имя + @ник Telegram — бот узнает человека при <code>/start</code> и пишет в Ops с упоминанием.</p>
      </div>
    </div>
    <form class="crm-team-add" id="crm-team-add">
      <select name="role" required>
        <option value="surveyor">Замерщик</option>
        <option value="manager">Менеджер</option>
        <option value="lidarub">Лидоруб</option>
      </select>
      <input name="name" required placeholder="Имя" />
      <input name="tg_username" placeholder="@ник" />
      <input name="phone" placeholder="+7…" />
      <button type="submit" class="btn primary">Добавить</button>
    </form>
    ${roles
      .map(([key, role, title]) => {
        const list = staff[key] || [];
        return `<div class="crm-team-group">
          <div class="crm-chip-label">${esc(title)}</div>
          ${list.map((p) => teamRowHtml(p, role)).join("") || "<p class='hint'>Пусто</p>"}
        </div>`;
      })
      .join("")}
    <p class="hint crm-bot-hint">Бот <a href="https://t.me/BestPaints_Zamerbot" target="_blank" rel="noopener">@BestPaints_Zamerbot</a>
      · после добавления @ника человек пишет боту <code>/start</code> — появляется «связан».</p>
  </div>`;
}

export function homeCrmSectionHtml() {
  const role = getCrmRole();
  const roles = [
    ["lidarub", "Лидоруб"],
    ["surveyor", "Замерщик"],
    ["manager", "Менеджер"],
    ["admin", "Админ"],
  ];
  return `
  <section class="crm-shell" id="crm-shell">
    <div class="crm-role-bar" id="crm-role-bar">
      <span>Я в кабинете как:</span>
      ${roles
        .map(
          ([id, label]) =>
            `<button type="button" class="crm-role-chip ${role === id ? "on" : ""}" data-crm-role="${id}">${label}</button>`
        )
        .join("")}
      <em class="hint" style="margin-left:auto">Сделки: лидоруб или админ</em>
    </div>
    <nav class="crm-tabs" role="tablist">
      <button type="button" class="crm-tab active" data-tab="deals">Сделки</button>
      <button type="button" class="crm-tab" data-tab="analytics">Аналитика</button>
      <button type="button" class="crm-tab" data-tab="payroll">ЗП</button>
      <button type="button" class="crm-tab" data-tab="schedule">График</button>
      <button type="button" class="crm-tab" data-tab="team">Команда</button>
      <button type="button" class="crm-tab" data-tab="cabinets">Кабинеты</button>
    </nav>
    <div class="crm-tab-panels">
      <div class="crm-tab-panel" id="crm-panel-deals" data-panel="deals">
        <div class="crm-panel-head">
          <div>
            <h3>Сделки</h3>
            <p class="hint" id="crm-duty-hint">Загрузка графика…</p>
          </div>
          <div class="crm-panel-head-btns">
            <button type="button" class="btn primary" id="crm-toggle-create" ${canCreateDeals() ? "" : "hidden"}>+ Сделка</button>
            <button type="button" class="btn ghost" id="crm-toggle-import" ${canCreateDeals() ? "" : "hidden"}>Загрузить готовую смету</button>
          </div>
        </div>
        <p class="hint" id="crm-create-lock" ${canCreateDeals() ? "hidden" : ""}>Создание сделок — у лидоруба. Переключите роль выше, если вы лидоруб.</p>
        <div id="crm-create-wrap" class="crm-create-wrap" hidden></div>
        <div id="crm-import-wrap" class="crm-create-wrap" hidden></div>
        <div id="crm-filter-bar" class="crm-filter-bar" hidden></div>
        <div id="crm-deals-list"></div>
      </div>
      <div class="crm-tab-panel" id="crm-panel-analytics" data-panel="analytics" hidden></div>
      <div class="crm-tab-panel" id="crm-panel-payroll" data-panel="payroll" hidden></div>
      <div class="crm-tab-panel" id="crm-panel-schedule" data-panel="schedule" hidden></div>
      <div class="crm-tab-panel" id="crm-panel-team" data-panel="team" hidden></div>
      <div class="crm-tab-panel" id="crm-panel-cabinets" data-panel="cabinets" hidden></div>
    </div>
  </section>`;
}

function analyticsHtml(data, period) {
  const k = data.kpis || {};
  const maxFunnel = Math.max(1, ...((data.funnel || []).map((f) => f.count)));
  return `
  <div class="crm-panel-inner an-root">
    <div class="crm-panel-head">
      <div>
        <h3>Аналитика</h3>
        <p class="hint">${esc(data.from || "…")} → ${esc(data.to || "…")} · нажмите блок — откроются сделки</p>
      </div>
    </div>
    <div class="an-periods" id="an-periods">
      ${[
        ["7d", "7 дней"],
        ["30d", "30 дней"],
        ["month", "Месяц"],
        ["all", "Всё"],
      ]
        .map(
          ([id, label]) =>
            `<button type="button" class="an-period ${period === id ? "on" : ""}" data-period="${id}">${label}</button>`
        )
        .join("")}
    </div>
    <div class="an-hero">
      <button type="button" class="an-hero-card win" data-an-filter="signed">
        <span>Заключено</span>
        <strong>${esc(moneyFmt(k.signed_sum))}</strong>
        <em>${esc(String(k.signed || 0))} сделок →</em>
      </button>
      <button type="button" class="an-hero-card work" data-an-filter="in_work">
        <span>В работе</span>
        <strong>${esc(String(k.in_work || 0))}</strong>
        <em>сделок →</em>
      </button>
      <button type="button" class="an-hero-card lose" data-an-filter="declined">
        <span>Не заключено</span>
        <strong>${esc(String(k.declined || 0))}</strong>
        <em>сделок →</em>
      </button>
    </div>
    <details class="an-more">
      <summary>Ещё цифры · конверсия, чек, скидка, м²</summary>
      <div class="an-kpis">
        <div class="an-kpi"><span>Конверсия</span><strong>${esc(String(k.conversion_pct || 0))}%</strong></div>
        <div class="an-kpi"><span>Средний чек</span><strong>${esc(moneyFmt(k.avg_check))}</strong></div>
        <div class="an-kpi"><span>Ср. скидка</span><strong>${esc(String(k.avg_discount_pct || 0))}%</strong></div>
        <div class="an-kpi"><span>Скидки, ₽</span><strong>${esc(moneyFmt(k.discount_rub))}</strong></div>
        <button type="button" class="an-kpi an-kpi-btn" data-an-filter="measured"><span>Замеров</span><strong>${esc(String(k.measures || 0))} →</strong></button>
        <div class="an-kpi"><span>Площадь</span><strong>${esc(String(k.area_m2 || 0))} м²</strong></div>
      </div>
    </details>
    <details class="an-more">
      <summary>Воронка</summary>
      <div class="an-funnel">
        ${(data.funnel || [])
          .filter((f) => f.count > 0)
          .map(
            (f) => `
          <button type="button" class="an-funnel-row" data-an-status="${esc(f.id)}">
            <span>${esc(f.label)}</span>
            <div class="an-bar"><i style="width:${Math.round((100 * f.count) / maxFunnel)}%;background:${esc(f.color)}"></i></div>
            <b>${esc(String(f.count))} →</b>
          </button>`
          )
          .join("") || "<p class='hint'>Нет сделок за период</p>"}
      </div>
    </details>
    <details class="an-more">
      <summary>По замерщикам</summary>
      <div class="an-people">
        ${(data.by_surveyor || [])
          .map(
            (p) => `
          <button type="button" class="an-person" data-an-surveyor="${esc(p.name)}">
            <strong>${esc(p.name)} →</strong>
            <span>${esc(String(p.deals))} · ✅ ${esc(String(p.signed))} · ✕ ${esc(String(p.declined))}</span>
            <em>${esc(moneyFmt(p.sum_signed))} заключено</em>
          </button>`
          )
          .join("") || "<p class='hint'>Пока пусто</p>"}
      </div>
    </details>
    ${
      (data.top_signed || []).length
        ? `<details class="an-more">
      <summary>Топ договоров</summary>
      <div class="an-top">
        ${data.top_signed
          .map(
            (t) => `<button type="button" class="an-top-row" data-crm-open="${esc(t.id)}">
              <span>${esc(t.title)}</span>
              <b>${esc(moneyFmt(t.amount_total))}${t.discount_pct ? ` <i>−${esc(String(t.discount_pct))}%</i>` : ""}</b>
            </button>`
          )
          .join("")}
      </div>
    </details>`
        : ""
    }
  </div>`;
}

function zpPersonCards(people, emptyHint) {
  if (!people.length) return `<p class="hint" style="padding:8px">${emptyHint}</p>`;
  return people
    .map((p) => {
      const deals = p.deals || [];
      return `
        <details class="zp-person el-card">
          <summary>
            <span>
              <strong>${esc(p.name)}</strong>
              <em>${esc(String(p.deals_count || 0))} дог. · обороты ${esc(moneyFmt(p.sum_contracts || 0))}</em>
            </span>
            <b class="zp-sum">${esc(moneyFmt(p.sum_payroll || 0))}</b>
          </summary>
          <div class="el-card-body zp-deals">
            ${
              deals.length
                ? deals
                    .map(
                      (d) => `
              <button type="button" class="zp-deal" data-crm-open="${esc(d.id)}">
                <div class="zp-deal-top">
                  <strong>${esc(d.title || "Без названия")}</strong>
                  <b>${esc(moneyFmt(d.commission))}</b>
                </div>
                <div class="zp-deal-meta">
                  ${esc(d.address || "—")}
                  ${d.measure_date ? ` · ${esc(d.measure_date)}` : ""}
                </div>
                <div class="zp-deal-meta">
                  Договор ${esc(moneyFmt(d.amount_total))}
                  ${d.discount_pct != null ? ` · скидка ${esc(String(d.discount_pct || 0))}%` : ""}
                  · ${esc(d.place_label || "")}
                  · ставка ${esc(String(d.rate_pct))}%
                </div>
                <div class="zp-deal-rule">${esc(d.rule || "")} →</div>
              </button>`
                    )
                    .join("")
                : `<p class="hint">Нет заключённых с суммой за период</p>`
            }
          </div>
        </details>`;
    })
    .join("");
}

function payrollHtml(data, period, roleFilter = "surveyors") {
  const surveyors = data.by_surveyor || [];
  const managers = data.by_manager || [];
  const months = monthPeriodOptions();
  const periodBtns = [
    ["7d", "7 дней"],
    ["30d", "30 дней"],
    ["month", "Этот месяц"],
    ...months.slice(0, 4),
    ["all", "Всё"],
  ];
  const showSv = roleFilter !== "managers";
  const showMg = roleFilter !== "surveyors";
  return `
  <div class="crm-panel-inner an-root zp-root">
    <div class="crm-panel-head">
      <div>
        <h3>ЗП · мотивация</h3>
        <p class="hint">${esc(data.from || "…")} → ${esc(data.to || "…")} · нажмите сделку — откроется объект</p>
      </div>
    </div>
    <div class="an-periods" id="zp-periods">
      ${periodBtns
        .map(
          ([id, label]) =>
            `<button type="button" class="an-period ${period === id ? "on" : ""}" data-zp-period="${id}">${label}</button>`
        )
        .join("")}
    </div>
    <div class="zp-role-tabs" id="zp-role-tabs">
      ${[
        ["surveyors", "Замерщики"],
        ["managers", "Менеджеры"],
        ["all", "Все"],
      ]
        .map(
          ([id, label]) =>
            `<button type="button" class="crm-role-chip ${roleFilter === id ? "on" : ""}" data-zp-role="${id}">${label}</button>`
        )
        .join("")}
    </div>
    <div class="an-hero">
      ${
        showSv
          ? `<div class="an-hero-card win zp-total-card">
        <span>Замерщики</span>
        <strong>${esc(moneyFmt(data.total_payroll || 0))}</strong>
        <em>${esc(String(surveyors.length))} чел.</em>
      </div>`
          : ""
      }
      ${
        showMg
          ? `<div class="an-hero-card zp-total-card">
        <span>Менеджеры</span>
        <strong>${esc(moneyFmt(data.total_manager_payroll || 0))}</strong>
        <em>${esc(String(managers.length))} чел. · ${esc(String((data.manager_rules || [])[0]?.rate_pct ?? 1))}%</em>
      </div>`
          : ""
      }
    </div>
    <details class="an-more">
      <summary>Правила мотивации</summary>
      <ul class="zp-rules">
        <li><b>Замерщик</b> на адресе, скидка <b>0%</b> → <b>5%</b></li>
        <li>На адресе, скидка <b>1–5%</b> → <b>3%</b> · <b>6–10%+</b> → <b>2%</b></li>
        <li>Из офиса → <b>1%</b></li>
        <li><b>Менеджер</b> с заключённого договора → <b>${esc(String((data.manager_rules || [])[0]?.rate_pct ?? 1))}%</b> (если назначен на сделку)</li>
      </ul>
    </details>
    ${
      showSv
        ? `<h4 class="subhead" style="margin:12px 0 6px">Замерщики</h4>
    <div class="zp-people" data-zp-group="surveyors">
      ${zpPersonCards(surveyors, "Пока нет ЗП замерщиков за период — нужны заключённые договоры с суммой.")}
    </div>`
        : ""
    }
    ${
      showMg
        ? `<h4 class="subhead" style="margin:16px 0 6px">Менеджеры</h4>
    <div class="zp-people" data-zp-group="managers">
      ${zpPersonCards(managers, "Нет ЗП менеджеров: нужны заключённые сделки с назначенным менеджером.")}
    </div>`
        : ""
    }
  </div>`;
}


async function loadCabinetsPanel(root, toast, onOpenDetail) {
  const panel = root.querySelector("#crm-panel-cabinets");
  if (!panel) return;
  panel.innerHTML = `<div class="crm-panel-inner"><h3>Кабинеты клиентов</h3><p class="hint">Все кабинеты · логи изменений видны в карточке сделки</p><div id="crm-cab-list">Загрузка…</div></div>`;
  try {
    const pack = await api("/cabinets");
    const list = pack.cabinets || [];
    const el = panel.querySelector("#crm-cab-list");
    if (!list.length) {
      el.innerHTML = `<p class="hint">Пока нет кабинетов. Откройте из карточки сделки после сметы.</p>`;
      return;
    }
    el.innerHTML = `<div class="crm-deals">${list
      .map((c) => {
        const o = c.object || {};
        return `<button type="button" class="crm-deal" data-cab-open="${esc(c.id)}" data-crm-open="${esc(c.object_id)}">
          <div class="crm-deal-title">${esc(c.client_name || o.title || "Клиент")} · ${esc(c.client_phone)}</div>
          <div class="crm-deal-meta">${esc(o.address || "")} · ${esc(o.surveyor_name || "—")} · ${esc(c.status)}
          ${Number(o.amount_total) > 0 ? ` · ${esc(moneyFmt(o.amount_total))}` : ""}</div>
        </button>`;
      })
      .join("")}</div>
      <details class="crm-fold" style="margin-top:12px"><summary>Лог выбранного кабинета</summary>
        <ul class="crm-events" id="crm-cab-log-view"><li class="hint">Нажмите кабинет</li></ul>
      </details>`;
    el.querySelectorAll("[data-cab-open]").forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-cab-open");
        const oid = btn.getAttribute("data-crm-open");
        try {
          const detail = await api(`/cabinets/${encodeURIComponent(id)}`);
          const logs = detail.logs || [];
          const box = panel.querySelector("#crm-cab-log-view");
          if (box) {
            box.innerHTML = logs
              .slice(0, 60)
              .map((e) => `<li><span class="hint">${fmtTs(e.created_at)}</span> <b>${esc(e.actor_type)}</b> · ${esc(e.message)}</li>`)
              .join("") || "<li class='hint'>Пусто</li>";
          }
          // also allow jump to deal
          if (oid && typeof window.__bpOpenCrmDeal === "function") {
            /* optional */
          }
          toast(`${detail.cabinet?.client_name || "Кабинет"} · ${logs.length} записей лога`);
          if (oid && typeof onOpenDetail === "function") onOpenDetail(oid);
        } catch (e) {
          toast(String(e.message || e));
        }
      };
    });
  } catch (e) {
    panel.querySelector("#crm-cab-list").textContent = String(e.message || e);
  }
}

export async function mountHomeCrm(ctx) {
  const { root, toast, onOpenDetail, getMeta } = ctx;
  const shell = root.querySelector("#crm-shell");
  if (!shell) return;

  let meta;
  let objects;
  let dealFilter = null; // { type, value, label }
  try {
    objects = await fetchObjects();
    meta = await getMeta();
  } catch (e) {
    shell.insertAdjacentHTML(
      "beforeend",
      `<div class="callout danger">CRM недоступен: ${esc(e.message)}</div>`
    );
    return;
  }

  const duty = (meta.on_duty_surveyors || []).map((s) => s.name).join(", ") || "никого — откройте «График»";
  const dutyEl = root.querySelector("#crm-duty-hint");
  if (dutyEl) dutyEl.textContent = `На смене сегодня: ${duty}`;

  const listEl = root.querySelector("#crm-deals-list");
  const filterBar = root.querySelector("#crm-filter-bar");

  const WON = new Set(["contract_signed", "closed"]);
  const LOST = new Set(["contract_declined"]);
  const WORK = new Set([
    "created",
    "assigned",
    "accepted",
    "visit_confirmed",
    "on_site",
    "manager_assigned",
    "manager_accepted",
  ]);

  function filteredObjects() {
    if (!dealFilter) return objects;
    const { type, value } = dealFilter;
    return objects.filter((o) => {
      if (type === "signed") return WON.has(o.status);
      if (type === "declined") return LOST.has(o.status);
      if (type === "in_work") return WORK.has(o.status);
      if (type === "measured") {
        return (
          o.on_site_at ||
          ["on_site", "contract_signed", "contract_declined", "manager_assigned", "manager_accepted", "closed"].includes(
            o.status
          )
        );
      }
      if (type === "status") return o.status === value;
      if (type === "surveyor") return (o.surveyor_name || "Без замерщика") === value;
      return true;
    });
  }

  function paintDeals() {
    const rows = filteredObjects();
    if (filterBar) {
      if (dealFilter) {
        filterBar.hidden = false;
        filterBar.innerHTML = `<span>Фильтр: <strong>${esc(dealFilter.label)}</strong> · ${rows.length}</span>
          <button type="button" class="btn ghost sm" id="crm-filter-clear">Сбросить</button>`;
        filterBar.querySelector("#crm-filter-clear").onclick = () => {
          dealFilter = null;
          paintDeals();
        };
      } else {
        filterBar.hidden = true;
        filterBar.innerHTML = "";
      }
    }
    if (listEl) listEl.innerHTML = boardHtml(rows);
    root.querySelectorAll("#crm-deals-list [data-crm-open]").forEach((btn) => {
      btn.onclick = (ev) => {
        ev.preventDefault();
        onOpenDetail(btn.getAttribute("data-crm-open"));
      };
    });
  }

  paintDeals();

  let zpRoleFilter = "surveyors";

  function syncCreateUi() {
    const toggle = root.querySelector("#crm-toggle-create");
    const importToggle = root.querySelector("#crm-toggle-import");
    const lock = root.querySelector("#crm-create-lock");
    const wrap = root.querySelector("#crm-create-wrap");
    const importWrap = root.querySelector("#crm-import-wrap");
    const ok = canCreateDeals();
    if (toggle) toggle.hidden = !ok;
    if (importToggle) importToggle.hidden = !ok;
    if (lock) lock.hidden = ok;
    if (!ok && wrap) {
      wrap.hidden = true;
      wrap.innerHTML = "";
    }
    if (!ok && importWrap) {
      importWrap.hidden = true;
      importWrap.innerHTML = "";
    }
  }

  root.querySelectorAll("[data-crm-role]").forEach((btn) => {
    btn.onclick = () => {
      setCrmRole(btn.getAttribute("data-crm-role"));
      root.querySelectorAll("[data-crm-role]").forEach((b) => {
        b.classList.toggle("on", b.getAttribute("data-crm-role") === getCrmRole());
      });
      syncCreateUi();
      toast(`Роль: ${btn.textContent}`);
    };
  });
  syncCreateUi();

  const showTab = (name) => {
    root.querySelectorAll(".crm-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    root.querySelectorAll(".crm-tab-panel").forEach((p) => {
      p.hidden = p.dataset.panel !== name;
    });
  };

  function applyAnFilter(type, value, label) {
    dealFilter = { type, value, label };
    showTab("deals");
    paintDeals();
    toast(label);
  }

  root.querySelectorAll(".crm-tab").forEach((tab) => {
    tab.onclick = async () => {
      showTab(tab.dataset.tab);
      if (tab.dataset.tab === "schedule") await renderSchedule();
      if (tab.dataset.tab === "team") await renderTeam();
      if (tab.dataset.tab === "analytics") await renderAnalytics("30d");
      if (tab.dataset.tab === "payroll") await renderPayroll("30d");
      if (tab.dataset.tab === "cabinets") await loadCabinetsPanel(root, toast, onOpenDetail);
    };
  });

  async function refreshMeta() {
    meta = await getMeta();
    const d = (meta.on_duty_surveyors || []).map((s) => s.name).join(", ") || "никого — откройте «График»";
    if (dutyEl) dutyEl.textContent = `На смене сегодня: ${d}`;
  }

  async function renderPayroll(period, roleFilter = zpRoleFilter) {
    const panel = root.querySelector("#crm-panel-payroll");
    if (!panel) return;
    zpRoleFilter = roleFilter || "surveyors";
    panel.innerHTML = `<p class="hint" style="padding:12px">Считаем ЗП…</p>`;
    try {
      const data = await fetchPayroll(period);
      panel.innerHTML = payrollHtml(data, period, zpRoleFilter);
      panel.querySelectorAll("[data-zp-period]").forEach((btn) => {
        btn.onclick = () => renderPayroll(btn.getAttribute("data-zp-period"), zpRoleFilter);
      });
      panel.querySelectorAll("[data-zp-role]").forEach((btn) => {
        btn.onclick = () => renderPayroll(period, btn.getAttribute("data-zp-role"));
      });
      panel.querySelectorAll("[data-crm-open]").forEach((btn) => {
        btn.onclick = (ev) => {
          ev.preventDefault();
          onOpenDetail(btn.getAttribute("data-crm-open"));
        };
      });
    } catch (err) {
      panel.innerHTML = `<div class="callout danger">${esc(err.message || err)}</div>`;
    }
  }

  async function renderAnalytics(period) {
    const panel = root.querySelector("#crm-panel-analytics");
    panel.innerHTML = `<p class="hint" style="padding:12px">Считаем…</p>`;
    try {
      const data = await fetchAnalytics(period);
      panel.innerHTML = analyticsHtml(data, period);
      panel.querySelectorAll("[data-period]").forEach((btn) => {
        btn.onclick = () => renderAnalytics(btn.getAttribute("data-period"));
      });
      panel.querySelectorAll("[data-an-filter]").forEach((btn) => {
        btn.onclick = () => {
          const t = btn.getAttribute("data-an-filter");
          const labels = {
            signed: "Заключено",
            in_work: "В работе",
            declined: "Не заключено",
            measured: "С замером",
          };
          applyAnFilter(t, t, labels[t] || t);
        };
      });
      panel.querySelectorAll("[data-an-status]").forEach((btn) => {
        btn.onclick = () => {
          const st = btn.getAttribute("data-an-status");
          const lab = (meta.statuses || []).find((s) => s.id === st)?.label || st;
          applyAnFilter("status", st, lab);
        };
      });
      panel.querySelectorAll("[data-an-surveyor]").forEach((btn) => {
        btn.onclick = () => {
          const name = btn.getAttribute("data-an-surveyor");
          applyAnFilter("surveyor", name, `Замерщик: ${name}`);
        };
      });
      panel.querySelectorAll("[data-crm-open]").forEach((btn) => {
        btn.onclick = (ev) => {
          ev.preventDefault();
          onOpenDetail(btn.getAttribute("data-crm-open"));
        };
      });
    } catch (err) {
      panel.innerHTML = `<div class="callout danger">${esc(err.message || err)}</div>`;
    }
  }

  async function renderSchedule() {
    const panel = root.querySelector("#crm-panel-schedule");
    const day = root.querySelector("#crm-sch-date")?.value || meta.today;
    const pack = await fetchSchedule(day);
    const view = {
      ...meta,
      today: day,
      schedule_today: pack.items || [],
      on_duty_surveyors: pack.on_duty_surveyors || [],
      on_duty_managers: pack.on_duty_managers || [],
    };
    panel.innerHTML = schedulePanelHtml(view, day);
    panel.querySelector("#crm-sch-date")?.addEventListener("change", () => renderSchedule().catch((e) => toast(String(e.message || e))));
    panel.querySelector("#crm-sch-fill")?.addEventListener("click", async () => {
      const d = panel.querySelector("#crm-sch-date")?.value || meta.today;
      await setSchedule({ fill_all: true, work_date: d });
      toast(`Все на ${d}`);
      await refreshMeta();
      await renderSchedule();
    });
    panel.querySelector("#crm-sch-clear")?.addEventListener("click", async () => {
      const d = panel.querySelector("#crm-sch-date")?.value || meta.today;
      if (!confirm(`Очистить смену ${d}?`)) return;
      await setSchedule({ clear: true, work_date: d });
      toast("Очищено");
      await refreshMeta();
      await renderSchedule();
    });
    panel.querySelectorAll("[data-sch-toggle]").forEach((btn) => {
      btn.onclick = async () => {
        const [role, pid] = (btn.getAttribute("data-sch-toggle") || "").split(":");
        const d = panel.querySelector("#crm-sch-date")?.value || meta.today;
        try {
          const r = await setSchedule({ toggle: true, role, person_id: pid, work_date: d });
          toast(r.on_duty ? "В смене" : "Снят со смены");
          await refreshMeta();
          await renderSchedule();
        } catch (err) {
          toast(String(err.message || err));
        }
      };
    });
  }

  async function renderTeam() {
    const panel = root.querySelector("#crm-panel-team");
    meta = await getMeta();
    panel.innerHTML = teamPanelHtml(meta);
    const form = panel.querySelector("#crm-team-add");
    form.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.tg_username = String(payload.tg_username || "").replace(/^@/, "");
      try {
        await upsertStaffPerson(payload);
        toast("Сохранено");
        await refreshMeta();
        await renderTeam();
      } catch (err) {
        toast(String(err.message || err));
      }
    };
    panel.querySelectorAll("[data-team-del]").forEach((btn) => {
      btn.onclick = async () => {
        const row = btn.closest(".crm-team-row");
        if (!row || !confirm("Удалить из команды?")) return;
        try {
          await deleteStaffPerson(row.dataset.role, row.dataset.id);
          toast("Удалено");
          await refreshMeta();
          await renderTeam();
        } catch (err) {
          toast(String(err.message || err));
        }
      };
    });
    panel.querySelectorAll("[data-team-edit]").forEach((btn) => {
      btn.onclick = async () => {
        const row = btn.closest(".crm-team-row");
        if (!row) return;
        const role = row.dataset.role;
        const id = row.dataset.id;
        const peopleKey = role === "surveyor" ? "surveyors" : role === "manager" ? "managers" : "lidarubs";
        const p = (meta.staff?.[peopleKey] || []).find((x) => x.id === id);
        if (!p) return;
        const name = prompt("Имя", p.name || "") ?? null;
        if (name === null) return;
        const tg = prompt("Telegram @ник (без @)", p.tg_username || "") ?? null;
        if (tg === null) return;
        const phone = prompt("Телефон", p.phone || "") ?? null;
        if (phone === null) return;
        try {
          await upsertStaffPerson({
            role,
            id,
            name: name.trim(),
            tg_username: String(tg).replace(/^@/, "").trim(),
            phone: phone.trim(),
            tg_id: p.tg_id || "",
          });
          toast("Обновлено");
          await refreshMeta();
          await renderTeam();
        } catch (err) {
          toast(String(err.message || err));
        }
      };
    });
  }

  const toggle = root.querySelector("#crm-toggle-create");
  const wrap = root.querySelector("#crm-create-wrap");

  function bindCreateForm(form) {
    if (!form) return;
    const submitCreate = async () => {
      if (!canCreateDeals()) {
        toast("Сделки создаёт лидоруб или админ");
        return;
      }
      if (!form.reportValidity()) return;
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      try {
        const obj = await createObject(payload);
        clearCreateDraft();
        toast(obj.status === "created" ? "Создано без графика" : `→ ${obj.surveyor_name}`);
        wrap.hidden = true;
        wrap.innerHTML = "";
        objects = await fetchObjects();
        paintDeals();
      } catch (err) {
        toast(String(err.message || err));
      }
    };

    // Черновик: выбор замерщика / ввод не теряются при случайном reload
    form.addEventListener("input", () => saveCreateDraft(form));
    form.addEventListener("change", () => saveCreateDraft(form));
    // Нативный submit (Enter / баг select на мобиле) не должен уводить со страницы
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
    form.querySelector("#crm-create-submit")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      submitCreate();
    });
    // Enter в полях → сохранить черновик, не «отправить форму»
    form.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "TEXTAREA") return;
      e.preventDefault();
      saveCreateDraft(form);
    });
  }

  if (toggle && wrap) {
    // Если был черновик — сразу показать форму после reload
    if (loadCreateDraft() && canCreateDeals()) {
      getMeta()
        .then((m) => {
          wrap.innerHTML = createFormHtml(m);
          wrap.hidden = false;
          bindCreateForm(wrap.querySelector("#crm-create-form"));
        })
        .catch(() => {});
    }

    toggle.onclick = async () => {
      if (!canCreateDeals()) {
        toast("Сделки создаёт лидоруб или админ");
        return;
      }
      if (!wrap.hidden && wrap.innerHTML) {
        const form = wrap.querySelector("#crm-create-form");
        if (form) saveCreateDraft(form);
        wrap.hidden = true;
        return;
      }
      const m = await getMeta();
      wrap.innerHTML = createFormHtml(m);
      wrap.hidden = false;
      bindCreateForm(wrap.querySelector("#crm-create-form"));
    };
  }

  const importToggle = root.querySelector("#crm-toggle-import");
  const importWrap = root.querySelector("#crm-import-wrap");
  if (importToggle && importWrap) {
    importToggle.onclick = () => {
      if (!canCreateDeals()) {
        toast("Сделки создаёт лидоруб или админ");
        return;
      }
      if (!importWrap.hidden && importWrap.innerHTML) {
        importWrap.hidden = true;
        return;
      }
      if (wrap) {
        wrap.hidden = true;
      }
      importWrap.innerHTML = importEstimateHtml();
      importWrap.hidden = false;
      bindImportEstimatePanel(importWrap, {
        getMeta,
        toast,
        actorRole: getCrmRole(),
        onCreated: async (obj) => {
          importWrap.hidden = true;
          importWrap.innerHTML = "";
          objects = await fetchObjects();
          paintDeals();
          onOpenDetail(obj.id);
        },
      });
    };
  }
}

function checklistHtml(obj, meta) {
  const declinedish = ["contract_declined", "manager_assigned", "manager_accepted"].includes(obj.status);
  let items = [];
  if (obj.status === "contract_signed") {
    items = meta?.checklists?.signed || [];
  } else if (declinedish) {
    items = meta?.checklists?.declined || [];
  } else if (obj.status === "closed" && Object.keys(obj.checklist || {}).length) {
    // после закрытия статус уже не хранит «заключён/не заключён» — определяем по сохранённым полям чек-листа
    items = Object.keys(obj.checklist).some((k) => ["video", "tz", "contract_scan"].includes(k))
      ? meta?.checklists?.signed || []
      : meta?.checklists?.declined || [];
  }
  if (!items.length) return "";
  const cur = obj.checklist || {};
  const up = obj.uploads || {};
  return `
  <div class="crm-checklist">
    ${items
      .map(
        (it) => `
      <label class="crm-check">
        <input type="checkbox" data-check="${esc(it.id)}" ${cur[it.id] ? "checked" : ""} />
        ${esc(it.label)}
      </label>`
      )
      .join("")}
    <label>Ссылка на фото<input data-upload="photos" value="${esc(up.photos || "")}" placeholder="https://…" /></label>
    <label>Ссылка на видео<input data-upload="video" value="${esc(up.video || "")}" placeholder="https://…" /></label>
    <label>Ссылка на ТЗ<input data-upload="tz" value="${esc(up.tz || "")}" placeholder="https://…" /></label>
    ${
      declinedish
        ? `<label>Причина отказа<textarea data-refusal rows="2">${esc(obj.refusal_reason || "")}</textarea></label>`
        : ""
    }
    <button type="button" class="btn" id="crm-save-check">Сохранить чек-лист и ссылки</button>
  </div>`;
}

function audioHtml(obj) {
  const list = obj.audio || [];
  if (!list.length) return "";
  return `<div class="crm-audio"><ul>${list
    .map((a, i) => `<li>#${i + 1} ${esc(a.name || "audio")} <span class="hint">(file_id в Telegram)</span></li>`)
    .join("")}</ul><p class="hint">Прослушать: откройте переписку с ботом или попросите админа выгрузить.</p></div>`;
}

/** Подсказка «что делать сейчас» по статусу */
function stepCopy(status) {
  const map = {
    created: {
      title: "Назначьте замерщика",
      body: "Выберите из графика или списка — потом замерщик нажмёт «Взял в работу».",
    },
    assigned: {
      title: "Ваш следующий шаг",
      body: "Подтвердите, что берёте этот замер. Остальное — после этого.",
    },
    accepted: {
      title: "Подтвердите выезд",
      body: "Когда договорились о времени с клиентом — нажмите кнопку ниже.",
    },
    visit_confirmed: {
      title: "На объекте?",
      body: "Когда приехали — отметьте и откройте конструктор замера.",
    },
    on_site: {
      title: "Замер и смета",
      body: "Считайте в конструкторе. Потом отметьте исход: заключили или нет.",
    },
    contract_signed: {
      title: "Договор есть",
      body: "Проверьте чек-лист и закройте сделку, когда всё сдано.",
    },
    contract_declined: {
      title: "Не заключили",
      body: "Передайте менеджеру на защиту ТЗ или закройте позже.",
    },
    manager_assigned: {
      title: "Менеджеру",
      body: "Возьмите сделку в работу и работайте со сметой.",
    },
    manager_accepted: {
      title: "В работе у менеджера",
      body: "Закройте исход: заключили или завершите сделку.",
    },
    closed: {
      title: "Сделка закрыта",
      body: "При необходимости можно вернуть в работу.",
    },
  };
  return map[status] || { title: "Сделка", body: "" };
}

/** Назначение замерщика: только когда реально нужно сверху; иначе — в «Ещё» */
function assignSurveyorHtml(obj, meta, { forceOpen = false } = {}) {
  const needsAssign = obj.status === "created" || !obj.surveyor_id;
  const canReassign = ["created", "assigned", "accepted", "visit_confirmed"].includes(obj.status);
  if (!canReassign) return "";
  const duty = meta?.on_duty_surveyors || [];
  const all = meta?.staff?.surveyors || [];
  const dutyIds = new Set(duty.map((s) => s.id));
  const opts = all
    .map((s) => {
      const mark = dutyIds.has(s.id) ? " · в графике" : "";
      const nick = nickOf(s);
      return `<option value="${esc(s.id)}" ${s.id === obj.surveyor_id ? "selected" : ""}>${esc(s.name)}${nick ? " " + esc(nick) : ""}${esc(mark)}</option>`;
    })
    .join("");
  const title = needsAssign ? "Назначить замерщика" : "Переназначить замерщика";
  const inner = `
    <p class="hint">Сейчас: <strong>${esc(obj.surveyor_name || "не назначен")}</strong>
      ${duty.length ? ` · в графике: ${esc(duty.map((s) => s.name).join(", "))}` : " · в графике никого"}</p>
    <button type="button" class="btn primary block" id="crm-assign-from-schedule">Из графика на сегодня</button>
    <div class="crm-assign-manual">
      <label>Из списка команды
        <select id="crm-assign-sv">
          <option value="">— выберите —</option>
          ${opts || ""}
        </select>
      </label>
      <button type="button" class="btn block" id="crm-assign-manual" ${all.length ? "" : "disabled"}>Назначить выбранного</button>
    </div>
    <details class="crm-assign-new" ${all.length ? "" : "open"}>
      <summary>+ Новый замерщик</summary>
      <div class="crm-assign-new-form">
        <label>Имя<input id="crm-new-sv-name" required placeholder="Иван" /></label>
        <div class="crm-form-row">
          <label>Телефон<input id="crm-new-sv-phone" type="tel" placeholder="+7…" /></label>
          <label>Telegram @<input id="crm-new-sv-tg" placeholder="nick" /></label>
        </div>
        <button type="button" class="btn primary block" id="crm-assign-create">Создать и назначить</button>
      </div>
    </details>`;

  if (needsAssign || forceOpen) {
    return `<section class="crm-assign-box" id="crm-assign-box"><h3>${esc(title)}</h3>${inner}</section>`;
  }
  return `<details class="crm-fold" id="crm-assign-box"><summary>${esc(title)}</summary><div class="crm-assign-box flat">${inner}</div></details>`;
}

export function detailHtml(obj, events, meta) {
  let actions = NEXT_ACTIONS[obj.status] || [];
  const step = stepCopy(obj.status);
  // На адресе рано показывать «Заключил / Не заключил» — сперва нужно посчитать
  // смету в конструкторе, иначе замерщик видит исход раньше самого замера.
  const surveyStarted = Boolean(obj.survey_local_id);
  if (obj.status === "on_site" && !surveyStarted) {
    actions = actions.filter((a) => a.action === "open_survey");
    step.body = "Откройте конструктор и посчитайте смету на месте. Кнопки «Заключил» / «Не заключил» появятся после этого.";
  }
  const needsAssign = obj.status === "created" || !obj.surveyor_id;
  // Переназначение замерщика, кабинет клиента и «исправить статус/удалить» —
  // рабочие инструменты лидоруба/менеджера/админа. Замерщику эти блоки не нужны
  // и только загромождают карточку сделки.
  const canManage = getCrmRole() !== "surveyor";
  const mgrOpts = (meta?.staff?.managers || [])
    .map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`)
    .join("");
  const statusOpts = (meta?.statuses || [])
    .map((s) => `<option value="${esc(s.id)}" ${s.id === obj.status ? "selected" : ""}>${esc(s.label)}</option>`)
    .join("");
  const showMoney =
    ["contract_signed", "contract_declined", "manager_assigned", "manager_accepted", "closed"].includes(obj.status) ||
    Number(obj.amount_total) > 0;
  const primary = actions.filter((a) => a.primary);
  const secondary = actions.filter((a) => !a.primary);
  const assignHtml = canManage ? assignSurveyorHtml(obj, meta) : "";
  const noAssignYet = needsAssign && !canManage
    ? `<section class="crm-step-card"><p class="crm-step-kicker">Замерщик не назначен</p><p class="crm-step-body">Ждите, когда лидоруб назначит замерщика на этот замер.</p></section>`
    : "";
  const audio = audioHtml(obj);
  const checklist = checklistHtml(obj, meta);

  return `
  <header class="topbar">
    <div class="brand">
      <strong>${esc(obj.title || "Сделка")}</strong>
      <span>${statusPill(obj)}</span>
    </div>
    <button type="button" class="btn ghost" id="crm-back">← К списку</button>
  </header>

  <section class="crm-deal-hero">
    <div class="crm-deal-line"><span>Адрес</span><b>${esc(obj.address || "—")}</b></div>
    <div class="crm-deal-line"><span>Замер</span><b>${esc(obj.measure_date || "—")}</b></div>
    <div class="crm-deal-line"><span>Клиент</span><b>${esc(obj.client_name || "—")}${obj.client_phone ? " · " + esc(obj.client_phone) : ""}</b></div>
    <div class="crm-deal-line"><span>Замерщик</span><b>${esc(obj.surveyor_name || "не назначен")}</b></div>
  </section>

  ${needsAssign ? (canManage ? assignHtml : noAssignYet) : ""}

  ${
    !needsAssign && (primary.length || step.body)
      ? `<section class="crm-step-card">
    <p class="crm-step-kicker">${esc(step.title)}</p>
    <p class="crm-step-body">${esc(step.body)}</p>
    <div class="crm-step-actions">
      ${primary
        .map((a) => `<button type="button" class="btn primary block" data-crm-act="${esc(a.action)}">${esc(a.label)}</button>`)
        .join("")}
      ${secondary
        .map((a) => {
          const cls = a.danger ? "btn danger block" : "btn ghost block";
          return `<button type="button" class="${cls}" data-crm-act="${esc(a.action)}">${esc(a.label)}</button>`;
        })
        .join("")}
    </div>
    ${
      obj.status === "contract_declined" || obj.status === "manager_assigned"
        ? `<label class="crm-mgr">Менеджер<select id="crm-mgr">${mgrOpts}</select></label>`
        : ""
    }
  </section>`
      : ""
  }

  ${
    showMoney
      ? `<details class="crm-fold" ${Number(obj.amount_total) > 0 ? "" : "open"}>
    <summary>Сумма и скидка${Number(obj.amount_total) > 0 ? ` · ${esc(moneyFmt(obj.amount_total))}` : ""}</summary>
    <section class="crm-money-box">
      <p class="hint">После сметы. Попадает в аналитику и ЗП.</p>
      <div class="crm-form-row">
        <label>Сумма до скидки, ₽<input id="crm-money-sub" type="number" min="0" step="100" value="${esc(obj.amount_subtotal || "")}" /></label>
        <label>Скидка, %<input id="crm-money-disc" type="number" min="0" max="100" step="0.5" value="${esc(obj.discount_pct || 0)}" /></label>
      </div>
      <div class="crm-form-row">
        <label>Итого, ₽<input id="crm-money-total" type="number" min="0" step="100" value="${esc(obj.amount_total || "")}" readonly /></label>
        <label>Площадь, м²<input id="crm-money-area" type="number" min="0" step="0.1" value="${esc(obj.area_m2 || "")}" /></label>
      </div>
      <button type="button" class="btn primary" id="crm-save-money">Сохранить</button>
    </section>
  </details>`
      : ""
  }

  ${audio ? `<details class="crm-fold"><summary>Аудио Лидоруба</summary>${audio}</details>` : ""}
  ${checklist ? `<details class="crm-fold"><summary>Чек-лист</summary>${checklist}</details>` : ""}

  ${
    canManage
      ? `<details class="crm-fold" id="crm-cabinet-fold">
    <summary>Кабинет клиента</summary>
    <section class="crm-money-box" id="crm-cabinet-box">
      <p class="hint">Ссылка клиенту после сметы. Вход по телефону, правки в логе.</p>
      <div id="crm-cabinet-info" class="hint">Загрузка…</div>
      <div class="crm-actions" style="margin-top:10px">
        <button type="button" class="btn primary" id="crm-cab-open">Открыть / обновить</button>
        <button type="button" class="btn ghost" id="crm-cab-copy" hidden>Копировать ссылку</button>
        <button type="button" class="btn ghost" id="crm-cab-revoke" hidden>Отозвать</button>
      </div>
      <ul class="crm-events" id="crm-cabinet-logs" style="margin-top:12px"></ul>
    </section>
  </details>`
      : ""
  }

  <details class="crm-fold">
    <summary>Подробности</summary>
    <section class="crm-detail">
      <p><strong>Квалификация:</strong> ${esc(obj.qualification || "—")}</p>
      <p><strong>Менеджер:</strong> ${esc(obj.manager_name || "—")}</p>
      <p><strong>Лидоруб:</strong> ${esc(obj.lidarub_name || obj.ledorub_name || "—")}</p>
      ${obj.deal_source === "import_estimate" ? `<p><strong>Источник:</strong> импорт готовой сметы (см. «История»)</p>` : ""}
      ${obj.survey_local_id ? `<p><strong>Локальный замер:</strong> ${esc(obj.survey_local_id)}</p>` : ""}
      ${obj.escalated_at ? `<p class="crm-escalated">Эскалация (${fmtTs(obj.escalated_at)})</p>` : ""}
    </section>
  </details>

  ${!needsAssign && canManage ? assignHtml : ""}

  <details class="crm-fold">
    <summary>История</summary>
    <ul class="crm-events">
      ${(events || [])
        .map((e) => `<li><span class="hint">${fmtTs(e.created_at)}</span> ${esc(e.message)}</li>`)
        .join("") || "<li class='hint'>Пока пусто</li>"}
    </ul>
  </details>

  ${
    canManage
      ? `<details class="crm-admin">
    <summary>Исправить статус / удалить</summary>
    <p class="hint">Если нажали не ту кнопку — выберите статус.</p>
    <label>Статус вручную
      <select id="crm-set-status">${statusOpts}</select>
    </label>
    <div class="crm-actions">
      <button type="button" class="btn" id="crm-apply-status">Сменить статус</button>
      <button type="button" class="btn" data-crm-act="reopen">Вернуть в работу</button>
      <button type="button" class="btn danger" data-crm-act="delete">Удалить сделку</button>
    </div>
  </details>`
      : ""
  }

  <p class="footer-note"><a href="/bestpaints/logout">Выйти</a></p>`;
}


export async function mountDetail(ctx) {
  const { root, objectId, toast, onBack, onOpenSurvey, getMeta } = ctx;
  root.innerHTML = `<p style="color:#9aada2;padding:24px">Загрузка CRM…</p>`;
  let meta;
  let pack;
  try {
    meta = await getMeta();
    pack = await fetchObject(objectId);
  } catch (e) {
    root.innerHTML = `<p class="callout danger">${esc(e.message)}</p><button class="btn" id="crm-back">Назад</button>`;
    root.querySelector("#crm-back").onclick = onBack;
    return;
  }
  const obj = pack.object;
  root.innerHTML = detailHtml(obj, pack.events, meta);
  root.querySelector("#crm-back").onclick = onBack;

  const refresh = () => mountDetail(ctx);

  // Кабинет клиента
  let cabLink = "";
  async function loadCabinetBox() {
    const info = root.querySelector("#crm-cabinet-info");
    const logsEl = root.querySelector("#crm-cabinet-logs");
    const copyBtn = root.querySelector("#crm-cab-copy");
    const revokeBtn = root.querySelector("#crm-cab-revoke");
    if (!info) return;
    try {
      const pack = await api(`/objects/${encodeURIComponent(objectId)}/cabinet`);
      const cab = pack.cabinet;
      if (!cab) {
        info.textContent = "Кабинет ещё не открыт. Нужны смета в конструкторе и телефон клиента.";
        if (copyBtn) copyBtn.hidden = true;
        if (revokeBtn) revokeBtn.hidden = true;
        if (logsEl) logsEl.innerHTML = "";
        return;
      }
      info.innerHTML = `<strong>${esc(cab.client_name || "Клиент")}</strong> · ${esc(cab.client_phone)}
        · статус ${esc(cab.status)} · код <b>${esc(cab.access_code || "—")}</b>
        <div class="hint" style="margin-top:6px">Клиент входит по ссылке + телефону или телефону + коду.</div>
        ${cabLink ? `<div style="margin-top:8px"><a href="${esc(cabLink)}" target="_blank" rel="noopener">${esc(cabLink)}</a></div>` : ""}`;
      if (copyBtn) copyBtn.hidden = false;
      if (revokeBtn) revokeBtn.hidden = cab.status !== "active";
      // cabLink сохраняем из последнего open/refresh
      if (logsEl) {
        logsEl.innerHTML = (pack.logs || [])
          .slice(0, 40)
          .map((e) => `<li><span class="hint">${fmtTs(e.created_at)}</span> <b>${esc(e.actor_type)}</b> · ${esc(e.message)}</li>`)
          .join("") || "<li class='hint'>Лог пуст</li>";
      }
    } catch (e) {
      info.textContent = String(e.message || e);
    }
  }
  loadCabinetBox();

  root.querySelector("#crm-cab-open")?.addEventListener("click", async () => {
    // Нужен survey из localStorage по survey_local_id или через callback
    const sid = obj.survey_local_id;
    let survey = null;
    try {
      const raw = localStorage.getItem("bp_surveys_v1");
      const list = raw ? JSON.parse(raw) : [];
      survey = list.find((s) => s.id === sid) || null;
    } catch { /* ignore */ }
    if (!survey) {
      // если кабинет уже есть — обновим ссылку с серверной сметы
      try {
        const existing = await api(`/objects/${encodeURIComponent(objectId)}/cabinet`);
        if (existing.cabinet) {
          const refreshed = await api(`/cabinets/${encodeURIComponent(existing.cabinet.id)}/refresh-link`, {
            method: "POST",
            body: "{}",
          });
          cabLink = refreshed.link || "";
          toast("Ссылка обновлена из серверной сметы");
          const info = root.querySelector("#crm-cabinet-info");
          if (info) {
            info.innerHTML = `<strong>Ссылка:</strong> <a href="${esc(cabLink)}" target="_blank" rel="noopener">${esc(cabLink)}</a>
              <div>Код: <b>${esc(refreshed.access_code || "")}</b></div>`;
          }
          root.querySelector("#crm-cab-copy").hidden = false;
          await loadCabinetBox();
          return;
        }
      } catch { /* fallthrough */ }
      toast("Откройте конструктор по этой сделке, сохраните смету — затем снова «Открыть / обновить»");
      return;
    }
    try {
      // snapshot totals if possible — client sends raw survey; server stores slim
      const res = await api(`/objects/${encodeURIComponent(objectId)}/cabinet`, {
        method: "POST",
        body: JSON.stringify({ survey, created_from: "crm", actor_id: getCrmRole() }),
      });
      cabLink = res.link || "";
      toast("Кабинет готов");
      const info = root.querySelector("#crm-cabinet-info");
      if (info) {
        info.innerHTML = `<strong>Ссылка:</strong> <a href="${esc(cabLink)}" target="_blank" rel="noopener">${esc(cabLink)}</a>
          <div>Код доступа: <b>${esc(res.access_code || "")}</b> · тел. ${esc(res.phone || "")}</div>`;
      }
      root.querySelector("#crm-cab-copy").hidden = false;
      root.querySelector("#crm-cab-revoke").hidden = false;
      await loadCabinetBox();
      if (cabLink) {
        // keep link visible
        const info2 = root.querySelector("#crm-cabinet-info");
        if (info2) info2.innerHTML += `<div style="margin-top:8px"><a href="${esc(cabLink)}" target="_blank">${esc(cabLink)}</a></div>`;
      }
    } catch (e) {
      toast(String(e.message || e));
    }
  });
  root.querySelector("#crm-cab-copy")?.addEventListener("click", async () => {
    if (!cabLink) {
      toast("Сначала нажмите «Открыть / обновить кабинет» чтобы получить свежую ссылку");
      return;
    }
    try {
      await navigator.clipboard.writeText(cabLink);
      toast("Ссылка скопирована");
    } catch {
      prompt("Ссылка:", cabLink);
    }
  });
  root.querySelector("#crm-cab-revoke")?.addEventListener("click", async () => {
    try {
      const pack = await api(`/objects/${encodeURIComponent(objectId)}/cabinet`);
      if (!pack.cabinet) return;
      await api(`/cabinets/${encodeURIComponent(pack.cabinet.id)}/revoke`, { method: "POST", body: "{}" });
      toast("Кабинет отозван");
      cabLink = "";
      await loadCabinetBox();
    } catch (e) {
      toast(String(e.message || e));
    }
  });


  const subEl = root.querySelector("#crm-money-sub");
  const discEl = root.querySelector("#crm-money-disc");
  const totEl = root.querySelector("#crm-money-total");
  const recalc = () => {
    const sub = Number(subEl?.value || 0);
    const disc = Number(discEl?.value || 0);
    if (totEl) totEl.value = String(Math.round(sub * (1 - disc / 100)));
  };
  subEl?.addEventListener("input", recalc);
  discEl?.addEventListener("input", recalc);
  root.querySelector("#crm-save-money")?.addEventListener("click", async () => {
    try {
      await doAction(objectId, "save_money", {
        amount_subtotal: Number(subEl?.value || 0),
        discount_pct: Number(discEl?.value || 0),
        area_m2: Number(root.querySelector("#crm-money-area")?.value || 0),
      });
      toast("Сумма сохранена");
      await refresh();
    } catch (err) {
      toast(String(err.message || err));
    }
  });

  async function runAction(action, extra = {}) {
    if (action === "open_survey") {
      onOpenSurvey(obj);
      return;
    }
    if (action === "delete") {
      if (!confirm("Удалить сделку из списка? (можно не восстановить без админа)")) return;
    }
    if (action === "reopen") {
      extra.status = extra.status || "accepted";
    }
    if (action === "assign_manager") {
      const sel = root.querySelector("#crm-mgr");
      if (sel) extra.manager_id = sel.value;
    }
    if (action === "decline_on_site") {
      const reason = prompt("Кратко: почему не заключили?") || "";
      extra.refusal_reason = reason;
    }
    try {
      await doAction(objectId, action, extra);
      toast("Обновлено");
      if (action === "delete") onBack();
      else await refresh();
    } catch (err) {
      toast(String(err.message || err));
    }
  }

  root.querySelector("#crm-assign-from-schedule")?.addEventListener("click", () => {
    runAction("reassign_surveyor", {});
  });
  root.querySelector("#crm-assign-manual")?.addEventListener("click", () => {
    const sid = root.querySelector("#crm-assign-sv")?.value;
    if (!sid) {
      toast("Выберите замерщика из списка");
      return;
    }
    runAction("reassign_surveyor", { surveyor_id: sid });
  });
  root.querySelector("#crm-assign-create")?.addEventListener("click", async () => {
    const name = (root.querySelector("#crm-new-sv-name")?.value || "").trim();
    const phone = (root.querySelector("#crm-new-sv-phone")?.value || "").trim();
    const tg = String(root.querySelector("#crm-new-sv-tg")?.value || "")
      .replace(/^@/, "")
      .trim();
    if (!name) {
      toast("Укажите имя замерщика");
      return;
    }
    try {
      const staff = await upsertStaffPerson({
        role: "surveyor",
        name,
        phone,
        tg_username: tg,
      });
      const people = staff.surveyors || [];
      const person =
        staff.person ||
        people.find((p) => (p.name || "").trim() === name && (!tg || (p.tg_username || "") === tg)) ||
        people.find((p) => (p.name || "").trim() === name) ||
        people[people.length - 1];
      if (!person?.id) {
        toast("Создали в команде, но не нашли id — назначьте из списка");
        await refresh();
        return;
      }
      await doAction(objectId, "reassign_surveyor", { surveyor_id: person.id });
      toast(`Назначен ${person.name}`);
      await refresh();
    } catch (err) {
      toast(String(err.message || err));
    }
  });

  root.querySelectorAll("[data-crm-act]").forEach((btn) => {
    btn.onclick = () => runAction(btn.getAttribute("data-crm-act"));
  });

  root.querySelector("#crm-apply-status")?.addEventListener("click", async () => {
    const st = root.querySelector("#crm-set-status")?.value;
    await runAction("set_status", { status: st });
  });

  const saveCheck = root.querySelector("#crm-save-check");
  if (saveCheck) {
    saveCheck.onclick = async () => {
      const checklist = {};
      root.querySelectorAll("[data-check]").forEach((inp) => {
        checklist[inp.getAttribute("data-check")] = !!inp.checked;
      });
      const uploads = {};
      root.querySelectorAll("[data-upload]").forEach((inp) => {
        uploads[inp.getAttribute("data-upload")] = inp.value.trim();
      });
      const refusal = root.querySelector("[data-refusal]")?.value || "";
      try {
        await doAction(objectId, "save_checklist", { checklist, uploads, refusal_reason: refusal });
        toast("Чек-лист сохранён");
        await refresh();
      } catch (err) {
        toast(String(err.message || err));
      }
    };
  }
}

export { NEXT_ACTIONS };
