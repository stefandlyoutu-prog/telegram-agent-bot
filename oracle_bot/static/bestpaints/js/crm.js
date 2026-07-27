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
    return `<div class="empty crm-empty">Нет сделок. Лидоруб создаёт в Telegram (/zamer) или кнопкой ниже.</div>`;
  }
  return `<div class="crm-list">${objects
    .map(
      (o) => `
    <article class="crm-item">
      <div class="crm-item-main">
        <h3>${esc(o.title)} ${statusPill(o)}</h3>
        <p>${esc(o.address || "Адрес не указан")}
          · ${esc(o.client_name || "Клиент")}
          ${o.surveyor_name ? ` · ${esc(o.surveyor_name)}` : ""}
          ${o.measure_date ? ` · замер ${esc(o.measure_date)}` : ""}
          ${o.escalated_at ? ` · <span class="crm-escalated">эскалация</span>` : ""}
        </p>
      </div>
      <div class="survey-actions">
        <button type="button" class="btn" data-crm-open="${esc(o.id)}">Открыть</button>
      </div>
    </article>`
    )
    .join("")}</div>`;
}

export function createFormHtml(meta) {
  const surv = (meta?.staff?.surveyors || [])
    .map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`)
    .join("");
  const today = meta?.today || "";
  const duty = (meta?.on_duty_surveyors || []).map((s) => s.name).join(", ") || "никого — заполните график";
  return `
  <form class="crm-create" id="crm-create-form">
    <h3>Новая сделка (как у Лидоруба)</h3>
    <p class="hint">Сегодня в графике замерщиков: <strong>${esc(duty)}</strong></p>
    <label>Название сделки<input name="title" required placeholder="Как в вашей CRM" /></label>
    <label>Квалификация (комментарий)<textarea name="qualification" rows="2" placeholder="Что обсудили с клиентом"></textarea></label>
    <label>Адрес объекта<input name="address" required placeholder="Адрес" /></label>
    <label>Дата замера<input name="measure_date" type="date" value="${esc(today)}" /></label>
    <label>Клиент<input name="client_name" placeholder="ФИО" /></label>
    <label>Телефон клиента<input name="client_phone" type="tel" placeholder="+7…" /></label>
    <label>Лидоруб (имя)<input name="lidarub_name" placeholder="Ваше имя" /></label>
    <label>Телефон Лидоруба<input name="lidarub_phone" type="tel" placeholder="+7… (эскалация)" /></label>
    <label>Замерщик (пусто = из графика)
      <select name="surveyor_id">
        <option value="">Из графика / зоны</option>
        ${surv}
      </select>
    </label>
    <button type="submit" class="btn primary block">Создать сделку</button>
  </form>`;
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

export function schedulePanelHtml(meta) {
  const today = meta?.today || "";
  const items = meta?.schedule_today || [];
  const surv = (meta?.on_duty_surveyors || []).map((s) => s.name).join(", ") || "никого";
  const mgr = (meta?.on_duty_managers || []).map((m) => m.name).join(", ") || "никого";
  const list =
    items
      .map((r) => `<li>${esc(r.role)}: <strong>${esc(r.person_name || r.person_id)}</strong></li>`)
      .join("") || "<li class='hint'>Пусто — сделки не назначатся</li>";
  return `
  <section class="crm-schedule" id="crm-schedule">
    <div class="crm-board-head">
      <h2 class="subhead">График смен · ${esc(today)}</h2>
    </div>
    <p class="hint">Замерщики: <strong>${esc(surv)}</strong> · Менеджеры: <strong>${esc(mgr)}</strong></p>
    <ul class="crm-schedule-list">${list}</ul>
    <div class="crm-schedule-actions">
      <label>Дата <input type="date" id="crm-sch-date" value="${esc(today)}" /></label>
      <button type="button" class="btn primary" id="crm-sch-fill">Поставить всех в график</button>
      <button type="button" class="btn ghost" id="crm-sch-clear">Очистить день</button>
      <button type="button" class="btn ghost" id="crm-sch-reload">Обновить</button>
    </div>
    <p class="hint">То же в боте: <code>/grafik_fill</code> · без графика /zamer оставит сделку «Создана»</p>
  </section>`;
}

export function homeCrmSectionHtml(objects) {
  return `
  <section class="crm-board">
    <div class="crm-board-head">
      <h2 class="subhead">CRM · сделки замеров</h2>
      <button type="button" class="btn primary" id="crm-toggle-create">+ Сделка</button>
    </div>
    <p class="hint crm-board-hint">Лидоруб: Telegram /zamer · График ниже или /grafik_fill · статусы здесь</p>
    <div id="crm-schedule-host"></div>
    <div id="crm-create-wrap" class="crm-create-wrap" hidden></div>
    ${boardHtml(objects)}
  </section>`;
}

export async function mountHomeCrm(ctx) {
  const { root, toast, onOpenDetail, getMeta } = ctx;
  let objects = [];
  let meta = null;
  try {
    objects = await fetchObjects();
    meta = await getMeta();
  } catch (e) {
    const el = root.querySelector(".crm-board");
    if (el) {
      el.insertAdjacentHTML(
        "beforeend",
        `<div class="callout danger">CRM недоступен: ${esc(e.message)}. Работает только локальный замер.</div>`
      );
    }
    return;
  }
  const listHost = root.querySelector(".crm-board");
  if (!listHost) return;

  const schHost = root.querySelector("#crm-schedule-host");
  if (schHost) {
    schHost.innerHTML = schedulePanelHtml(meta);
    const reloadSch = async () => {
      const day = root.querySelector("#crm-sch-date")?.value || meta.today;
      const pack = await fetchSchedule(day);
      const fakeMeta = {
        ...meta,
        today: day,
        schedule_today: pack.items || [],
        on_duty_surveyors: pack.on_duty_surveyors || [],
        on_duty_managers: pack.on_duty_managers || [],
      };
      schHost.innerHTML = schedulePanelHtml(fakeMeta);
      bindSch();
    };
    const bindSch = () => {
      root.querySelector("#crm-sch-reload")?.addEventListener("click", () => reloadSch().catch((e) => toast(String(e.message || e))));
      root.querySelector("#crm-sch-fill")?.addEventListener("click", async () => {
        const day = root.querySelector("#crm-sch-date")?.value || meta.today;
        try {
          await setSchedule({ fill_all: true, work_date: day });
          toast(`График на ${day} заполнен`);
          await reloadSch();
        } catch (err) {
          toast(String(err.message || err));
        }
      });
      root.querySelector("#crm-sch-clear")?.addEventListener("click", async () => {
        const day = root.querySelector("#crm-sch-date")?.value || meta.today;
        if (!confirm(`Очистить график на ${day}?`)) return;
        try {
          await setSchedule({ clear: true, work_date: day });
          toast(`График ${day} очищен`);
          await reloadSch();
        } catch (err) {
          toast(String(err.message || err));
        }
      });
      root.querySelector("#crm-sch-date")?.addEventListener("change", () => reloadSch().catch((e) => toast(String(e.message || e))));
    };
    bindSch();
  }

  const oldList = listHost.querySelector(".crm-list, .crm-empty");
  const tmp = document.createElement("div");
  tmp.innerHTML = boardHtml(objects);
  if (oldList) oldList.replaceWith(...tmp.childNodes);
  else listHost.append(...tmp.childNodes);

  root.querySelectorAll("[data-crm-open]").forEach((btn) => {
    btn.onclick = (ev) => {
      ev.preventDefault();
      onOpenDetail(btn.getAttribute("data-crm-open"));
    };
  });

  const toggle = root.querySelector("#crm-toggle-create");
  const wrap = root.querySelector("#crm-create-wrap");
  if (toggle && wrap) {
    toggle.onclick = async () => {
      if (wrap.innerHTML && !wrap.hidden) {
        wrap.hidden = true;
        return;
      }
      const m = await getMeta();
      wrap.innerHTML = createFormHtml(m);
      wrap.hidden = false;
      const form = wrap.querySelector("#crm-create-form");
      form.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const payload = Object.fromEntries(fd.entries());
        try {
          const obj = await createObject(payload);
          if (obj.status === "created") {
            toast("Создано, но график пуст — назначьте замерщика");
          } else {
            toast(`Создано → ${obj.surveyor_name || "замерщик"}`);
          }
          wrap.hidden = true;
          wrap.innerHTML = "";
          await mountHomeCrm(ctx);
        } catch (err) {
          toast(String(err.message || err));
        }
      };
    };
  }
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
