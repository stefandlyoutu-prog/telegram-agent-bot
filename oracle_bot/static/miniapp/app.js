const tg = window.Telegram?.WebApp;
let botUsername = "MOracul_bot";
let botLink = "https://t.me/MOracul_bot";
let busy = false;

if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor("#0f0e14");
  tg.setBackgroundColor("#0f0e14");
}

function uid() {
  return tg?.initDataUnsafe?.user?.id || new URLSearchParams(location.search).get("uid");
}

function initData() {
  return tg?.initData || "";
}

async function waitForUid(ms = 2500) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    const id = uid();
    if (id) return id;
    await new Promise((r) => setTimeout(r, 80));
  }
  return uid();
}

async function api(path, opts = {}) {
  const id = await waitForUid();
  const url = id ? `${path}?user_id=${id}` : path;
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function haptic() {
  try {
    tg?.HapticFeedback?.impactOccurred("light");
  } catch (_) {}
}

function toast(text) {
  try {
    if (tg?.showAlert) {
      tg.showAlert(text);
      return;
    }
  } catch (_) {}
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2200);
}

function openBotDeepLink(start) {
  const url = start ? `${botLink}?start=${encodeURIComponent(start)}` : botLink;
  if (tg?.openTelegramLink) {
    tg.openTelegramLink(url);
    return;
  }
  if (tg?.openLink) {
    tg.openLink(url);
    return;
  }
  window.location.href = url;
}

function closeSoon(ms = 450) {
  setTimeout(() => {
    try {
      tg?.close();
    } catch (_) {}
  }, ms);
}

async function triggerAction(payload) {
  if (busy) return;
  busy = true;
  haptic();

  const data = initData();
  if (data) {
    try {
      const r = await fetch("/api/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: data, ...payload }),
      });
      if (r.ok) {
        toast("Готово — смотри ответ в чате с ботом");
        closeSoon(500);
        busy = false;
        return;
      }
    } catch (e) {
      console.warn("api/action", e);
    }
  }

  const action = payload.action;
  if (action === "mod" && payload.module) {
    openBotDeepLink(`mod_${payload.module}`);
  } else if (action === "premium") {
    openBotDeepLink("premium");
  } else if (action === "ref") {
    openBotDeepLink("ref");
  } else if (action === "voice") {
    openBotDeepLink("voice");
  } else {
    openBotDeepLink("");
  }
  toast("Открываю чат с ботом…");
  closeSoon(700);
  busy = false;
}

function openMod(mod) {
  if (!mod) return;
  triggerAction({ action: "mod", module: mod });
}

function openAction(action) {
  if (!action) return;
  triggerAction({ action });
}

function renderModules(modules, sections) {
  const root = document.getElementById("moduleSections");
  if (!root || !modules?.length) return;

  const order = ["top", "popular", "deep"];
  const bySection = {};
  modules.forEach((m) => {
    (bySection[m.section] ||= []).push(m);
  });

  root.innerHTML = order
    .filter((s) => bySection[s]?.length)
    .map((section) => {
      const label = sections?.[section] || section;
      const cards = bySection[section]
        .map(
          (m) => `
        <button type="button" class="mod" data-mod="${m.id}">
          <span class="mod-emoji">${m.emoji || ""}</span>
          <span class="mod-body">
            <span class="mod-title">${m.title}</span>
            <span class="mod-desc">${m.desc}</span>
          </span>
        </button>`
        )
        .join("");
      return `
        <section class="mod-section">
          <p class="label">${label}</p>
          <div class="grid">${cards}</div>
        </section>`;
    })
    .join("");
}

function bindUi() {
  document.querySelector(".app")?.addEventListener("click", (e) => {
    const modBtn = e.target.closest("[data-mod]");
    if (modBtn?.dataset.mod) {
      e.preventDefault();
      openMod(modBtn.dataset.mod);
      return;
    }
    const actionBtn = e.target.closest("[data-action]");
    if (actionBtn?.dataset.action) {
      e.preventDefault();
      openAction(actionBtn.dataset.action);
    }
  });

  document.getElementById("cardDay")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openMod("card_day");
    }
  });

  document.querySelectorAll("#topics button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      haptic();
      const topic = btn.dataset.topic;
      const userId = Number(await waitForUid());
      if (!userId) {
        toast("Открой приложение из @MOracul_bot");
        return;
      }
      try {
        await api("/api/topic", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic, user_id: userId }),
        });
        document.querySelectorAll("#topics button").forEach((b) =>
          b.classList.toggle("active", b === btn)
        );
      } catch (e) {
        console.warn(e);
      }
    });
  });
}

async function load() {
  try {
    const data = await api("/api/home");
    document.getElementById("greeting").textContent = data.greeting || "Привет";
    document.getElementById("subtitle").textContent = data.subtitle || "";
    document.getElementById("streak").textContent = data.streak ?? 0;
    document.getElementById("credits").textContent = data.credits ?? 0;
    document.getElementById("used").textContent = data.used_today ?? 0;
    document.getElementById("cardTitle").textContent = data.card?.title || "—";
    document.getElementById("cardHint").textContent = data.card?.hint || "";
    botUsername = data.bot || botUsername;
    botLink = data.bot_link || `https://t.me/${botUsername}`;
    renderModules(data.modules, data.sections);
    document.querySelectorAll("#topics button").forEach((b) => {
      b.classList.toggle("active", b.dataset.topic === (data.topic || ""));
    });
  } catch (e) {
    console.warn(e);
    document.getElementById("subtitle").textContent =
      "Нажми раздел — ответ придёт в чат с ботом";
    try {
      const cat = await fetch("/api/catalog").then((r) => r.json());
      botUsername = cat.bot || botUsername;
      botLink = cat.bot_link || botLink;
      renderModules(cat.modules, cat.sections);
    } catch (_) {
      renderModules([], {});
    }
  }
}

bindUi();
load();
