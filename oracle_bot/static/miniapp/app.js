const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor("#0f0e14");
  tg.setBackgroundColor("#0f0e14");
}

const MODULES = [
  ["horo_today", "Сегодня"],
  ["tarot", "Таро"],
  ["natal", "Натальная"],
  ["compat", "Пара"],
  ["karma", "Карма"],
  ["palm", "Ладонь"],
  ["career", "Карьера"],
  ["dating", "Любовь"],
  ["dream", "Сонник"],
  ["destiny", "Судьба дня"],
  ["portrait", "Портрет"],
  ["numerology", "Числа"],
];

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

function openMod(mod) {
  if (tg) tg.sendData(JSON.stringify({ action: "mod", module: mod }));
  else alert("Открой через Telegram: @" + (window.BOT_USERNAME || "MOracul_bot"));
}

function renderModules() {
  const el = document.getElementById("modules");
  el.innerHTML = MODULES.map(
    ([k, t]) => `<button class="mod" data-mod="${k}">${t}</button>`
  ).join("");
  el.querySelectorAll(".mod").forEach((b) =>
    b.addEventListener("click", () => openMod(b.dataset.mod))
  );
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
    document.querySelectorAll("#topics button").forEach((b) => {
      b.classList.toggle("active", b.dataset.topic === (data.topic || ""));
    });
  } catch (e) {
    console.warn(e);
  }
}

document.getElementById("btnPremium")?.addEventListener("click", () => {
  if (tg) tg.sendData(JSON.stringify({ action: "premium" }));
});

document.getElementById("btnRef")?.addEventListener("click", () => {
  if (tg) tg.sendData(JSON.stringify({ action: "ref" }));
});

document.querySelectorAll("#topics button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const topic = btn.dataset.topic;
    await api("/api/topic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, user_id: Number(uid()) }),
    });
    document.querySelectorAll("#topics button").forEach((b) =>
      b.classList.toggle("active", b === btn)
    );
  });
});

renderModules();
load();
