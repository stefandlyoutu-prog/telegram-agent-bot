let state = { data: null, spheres: null, chart: null, filter: "all", query: "", channel: "all", activeSphere: null, authRequired: false };

function apiHeaders(extra = {}) {
  const h = { ...extra };
  const token = sessionStorage.getItem("dashboard_token");
  if (token) h["X-Dashboard-Token"] = token;
  return h;
}

async function apiFetch(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: apiHeaders(opts.headers || {}),
  });
  if (res.status === 401 && state.authRequired) {
    const token = prompt("Токен дашборда (MONEY_DASHBOARD_TOKEN):");
    if (token) {
      sessionStorage.setItem("dashboard_token", token);
      return apiFetch(url, opts);
    }
  }
  return res;
}

const fmtRub = (n) =>
  new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(n || 0);

const fmtTime = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};

const TIER_LABELS = { flagship: "флагман", watch: "осторожно" };
const CLUSTER_LABELS = {
  platform: "подписки", data: "данные", b2b: "B2B", marketplace: "биржа",
  content: "контент", referral: "рефералки", product: "продукт",
};
const CHANNEL_LABELS = { online: "онлайн", physical: "физика", meta: "мета" };
const SOLUTION_LABELS = { bot: "бот", site: "сайт", chat: "чат", referral: "CPA" };
const PIPE_LABELS = {
  proposed: "предложено", needs_user: "ждёт вас", launching: "запуск",
  launched: "запущено", scout: "скан", scored: "оценка", rejected: "отказ",
};

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function channelTag(ch) {
  if (!ch || ch === "meta") return "";
  return `<span class="channel-tag channel-tag--${ch}">${CHANNEL_LABELS[ch] || ch}</span>`;
}

function matchesFilter(idea) {
  if (state.channel !== "all" && idea.channel !== state.channel) return false;
  const q = state.query.toLowerCase();
  if (q) {
    const hay = `${idea.title} ${idea.category} ${idea.note} ${idea.action_required}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  const f = state.filter;
  if (f === "all") return true;
  if (f === "flagship") return idea.tier === "flagship";
  if (f === "online" || f === "physical") return idea.channel === f;
  return idea.cluster === f;
}

function tierBadge(tier) {
  if (!tier || tier === "strong") return "";
  return `<span class="tier tier--${tier}">${TIER_LABELS[tier] || tier}</span>`;
}

function compactCard(idea) {
  const el = document.createElement("div");
  el.className = "card" + (idea.tier === "flagship" ? " card--flagship" : "");
  el.dataset.slug = idea.slug;
  if (!matchesFilter(idea)) el.classList.add("card--hidden");

  const sub = CLUSTER_LABELS[idea.cluster] || idea.category;
  const right =
    idea.status === "running"
      ? `<div class="card__money">${fmtRub(idea.revenue_today)}</div>`
      : idea.tier === "flagship"
        ? `<span class="card__tag">★</span>`
        : `<span class="card__sub">${idea.expected_daily_rub || 0}₽/д</span>`;

  el.innerHTML = `
    <div class="card__main">
      <div class="card__title">${idea.status === "running" ? '<span class="live-dot"></span>' : ""}${escapeHtml(idea.title)}${channelTag(idea.channel)}</div>
      <div class="card__sub">${escapeHtml(sub)}${idea.user_needed ? ' <span class="user-needed">· нужен вы</span>' : " · авто"}</div>
    </div>
    <div class="card__right">${right}</div>
  `;
  return el;
}

function fillPanel(id, items, emptyText) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  const visible = items.filter(matchesFilter);
  if (!visible.length) {
    el.innerHTML = `<p class="empty">${emptyText}</p>`;
    return;
  }
  visible.forEach((idea) => el.appendChild(compactCard(idea)));
}

function renderMoneyBar(m) {
  document.getElementById("m-target").textContent = fmtRub(m.target_today);
  document.getElementById("m-actual").textContent = fmtRub(m.actual_today);
  const gapEl = document.getElementById("m-gap");
  gapEl.textContent = (m.gap > 0 ? "−" : "+") + fmtRub(Math.abs(m.gap));
  gapEl.parentElement.className = "money-cell" + (m.gap > 0 ? " gap-bad" : m.gap < 0 ? " gap-good" : "");
  document.getElementById("m-potential").textContent = fmtRub(m.potential_if_launch_online);
}

function renderTodayPlan(plan) {
  const el = document.getElementById("today-plan");
  el.innerHTML = "";
  if (!plan.length) {
    el.innerHTML = '<span class="today-strip__hint">Клик по идее → «В план на сегодня»</span>';
    return;
  }
  plan.forEach((p) => {
    const chip = document.createElement("div");
    chip.className = "plan-chip";
    chip.innerHTML = `<span>${escapeHtml(p.title || p.slug)}</span><span class="plan-chip__exp">${fmtRub(p.expected_rub)}</span>`;
    chip.dataset.slug = p.slug;
    chip.title = p.promotion || "";
    el.appendChild(chip);
  });
  document.getElementById("plan-hint").textContent = `Цель: ${fmtRub(plan.reduce((s, p) => s + (p.expected_rub || 0), 0))} · ${plan.length} проект(ов)`;
}

function renderAssets(assets, doneCount) {
  const grid = document.getElementById("assets-grid");
  document.getElementById("assets-done").textContent = `${doneCount}/${assets.length}`;
  grid.innerHTML = assets
    .map(
      (a) =>
        `<button type="button" class="asset-chip${a.done ? " asset-chip--done" : ""}" data-asset="${a.asset_key}" title="${escapeHtml(a.hint)}">${a.done ? "✓ " : ""}${escapeHtml(a.label)}</button>`
    )
    .join("");
}

function renderChannels(channels) {
  const grid = document.getElementById("channels-grid");
  const cnt = document.getElementById("channels-count");
  if (!grid) return;
  cnt.textContent = channels.length;
  if (!channels.length) {
    grid.innerHTML = '<p class="channels__hint">Пока нет каналов — добавь @username после назначения бота админом</p>';
    return;
  }
  grid.innerHTML = channels
    .map((c) => {
      const st = c.ready
        ? "✓ бот может постить"
        : c.bot_admin
          ? "админ, нет права поста"
          : "ждём @MOracul_bot админом";
      const yz =
        c.yandex_status === "moderation"
          ? " · Яндекс: модерация"
          : c.yandex_status === "active"
            ? " · Яндекс ✓"
            : "";
      return `<div class="channel-card${c.ready ? " channel-card--ready" : ""}">
        <div class="channel-card__title"><a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">@${escapeHtml(c.username)}</a></div>
        <div class="channel-card__meta">${escapeHtml(c.title || "—")} · ${escapeHtml(st)}${yz}</div>
        <div class="channel-card__actions">
          <button type="button" class="btn btn--sm btn--primary" data-ch-post="${escapeHtml(c.username)}" ${c.can_post ? "" : "disabled"}>Воронка → бот</button>
          <button type="button" class="btn btn--sm" data-ch-sync="${escapeHtml(c.username)}">↻</button>
        </div>
      </div>`;
    })
    .join("");
}

async function addChannel(username) {
  const u = username.trim();
  if (!u) return;
  await apiFetch("/api/tg-channels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: u }),
  });
  await load();
}

async function syncChannels() {
  await apiFetch("/api/tg-channels/sync", { method: "POST" });
  await load();
}

async function postFunnel(username) {
  await apiFetch(`/api/tg-channels/${username}/post`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template: "funnel", pin: false }),
  });
  alert("Пост отправлен в @" + username);
  await load();
}

function renderScout(opps, pipeline) {
  document.getElementById("scout-count").textContent = opps.length;
  const pipe = document.getElementById("scout-pipeline");
  pipe.innerHTML = Object.entries(pipeline)
    .filter(([k]) => k !== "total")
    .map(([k, v]) => `<span class="pipe-step">${PIPE_LABELS[k] || k}: ${v}</span>`)
    .join("");
  const list = document.getElementById("scout-list");
  const show = opps.filter((o) => !["launched", "rejected"].includes(o.pipeline_stage)).slice(0, 12);
  if (!show.length) {
    list.innerHTML = '<p class="empty">Нажми «Обновить тренды»</p>';
    return;
  }
  list.innerHTML = show
    .map(
      (o) => `
    <div class="opp" data-opp="${o.slug}">
      <span class="opp__q">${escapeHtml(o.query_text)}</span>
      <span class="opp__meta">${SOLUTION_LABELS[o.solution_type] || o.solution_type}</span>
      <span class="opp__exp">~${o.expected_daily_rub || 0}₽</span>
    </div>`
    )
    .join("");
}

function renderBlockers(blockers) {
  const sec = document.getElementById("blockers-section");
  const el = document.getElementById("blockers-list");
  document.getElementById("blockers-count").textContent = blockers.length;
  if (!blockers.length) {
    sec.classList.add("blockers--hidden");
    return;
  }
  sec.classList.remove("blockers--hidden");
  el.innerHTML = blockers
    .map(
      (b) => `
    <div class="blocker">
      <span class="blocker__text">${escapeHtml(b.description)}${b.title ? ` (${escapeHtml(b.title)})` : ""}</span>
      <button class="btn btn--primary" data-action="blocker-done" data-id="${b.id}">Готово</button>
    </div>`
    )
    .join("");
}

function renderChart(history) {
  const el = document.getElementById("chart");
  if (!history.length) {
    el.innerHTML = '<p class="empty">Закрой первый день — появится график</p>';
    return;
  }
  const max = Math.max(...history.flatMap((h) => [h.expected_total, h.actual_total]), 1);
  el.innerHTML = history
    .map((h) => {
      const d = h.hist_date.slice(5);
      const eh = Math.round((h.expected_total / max) * 56);
      const ah = Math.round((h.actual_total / max) * 56);
      return `<div class="chart__col">
        <div class="chart__bars">
          <div class="chart__bar chart__bar--exp" style="height:${eh}px" title="план"></div>
          <div class="chart__bar chart__bar--act" style="height:${ah}px" title="факт"></div>
        </div>
        <span class="chart__lbl">${d}</span>
      </div>`;
    })
    .join("");
}

function renderSpheres() {
  const grid = document.getElementById("spheres-grid");
  grid.innerHTML = "";
  if (!state.spheres) return;
  state.spheres.forEach((sp) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sphere" + (state.activeSphere === sp.id ? " sphere--active" : "");
    btn.dataset.sphere = sp.id;
    btn.innerHTML = `<span class="sphere__emoji">${sp.emoji}</span><span class="sphere__name">${escapeHtml(sp.title)}</span><span class="sphere__cnt">${sp.ideas_count}</span>`;
    grid.appendChild(btn);
  });
}

function showSphereDetail(sphereId) {
  state.activeSphere = sphereId;
  renderSpheres();
  const sp = state.spheres.find((s) => s.id === sphereId);
  const box = document.getElementById("sphere-detail");
  if (!sp) return;
  box.innerHTML = `
    <div class="sphere-detail__title">${sp.emoji} ${escapeHtml(sp.title)}</div>
    <div class="sphere-detail__angle">${escapeHtml(sp.business_angle)}</div>
    <ul class="sphere-detail__list">${sp.ideas.map((i) => `<li data-slug="${i.slug}">${escapeHtml(i.title)}</li>`).join("")}</ul>
  `;
}

function openModal(slug) {
  const idea = state.data.all.find((i) => i.slug === slug);
  if (!idea) return;
  const inPlan = state.data.today_plan.some((p) => p.slug === slug);
  let actions = "";
  if (idea.status === "needs_action")
    actions += `<button class="btn btn--primary" data-action="status" data-slug="${slug}" data-status="connected">Подключить</button>`;
  if (idea.status === "connected")
    actions += `<button class="btn btn--live" data-action="status" data-slug="${slug}" data-status="running">Запустить</button>`;
  if (idea.status === "running") {
    actions += `<button class="btn btn--primary" data-action="revenue" data-slug="${slug}">+ доход</button>`;
    actions += `<button class="btn" data-action="status" data-slug="${slug}" data-status="connected">Пауза</button>`;
  }
  if (idea.channel === "online" && !inPlan)
    actions += `<button class="btn btn--gold" data-action="add-plan" data-slug="${slug}">В план на сегодня</button>`;

  document.getElementById("modal-content").innerHTML = `
    <h3>${escapeHtml(idea.title)}${tierBadge(idea.tier)} ${channelTag(idea.channel)}</h3>
    <div class="modal__meta">${escapeHtml(idea.category)} · ожид. ${fmtRub(idea.expected_daily_rub)}/день · авто ${idea.automation_pct}%</div>
    <div class="modal__block"><strong>Ваш шаг:</strong> ${escapeHtml(idea.effective_action || idea.action_required || "—")}</div>
    ${idea.missing_assets?.length ? `<div class="modal__block modal__block--note">Один раз: ${idea.missing_assets.join(", ")} — отметь в «Сделал один раз»</div>` : ""}
    ${idea.note ? `<div class="modal__block"><strong>Потенциал:</strong> ${escapeHtml(idea.potential_rub || "—")}</div>` : ""}
    <div class="modal__actions">${actions}</div>
  `;
  document.getElementById("idea-modal").showModal();
}

function openOppModal(slug) {
  const opp = state.data.opportunities.find((o) => o.slug === slug);
  if (!opp) return;
  document.getElementById("modal-content").innerHTML = `
    <h3>🔍 ${escapeHtml(opp.query_text)}</h3>
    <div class="modal__meta">${escapeHtml(opp.source)} · ${SOLUTION_LABELS[opp.solution_type]} · спрос ${opp.volume_score}/100</div>
    <div class="modal__block modal__block--note">${escapeHtml(opp.proposal).replace(/\n/g, "<br>")}</div>
    <div class="modal__actions">
      <button class="btn btn--primary" data-action="opp-launch" data-slug="${slug}">В реестр → ждёт вас</button>
      <button class="btn" data-action="opp-reject" data-slug="${slug}">Отклонить</button>
    </div>
  `;
  document.getElementById("idea-modal").showModal();
}

function showReport(report) {
  document.getElementById("report-content").innerHTML = `
    <h3>Отчёт за ${escapeHtml(report.report_date)}</h3>
    <div class="modal__meta">План ${fmtRub(report.expected_total)} → факт ${fmtRub(report.actual_total)} · разрыв ${fmtRub(report.gap_rub)}</div>
    <div class="report-block"><h4>Почему не та сумма</h4>${escapeHtml(report.gap_reason)}</div>
    <div class="report-block"><h4>Что изменить</h4>${escapeHtml(report.suggestions)}</div>
    <div class="report-block"><h4>Действия на завтра</h4>${escapeHtml(report.next_actions)}</div>
  `;
  document.getElementById("report-modal").showModal();
}

function renderAll() {
  if (!state.data) return;
  const d = state.data;
  const m = d.metrics;
  document.getElementById("header-date").textContent = new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  renderMoneyBar(m);
  renderTodayPlan(d.today_plan);
  renderAssets(d.user_assets, d.assets_done_count);
  renderChannels(d.tg_channels || []);
  renderScout(d.opportunities, d.pipeline);
  renderBlockers(d.blockers);
  document.getElementById("count-connected").textContent = d.totals.connected_count;
  document.getElementById("count-running").textContent = d.totals.running_count;
  document.getElementById("count-pending").textContent = d.totals.pending_count;

  fillPanel("list-connected", d.connected, "Пока ничего не подключено");
  fillPanel("list-running", d.running, "Нет активных потоков");
  const flagships = d.needs_action.filter((i) => i.tier === "flagship");
  const fr = document.getElementById("flagship-row");
  fr.innerHTML = "";
  flagships.filter(matchesFilter).forEach((i) => fr.appendChild(compactCard(i)));
  fillPanel("list-pending", d.needs_action.filter((i) => i.tier !== "flagship"), "Онлайн-идеи — фильтр 🌐 Онлайн");
  if (state.chart) renderChart(state.chart);
}

async function load() {
  try {
    const cfgR = await apiFetch("/api/config");
    if (cfgR.ok) {
      const cfg = await cfgR.json();
      state.authRequired = !!cfg.auth_required;
    }
    const ch = state.channel !== "all" ? `?channel=${state.channel}` : "";
    const [dashR, sphR, chartR] = await Promise.all([
      apiFetch(`/api/dashboard${ch}`),
      apiFetch("/api/spheres"),
      apiFetch("/api/chart"),
    ]);
    if (!dashR.ok) throw new Error(`dashboard ${dashR.status}`);
    const [dash, sph, chart] = await Promise.all([dashR.json(), sphR.json(), chartR.json()]);
    state.data = dash;
    state.spheres = sph.spheres || [];
    state.chart = chart.history || [];
    renderAll();
    renderSpheres();
    if (state.activeSphere) showSphereDetail(state.activeSphere);
  } catch (err) {
    console.error("load failed", err);
    const bar = document.getElementById("money-bar");
    if (bar && !document.getElementById("load-error")) {
      const el = document.createElement("div");
      el.id = "load-error";
      el.className = "today-strip__hint";
      el.style.color = "#fb7185";
      el.textContent = "Ошибка загрузки — проверьте, что сервер запущен";
      bar.after(el);
    }
  }
}

async function setStatus(slug, status) {
  await apiFetch(`/api/ideas/${slug}/status`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
  document.getElementById("idea-modal").close();
  await load();
}

async function addRevenue(slug) {
  const raw = prompt("Сумма (₽):");
  if (!raw) return;
  const amount = parseFloat(raw.replace(",", "."));
  if (!amount || amount <= 0) return;
  await apiFetch(`/api/ideas/${slug}/revenue`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ amount, note: "" }) });
  document.getElementById("idea-modal").close();
  await load();
}

async function addToPlan(slug) {
  const promo = prompt("Где продвигаешь? (VK, TikTok…)", "") || "";
  await apiFetch(`/api/today/plan/${slug}?promotion=${encodeURIComponent(promo)}`, { method: "POST" });
  document.getElementById("idea-modal").close();
  await load();
}

async function closeDay() {
  const note = prompt("Заметка к отчёту (необязательно):", "") || "";
  const r = await apiFetch("/api/today/close", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }) });
  const report = await r.json();
  showReport(report);
  await load();
}

async function blockerDone(id) {
  await apiFetch(`/api/blockers/${id}/done`, { method: "POST" });
  await load();
}

document.getElementById("search").addEventListener("input", (e) => {
  state.query = e.target.value.trim();
  renderAll();
});

document.getElementById("filters").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  document.querySelectorAll(".chip").forEach((c) => c.classList.remove("chip--active"));
  chip.classList.add("chip--active");
  const f = chip.dataset.filter;
  state.filter = f;
  if (f === "online" || f === "physical") state.channel = f;
  else state.channel = "all";
  load();
});

document.getElementById("btn-close-day").addEventListener("click", closeDay);
document.getElementById("modal-close").addEventListener("click", () => document.getElementById("idea-modal").close());
document.getElementById("report-close").addEventListener("click", () => document.getElementById("report-modal").close());

async function toggleAsset(key, done) {
  await apiFetch(`/api/assets/${key}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ done }),
  });
  await load();
}

async function launchOpp(slug) {
  await apiFetch(`/api/scout/${slug}/launch`, { method: "POST" });
  document.getElementById("idea-modal").close();
  await load();
}

async function rejectOpp(slug) {
  await apiFetch(`/api/scout/${slug}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage: "rejected" }),
  });
  document.getElementById("idea-modal").close();
  await load();
}

async function scanTrends() {
  await apiFetch("/api/scout/scan", { method: "POST" });
  await load();
}

document.getElementById("btn-scout-scan").addEventListener("click", scanTrends);

const chForm = document.getElementById("channels-add-form");
if (chForm) {
  chForm.addEventListener("submit", (e) => {
    e.preventDefault();
    addChannel(document.getElementById("channel-username").value);
    document.getElementById("channel-username").value = "";
  });
}
document.getElementById("btn-channels-sync")?.addEventListener("click", syncChannels);

document.getElementById("assets-grid").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-asset]");
  if (!chip) return;
  const key = chip.dataset.asset;
  const done = !chip.classList.contains("asset-chip--done");
  toggleAsset(key, done);
});

document.addEventListener("click", (e) => {
  const opp = e.target.closest(".opp");
  if (opp?.dataset.opp) { openOppModal(opp.dataset.opp); return; }
  const card = e.target.closest(".card:not(.card--hidden)");
  if (card?.dataset.slug) { openModal(card.dataset.slug); return; }
  const sphereBtn = e.target.closest(".sphere");
  if (sphereBtn) { showSphereDetail(sphereBtn.dataset.sphere); return; }
  const li = e.target.closest(".sphere-detail__list li");
  if (li?.dataset.slug) { openModal(li.dataset.slug); return; }
  const chPost = e.target.closest("[data-ch-post]");
  if (chPost) { postFunnel(chPost.dataset.chPost); return; }
  const chSync = e.target.closest("[data-ch-sync]");
  if (chSync) {
    apiFetch(`/api/tg-channels/${chSync.dataset.chSync}/sync`, { method: "POST" }).then(load);
    return;
  }
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const { action, slug, status, id } = btn.dataset;
  if (action === "status") setStatus(slug, status);
  if (action === "revenue") addRevenue(slug);
  if (action === "add-plan") addToPlan(slug);
  if (action === "blocker-done") blockerDone(id);
  if (action === "opp-launch") launchOpp(slug);
  if (action === "opp-reject") rejectOpp(slug);
});

load();
setInterval(load, 20000);
