/** Быстрый ввод размеров на телефоне — без системной клавиатуры */

let target = null;
let overlay = null;

const KEYS = ["7", "8", "9", "4", "5", "6", "1", "2", "3", ".", "0", "⌫"];

export function ensureKeypad() {
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.className = "keypad-overlay";
  overlay.hidden = true;
  overlay.innerHTML = `
    <div class="keypad" role="dialog" aria-label="Ввод размера">
      <div class="keypad-display"><span data-kp-val></span><button type="button" class="keypad-done" data-kp-done>Готово</button></div>
      <div class="keypad-grid">
        ${KEYS.map((k) => `<button type="button" class="keypad-key" data-k="${k}">${k}</button>`).join("")}
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeKeypad(true);
  });
  overlay.querySelector("[data-kp-done]").onclick = () => closeKeypad(true);
  overlay.querySelectorAll("[data-k]").forEach((btn) => {
    btn.onclick = () => press(btn.dataset.k);
  });
  return overlay;
}

function press(k) {
  if (!target) return;
  let v = String(target.value || "");
  if (k === "⌫") v = v.slice(0, -1);
  else if (k === ".") {
    if (!v.includes(".")) v += v ? "." : "0.";
  } else {
    if (v === "0" && k !== ".") v = k;
    else v += k;
  }
  target.value = v;
  target.dispatchEvent(new Event("input", { bubbles: true }));
  syncDisplay();
}

function syncDisplay() {
  const el = overlay?.querySelector("[data-kp-val]");
  if (el) el.textContent = target?.value || "0";
}

export function openKeypad(input) {
  ensureKeypad();
  target = input;
  overlay.hidden = false;
  syncDisplay();
}

export function closeKeypad(commit) {
  if (!overlay) return;
  if (commit && target) {
    target.dispatchEvent(new Event("change", { bubbles: true }));
    target.blur();
  }
  overlay.hidden = true;
  target = null;
}

/** Привязка к input[inputmode=decimal|numeric] с data-keypad или классом .use-keypad */
export function bindKeypad(root = document) {
  ensureKeypad();
  root.querySelectorAll('input[inputmode="decimal"], input[inputmode="numeric"]').forEach((inp) => {
    if (inp.dataset.kpBound) return;
    inp.dataset.kpBound = "1";
    inp.addEventListener("focus", (e) => {
      // на десктопе с мышью оставляем системную клавиатуру
      if (window.matchMedia("(pointer: fine)").matches && !inp.dataset.forceKeypad) return;
      e.preventDefault();
      inp.blur();
      openKeypad(inp);
    });
  });
}
