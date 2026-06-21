const tg = window.Telegram?.WebApp;
let botUsername = "MOracul_bot";
let botLink = "https://t.me/MOracul_bot";

if (tg) {
  tg.ready();
  tg.expand();
  tg.enableClosingConfirmation();
  tg.setHeaderColor("#0f0e14");
  tg.setBackgroundColor("#0f0e14");
}

function uid() {
  return tg?.initDataUnsafe?.user?.id || new URLSearchParams(location.search).get("uid");
}

async function api(path, opts = {}) {
  const id = uid();
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

function openMod(mod) {
  haptic();
  const payload = JSON.stringify({ action: "mod", module: mod });
  if (tg?.sendData) {
    tg.sendData(payload);
    setTimeout(() => tg.close?.(), 400);
    return;
  }
  window.location.href = `${botLink}?start=mod_${mod}`;
}

function openAction(action) {
  haptic();
  const payload = JSON.stringify({ action });
  if (tg?.sendData) {
    tg.sendData(payload);
    setTimeout(() => tg.close?.(), 400);
    return;
  }
  window.location.href = botLink;
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

  root.querySelectorAll(".mod").forEach((btn) => {
    btn.addEventListener("click", () => openMod(btn.dataset.mod));
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
    document.getElementById("cardDay")?.addEventListener("click", () => openMod("card_day"));
    document.getElementById("cardDay")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openMod("card_day");
      }
    });
    document.querySelectorAll("#quickBar .quick-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.dataset.mod) openMod(btn.dataset.mod);
        else if (btn.dataset.action) openAction(btn.dataset.action);
      });
    });
  } catch (e) {
    console.warn(e);
    document.getElementById("subtitle").textContent =
      "Открой из @MOracul_bot → Приложение";
    renderModules([], {});
  }
}

document.getElementById("btnPremium")?.addEventListener("click", () => openAction("premium"));
document.getElementById("btnRef")?.addEventListener("click", () => openAction("ref"));

document.querySelectorAll("#topics button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    haptic();
    const topic = btn.dataset.topic;
    try {
      await api("/api/topic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, user_id: Number(uid()) }),
      });
      document.querySelectorAll("#topics button").forEach((b) =>
        b.classList.toggle("active", b === btn)
      );
    } catch (e) {
      console.warn(e);
    }
  });
});

load();
