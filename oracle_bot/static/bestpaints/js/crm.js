/** BestPaints CRM — сделки Лидоруба, статусы, чек-листы, график. */

const API = "/bestpaints/api";

async function api(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
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
    const msg = (data && (data.detail || data.message)) || res.statusText || "Ошибка API";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
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
  created: [
    { action: "reassign_surveyor", label: "Назначить из графика", primary: true },
  ],
  assigned: [{ action: "accept", label: "Взял в работу", primary: true }],
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

export function createFormHtml(meta) {
  const surv = (meta?.staff?.surveyors || [])
    .map((s) => `<option value="${esc(s.id)}">${esc(s.name)}${nickOf(s) ? " " + nickOf(s) : ""}</option>`)
    .join("");
  const today = meta?.today || "";
  const duty = (meta?.on_duty_surveyors || []).map((s) => s.name).join(", ") || "никого в графике";
  return `
  <form class="crm-create" id="crm-create-form">
    <h3>Новая сделка</h3>
    <p class="hint">Сегодня на смене: ${esc(duty)}</p>
    <label>Название<input name="title" required placeholder="Как в CRM" /></label>
    <label>Квалификация<textarea name="qualification" rows="2" placeholder="Кратко"></textarea></label>
    <label>Адрес<input name="address" required /></label>
    <label>Дата замера<input name="measure_date" type="date" value="${esc(today)}" /></label>
    <div class="crm-form-row">
      <label>Клиент<input name="client_name" /></label>
      <label>Телефон<input name="client_phone" type="tel" /></label>
    </div>
    <label>Замерщик
      <select name="surveyor_id">
        <option value="">Авто из графика</option>
        ${surv}
      </select>
    </label>
    <button type="submit" class="btn primary block">Создать</button>
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
  return `
  <section class="crm-shell" id="crm-shell">
    <nav class="crm-tabs" role="tablist">
      <button type="button" class="crm-tab active" data-tab="deals">Сделки</button>
      <button type="button" class="crm-tab" data-tab="analytics">Аналитика</button>
      <button type="button" class="crm-tab" data-tab="schedule">График</button>
      <button type="button" class="crm-tab" data-tab="team">Команда</button>
    </nav>
    <div class="crm-tab-panels">
      <div class="crm-tab-panel" id="crm-panel-deals" data-panel="deals">
        <div class="crm-panel-head">
          <div>
            <h3>Сделки</h3>
            <p class="hint" id="crm-duty-hint">Загрузка графика…</p>
          </div>
          <button type="button" class="btn primary" id="crm-toggle-create">+ Сделка</button>
        </div>
        <div id="crm-create-wrap" class="crm-create-wrap" hidden></div>
        <div id="crm-deals-list"></div>
      </div>
      <div class="crm-tab-panel" id="crm-panel-analytics" data-panel="analytics" hidden></div>
      <div class="crm-tab-panel" id="crm-panel-schedule" data-panel="schedule" hidden></div>
      <div class="crm-tab-panel" id="crm-panel-team" data-panel="team" hidden></div>
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
        <p class="hint">${esc(data.from || "…")} → ${esc(data.to || "…")}</p>
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
      <div class="an-hero-card win">
        <span>Заключено</span>
        <strong>${esc(moneyFmt(k.signed_sum))}</strong>
        <em>${esc(String(k.signed || 0))} сделок</em>
      </div>
      <div class="an-hero-card work">
        <span>В работе</span>
        <strong>${esc(moneyFmt(k.in_work_sum))}</strong>
        <em>${esc(String(k.in_work || 0))} сделок</em>
      </div>
      <div class="an-hero-card lose">
        <span>Не заключено</span>
        <strong>${esc(moneyFmt(k.declined_sum))}</strong>
        <em>${esc(String(k.declined || 0))} сделок</em>
      </div>
    </div>
    <div class="an-kpis">
      <div class="an-kpi"><span>Конверсия</span><strong>${esc(String(k.conversion_pct || 0))}%</strong></div>
      <div class="an-kpi"><span>Средний чек</span><strong>${esc(moneyFmt(k.avg_check))}</strong></div>
      <div class="an-kpi"><span>Ср. скидка</span><strong>${esc(String(k.avg_discount_pct || 0))}%</strong></div>
      <div class="an-kpi"><span>Скидки, ₽</span><strong>${esc(moneyFmt(k.discount_rub))}</strong></div>
      <div class="an-kpi"><span>Замеров</span><strong>${esc(String(k.measures || 0))}</strong></div>
      <div class="an-kpi"><span>Площадь</span><strong>${esc(String(k.area_m2 || 0))} м²</strong></div>
    </div>
    ${(k.without_amount || 0) > 0 ? `<p class="hint an-warn">Без суммы в CRM: ${esc(String(k.without_amount))} — укажите в карточке сделки.</p>` : ""}
    <div class="an-block">
      <div class="crm-chip-label">Воронка за период</div>
      <div class="an-funnel">
        ${(data.funnel || [])
          .filter((f) => f.count > 0)
          .map(
            (f) => `
          <div class="an-funnel-row">
            <span>${esc(f.label)}</span>
            <div class="an-bar"><i style="width:${Math.round((100 * f.count) / maxFunnel)}%;background:${esc(f.color)}"></i></div>
            <b>${esc(String(f.count))}</b>
          </div>`
          )
          .join("") || "<p class='hint'>Нет сделок за период</p>"}
      </div>
    </div>
    <div class="an-block">
      <div class="crm-chip-label">По замерщикам</div>
      <div class="an-people">
        ${(data.by_surveyor || [])
          .map(
            (p) => `
          <div class="an-person">
            <strong>${esc(p.name)}</strong>
            <span>${esc(String(p.deals))} сделок · ✅ ${esc(String(p.signed))} · ✕ ${esc(String(p.declined))}</span>
            <em>${esc(moneyFmt(p.sum_signed))} заключено</em>
          </div>`
          )
          .join("") || "<p class='hint'>Пока пусто</p>"}
      </div>
    </div>
    ${
      (data.top_signed || []).length
        ? `<div class="an-block">
      <div class="crm-chip-label">Топ договоров</div>
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
    </div>`
        : ""
    }
  </div>`;
}

export async function mountHomeCrm(ctx) {
  const { root, toast, onOpenDetail, getMeta } = ctx;
  const shell = root.querySelector("#crm-shell");
  if (!shell) return;

  let meta;
  let objects;
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
  if (listEl) listEl.innerHTML = boardHtml(objects);

  root.querySelectorAll("[data-crm-open]").forEach((btn) => {
    btn.onclick = (ev) => {
      ev.preventDefault();
      onOpenDetail(btn.getAttribute("data-crm-open"));
    };
  });

  // tabs
  const showTab = (name) => {
    root.querySelectorAll(".crm-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
    root.querySelectorAll(".crm-tab-panel").forEach((p) => {
      p.hidden = p.dataset.panel !== name;
    });
  };
  root.querySelectorAll(".crm-tab").forEach((tab) => {
    tab.onclick = async () => {
      showTab(tab.dataset.tab);
      if (tab.dataset.tab === "schedule") await renderSchedule();
      if (tab.dataset.tab === "team") await renderTeam();
      if (tab.dataset.tab === "analytics") await renderAnalytics("30d");
    };
  });

  async function refreshMeta() {
    meta = await getMeta();
    const d = (meta.on_duty_surveyors || []).map((s) => s.name).join(", ") || "никого — откройте «График»";
    if (dutyEl) dutyEl.textContent = `На смене сегодня: ${d}`;
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
  if (toggle && wrap) {
    toggle.onclick = async () => {
      if (!wrap.hidden && wrap.innerHTML) {
        wrap.hidden = true;
        return;
      }
      const m = await getMeta();
      wrap.innerHTML = createFormHtml(m);
      wrap.hidden = false;
      wrap.querySelector("#crm-create-form").onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = Object.fromEntries(fd.entries());
        try {
          const obj = await createObject(payload);
          toast(obj.status === "created" ? "Создано без графика" : `→ ${obj.surveyor_name}`);
          wrap.hidden = true;
          wrap.innerHTML = "";
          objects = await fetchObjects();
          if (listEl) listEl.innerHTML = boardHtml(objects);
          root.querySelectorAll("[data-crm-open]").forEach((btn) => {
            btn.onclick = (ev) => {
              ev.preventDefault();
              onOpenDetail(btn.getAttribute("data-crm-open"));
            };
          });
        } catch (err) {
          toast(String(err.message || err));
        }
      };
    };
  }
}

function checklistHtml(obj, meta) {
  const signedish = ["contract_signed", "closed"].includes(obj.status);
  const declinedish = ["contract_declined", "manager_assigned", "manager_accepted"].includes(obj.status);
  let items = [];
  if (obj.status === "contract_signed" || (signedish && obj.status !== "closed" && !declinedish)) {
    items = meta?.checklists?.signed || [];
  } else if (declinedish || obj.status === "contract_signed") {
    items = obj.status === "contract_signed" ? meta?.checklists?.signed || [] : meta?.checklists?.declined || [];
  }
  if (obj.status === "contract_signed") items = meta?.checklists?.signed || [];
  if (declinedish) items = meta?.checklists?.declined || [];
  if (obj.status === "closed" && Object.keys(obj.checklist || {}).length) {
    items = Object.keys(obj.checklist).some((k) => ["video", "tz", "contract_scan"].includes(k))
      ? meta?.checklists?.signed || []
      : meta?.checklists?.declined || [];
  }
  if (!items.length) return "";
  const cur = obj.checklist || {};
  const up = obj.uploads || {};
  return `
  <div class="crm-checklist">
    <h3>Чек-лист</h3>
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
  return `<div class="crm-audio"><h3>Аудио от Лидоруба</h3><ul>${list
    .map((a, i) => `<li>#${i + 1} ${esc(a.name || "audio")} <span class="hint">(file_id в Telegram)</span></li>`)
    .join("")}</ul><p class="hint">Прослушать: откройте переписку с ботом или попросите админа выгрузить.</p></div>`;
}

export function detailHtml(obj, events, meta) {
  const actions = NEXT_ACTIONS[obj.status] || [];
  const mgrOpts = (meta?.staff?.managers || [])
    .map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`)
    .join("");
  const statusOpts = (meta?.statuses || [])
    .map((s) => `<option value="${esc(s.id)}" ${s.id === obj.status ? "selected" : ""}>${esc(s.label)}</option>`)
    .join("");
  return `
  <header class="topbar">
    <div class="brand">
      <strong>Сделка · ${esc(obj.title)}</strong>
      <span>${statusPill(obj)}</span>
    </div>
    <button type="button" class="btn ghost" id="crm-back">← К списку</button>
  </header>
  <section class="hero-card crm-detail">
    <p><strong>Адрес:</strong> ${esc(obj.address)}</p>
    <p><strong>Дата замера:</strong> ${esc(obj.measure_date || "—")}</p>
    <p><strong>Квалификация:</strong> ${esc(obj.qualification || "—")}</p>
    <p><strong>Клиент:</strong> ${esc(obj.client_name)} ${esc(obj.client_phone)}</p>
    <p><strong>Замерщик:</strong> ${esc(obj.surveyor_name || "—")} ${esc(obj.surveyor_phone || "")}</p>
    <p><strong>Менеджер:</strong> ${esc(obj.manager_name || "—")}</p>
    <p><strong>Лидоруб:</strong> ${esc(obj.lidarub_name || obj.ledorub_name || "—")}</p>
    ${obj.survey_local_id ? `<p><strong>Локальный замер:</strong> ${esc(obj.survey_local_id)}</p>` : ""}
    ${obj.escalated_at ? `<p class="crm-escalated">Эскалация: замерщик не взял вовремя (${fmtTs(obj.escalated_at)})</p>` : ""}
  </section>
  <section class="crm-money-box">
    <h3>Сумма и скидка</h3>
    <p class="hint">Попадает в аналитику. После сметы в конструкторе внесите итог сюда.</p>
    <div class="crm-form-row">
      <label>Сумма до скидки, ₽<input id="crm-money-sub" type="number" min="0" step="100" value="${esc(obj.amount_subtotal || "")}" /></label>
      <label>Скидка, %<input id="crm-money-disc" type="number" min="0" max="100" step="0.5" value="${esc(obj.discount_pct || 0)}" /></label>
    </div>
    <div class="crm-form-row">
      <label>Итого, ₽<input id="crm-money-total" type="number" min="0" step="100" value="${esc(obj.amount_total || "")}" readonly /></label>
      <label>Площадь, м²<input id="crm-money-area" type="number" min="0" step="0.1" value="${esc(obj.area_m2 || "")}" /></label>
    </div>
    <button type="button" class="btn primary" id="crm-save-money">Сохранить в аналитику</button>
  </section>
  ${audioHtml(obj)}
  <div class="crm-actions">
    ${actions
      .map((a) => {
        const cls = a.primary ? "btn primary" : a.danger ? "btn danger" : "btn ghost";
        return `<button type="button" class="${cls}" data-crm-act="${esc(a.action)}">${esc(a.label)}</button>`;
      })
      .join("")}
  </div>
  ${
    obj.status === "contract_declined" || obj.status === "manager_assigned"
      ? `<label class="crm-mgr">Менеджер<select id="crm-mgr">${mgrOpts}</select></label>`
      : ""
  }
  ${checklistHtml(obj, meta)}

  <details class="crm-admin" open>
    <summary>Исправить статус / удалить</summary>
    <p class="hint">Если нажали не ту кнопку — выберите статус и сохраните. Удаление скрывает сделку из списка.</p>
    <label>Статус вручную
      <select id="crm-set-status">${statusOpts}</select>
    </label>
    <div class="crm-actions">
      <button type="button" class="btn" id="crm-apply-status">Сменить статус</button>
      <button type="button" class="btn" data-crm-act="reopen">Вернуть в работу</button>
      <button type="button" class="btn danger" data-crm-act="delete">Удалить сделку</button>
    </div>
  </details>

  <h2 class="subhead">История</h2>
  <ul class="crm-events">
    ${(events || [])
      .map((e) => `<li><span class="hint">${fmtTs(e.created_at)}</span> ${esc(e.message)}</li>`)
      .join("") || "<li class='hint'>Пока пусто</li>"}
  </ul>
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
