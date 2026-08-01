/** Защита кабинета клиента: анти-копирование / анти-печать / анти-скрин (детеррент). */

const WATERMARK_ID = "bp-cab-wm";
const SHIELD_ID = "bp-cab-shield";

function markText(meta = {}) {
  const name = meta.name || "клиент";
  const phone = meta.phone || "";
  const cab = meta.cabinetId || "";
  const ts = new Date().toLocaleString("ru-RU");
  return `BESTPAINTS · конфиденциально · ${name} · ${phone} · ${cab} · ${ts}`;
}

export function mountWatermark(meta = {}) {
  let el = document.getElementById(WATERMARK_ID);
  if (!el) {
    el = document.createElement("div");
    el.id = WATERMARK_ID;
    el.setAttribute("aria-hidden", "true");
    document.body.appendChild(el);
  }
  const line = markText(meta);
  // плитка водяных знаков
  el.innerHTML = Array.from({ length: 24 }, () => `<span>${escapeHtml(line)}</span>`).join("");
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function ensureShield() {
  let el = document.getElementById(SHIELD_ID);
  if (!el) {
    el = document.createElement("div");
    el.id = SHIELD_ID;
    el.innerHTML = `<div><strong>Конфиденциально</strong><p>Смета BestPaints недоступна для скриншота и пересылки. Вернитесь в кабинет.</p></div>`;
    document.body.appendChild(el);
  }
  return el;
}

function showShield(on) {
  const el = ensureShield();
  el.classList.toggle("on", !!on);
  document.documentElement.classList.toggle("bp-cab-blur", !!on);
}

export function installCabinetGuard(getMeta) {
  document.documentElement.classList.add("bp-cab-secure");
  document.body.classList.add("bp-cab-secure");

  const refreshWm = () => mountWatermark(typeof getMeta === "function" ? getMeta() || {} : getMeta || {});
  refreshWm();
  setInterval(refreshWm, 30_000);

  // запрет контекстного меню / drag / select
  const block = (e) => {
    e.preventDefault();
    return false;
  };
  document.addEventListener("contextmenu", block, true);
  document.addEventListener("dragstart", block, true);
  document.addEventListener("selectstart", block, true);
  document.addEventListener("copy", block, true);
  document.addEventListener("cut", block, true);
  document.addEventListener("paste", block, true);

  // горячие клавиши: print, save, copy, view-source, devtools-ish
  document.addEventListener(
    "keydown",
    (e) => {
      const key = (e.key || "").toLowerCase();
      const mod = e.ctrlKey || e.metaKey;
      if (key === "printscreen") {
        showShield(true);
        setTimeout(() => showShield(false), 2500);
        e.preventDefault();
        return;
      }
      if (mod && ["p", "s", "u", "c", "x", "a"].includes(key)) {
        e.preventDefault();
        e.stopPropagation();
        flashBan(key === "p" ? "Печать отключена" : "Копирование / сохранение отключено");
        return;
      }
      if (mod && e.shiftKey && ["i", "j", "c"].includes(key)) {
        e.preventDefault();
        return;
      }
      if (key === "f12") {
        e.preventDefault();
      }
    },
    true
  );

  // уход со вкладки / сворачивание — блюр (мешает «чистому» скрину)
  const onHide = () => showShield(true);
  const onShow = () => {
    // небольшая задержка, чтобы скрин «в момент возврата» ловил щит
    setTimeout(() => showShield(false), 400);
  };
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) onHide();
    else onShow();
  });
  window.addEventListener("blur", onHide);
  window.addEventListener("focus", onShow);
  window.addEventListener("pagehide", onHide);

  // перед печатью — уничтожить видимый контент
  window.addEventListener("beforeprint", () => {
    showShield(true);
    flashBan("Печать и PDF в кабинете клиента отключены");
  });
  window.addEventListener("afterprint", () => showShield(false));

  // блокировка print()
  try {
    window.print = () => {
      flashBan("Печать отключена");
      showShield(true);
      setTimeout(() => showShield(false), 1500);
    };
  } catch {
    /* ignore */
  }

  // запрет скачивания картинок через long-press атрибуты
  document.addEventListener(
    "click",
    (e) => {
      const a = e.target.closest("a[download], a[href$='.pdf'], a[href*='blob:']");
      if (a) {
        e.preventDefault();
        flashBan("Скачивание из кабинета отключено");
      }
    },
    true
  );
}

function flashBan(msg) {
  let t = document.getElementById("bp-cab-toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "bp-cab-toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(flashBan._tm);
  flashBan._tm = setTimeout(() => t.classList.remove("on"), 2200);
}

export function banExportUi() {
  // на случай если где-то появится кнопка
  document.querySelectorAll("#cab-pdf, [data-export], [data-share]").forEach((el) => {
    el.remove();
  });
}
