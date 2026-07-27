/** BestPaints CRM — серверные объекты, статусы, чек-листы. */

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

const NEXT_ACTIONS = {
  assigned: [{ action: "accept", label: "Взял в работу", primary: true }],
  accepted: [{ action: "confirm_visit", label: "Выезд подтверждён", primary: true }],
  visit_confirmed: [{ action: "arrive", label: "На объекте", primary: true }],
  on_site: [
    { action: "estimate_done", label: "Смета готова", primary: true },
    { action: "open_survey", label: "Открыть конструктор", ghost: true },
  ],
  estimate_done: [
    { action: "sign_contract", label: "Договор подписан", primary: true },
    { action: "decline_contract", label: "Не заключён", danger: true },
    { action: "open_survey", label: "Конструктор / смета", ghost: true },
  ],
  contract_signed: [
    { action: "close", label: "Закрыть объект", primary: true },
  ],
  contract_declined: [
    { action: "assign_manager", label: "Назначить менеджера", primary: true },
  ],
  manager_assigned: [
    { action: "manager_accept", label: "Менеджер взял в работу", primary: true },
  ],
  manager_accepted: [
    { action: "close", label: "Закрыть", primary: true },
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
    return `<div class="empty crm-empty">Нет серверных объектов CRM. Создайте объект — замерщик получит SMS (если настроено).</div>`;
  }
  return `<div class="crm-list">${objects
    .map(
      (o) => `
    <article class="crm-item" data-crm-open="${esc(o.id)}">
      <div class="crm-item-main">
        <h3>${esc(o.title)} ${statusPill(o)}</h3>
        <p>${esc(o.address || "Адрес не указан")}
          · ${esc(o.client_name || "Клиент")}
          ${o.surveyor_name ? ` · ${esc(o.surveyor_name)}` : ""}
          ${o.escalated_at ? ` · <span class="crm-escalated">эскалация</span>` : ""}
        </p>
      </div>
      <button type="button" class="btn" data-crm-open="${esc(o.id)}">Открыть</button>
    </article>`
    )
    .join("")}</div>`;
}

export function createFormHtml(meta) {
  const surv = (meta?.staff?.surveyors || [])
    .map((s) => `<option value="${esc(s.id)}">${esc(s.name)} (${esc(s.note || s.phone || "")})</option>`)
    .join("");
  return `
  <form class="crm-create" id="crm-create-form">
    <h3>Новый объект CRM</h3>
    <p class="hint">Ледоруб создаёт объект → замерщик назначается по адресу → SMS.</p>
    <label>Название / объект<input name="title" required placeholder="Дом Ивановых" /></label>
    <label>Адрес<input name="address" required placeholder="Серебрянка, ул. …" /></label>
    <label>Клиент<input name="client_name" placeholder="ФИО" /></label>
    <label>Телефон клиента<input name="client_phone" type="tel" placeholder="+7…" /></label>
    <label>Ледоруб (имя)<input name="ledorub_name" placeholder="Ваше имя" /></label>
    <label>Телефон ледоруба (для эскалации)<input name="ledorub_phone" type="tel" placeholder="+7…" /></label>
    <label>Замерщик (или авто по адресу)
      <select name="surveyor_id">
        <option value="">Авто по адресу</option>
        ${surv}
      </select>
    </label>
    <button type="submit" class="btn primary block">Создать и назначить</button>
  </form>`;
}

function checklistHtml(obj, meta) {
  const signed = obj.status === "contract_signed" || obj.status === "closed";
  const declined =
    obj.status === "contract_declined" ||
    obj.status === "manager_assigned" ||
    obj.status === "manager_accepted";
  let items = [];
  if (signed || obj.status === "contract_signed") items = meta?.checklists?.signed || [];
  else if (declined) items = meta?.checklists?.declined || [];
  else return "";
  const cur = obj.checklist || {};
  if (!items.length) return "";
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
    <button type="button" class="btn" id="crm-save-check">Сохранить чек-лист</button>
  </div>`;
}

export function detailHtml(obj, events, meta) {
  const actions = NEXT_ACTIONS[obj.status] || [];
  const mgrOpts = (meta?.staff?.managers || [])
    .map((m) => `<option value="${esc(m.id)}">${esc(m.name)}</option>`)
    .join("");
  return `
  <header class="topbar">
    <div class="brand">
      <strong>CRM · ${esc(obj.title)}</strong>
      <span>${statusPill(obj)}</span>
    </div>
    <button type="button" class="btn ghost" id="crm-back">← К списку</button>
  </header>
  <section class="hero-card crm-detail">
    <p><strong>Адрес:</strong> ${esc(obj.address)}</p>
    <p><strong>Клиент:</strong> ${esc(obj.client_name)} ${esc(obj.client_phone)}</p>
    <p><strong>Замерщик:</strong> ${esc(obj.surveyor_name || "—")} ${esc(obj.surveyor_phone || "")}</p>
    <p><strong>Менеджер:</strong> ${esc(obj.manager_name || "—")}</p>
    <p><strong>Ледоруб:</strong> ${esc(obj.ledorub_name || "—")}</p>
    ${obj.survey_local_id ? `<p><strong>Локальный замер:</strong> ${esc(obj.survey_local_id)}</p>` : ""}
    ${obj.escalated_at ? `<p class="crm-escalated">Эскалация: замерщик не взял вовремя (${fmtTs(obj.escalated_at)})</p>` : ""}
  </section>
  <div class="crm-actions">
    ${actions
      .map((a) => {
        const cls = a.primary ? "btn primary" : a.danger ? "btn danger" : "btn ghost";
        return `<button type="button" class="${cls}" data-crm-act="${esc(a.action)}">${esc(a.label)}</button>`;
      })
      .join("")}
  </div>
  ${
    obj.status === "contract_declined"
      ? `<label class="crm-mgr">Менеджер<select id="crm-mgr">${mgrOpts}</select></label>`
      : ""
  }
  ${checklistHtml(obj, meta)}
  <h2 class="subhead">История</h2>
  <ul class="crm-events">
    ${(events || [])
      .map((e) => `<li><span class="hint">${fmtTs(e.created_at)}</span> ${esc(e.message)}</li>`)
      .join("") || "<li class='hint'>Пока пусто</li>"}
  </ul>
  <p class="footer-note"><a href="/bestpaints/logout">Выйти</a></p>`;
}

export function homeCrmSectionHtml(objects) {
  return `
  <section class="crm-board">
    <div class="crm-board-head">
      <h2 class="subhead">CRM · воронка замеров</h2>
      <button type="button" class="btn primary" id="crm-toggle-create">+ Объект CRM</button>
    </div>
    <div id="crm-create-wrap" class="crm-create-wrap" hidden></div>
    ${boardHtml(objects)}
  </section>`;
}

/**
 * Bind home CRM: load objects, create form, open detail.
 * @param {{ root: HTMLElement, toast: Function, onOpenDetail: (id:string)=>void, getMeta: ()=>Promise<any> }} ctx
 */
export async function mountHomeCrm(ctx) {
  const { root, toast, onOpenDetail, getMeta } = ctx;
  let objects = [];
  try {
    objects = await fetchObjects();
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
  // refresh list part
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
      const hide = wrap.hasAttribute("hidden") === false && wrap.innerHTML;
      if (wrap.innerHTML && !wrap.hidden) {
        wrap.hidden = true;
        return;
      }
      const meta = await getMeta();
      wrap.innerHTML = createFormHtml(meta);
      wrap.hidden = false;
      const form = wrap.querySelector("#crm-create-form");
      form.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const payload = Object.fromEntries(fd.entries());
        try {
          const obj = await createObject(payload);
          toast(`Создан: ${obj.title} → ${obj.surveyor_name || "без замерщика"}`);
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

  root.querySelectorAll("[data-crm-act]").forEach((btn) => {
    btn.onclick = async () => {
      const action = btn.getAttribute("data-crm-act");
      if (action === "open_survey") {
        onOpenSurvey(obj);
        return;
      }
      const extra = {};
      if (action === "assign_manager") {
        const sel = root.querySelector("#crm-mgr");
        if (sel) extra.manager_id = sel.value;
      }
      if (action === "estimate_done" && obj.survey_local_id) {
        extra.survey_local_id = obj.survey_local_id;
      }
      try {
        await doAction(objectId, action, extra);
        toast("Статус обновлён");
        await refresh();
      } catch (err) {
        toast(String(err.message || err));
      }
    };
  });

  const saveCheck = root.querySelector("#crm-save-check");
  if (saveCheck) {
    saveCheck.onclick = async () => {
      const checklist = {};
      root.querySelectorAll("[data-check]").forEach((inp) => {
        checklist[inp.getAttribute("data-check")] = !!inp.checked;
      });
      try {
        await doAction(objectId, "save_checklist", { checklist });
        toast("Чек-лист сохранён");
        await refresh();
      } catch (err) {
        toast(String(err.message || err));
      }
    };
  }
}

export { NEXT_ACTIONS };
