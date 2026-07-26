/** Soft-delete trash + confirm modal. Persist in localStorage for restore. */

const TRASH_KEY = "bp_trash_v1";
const MAX_TRASH = 40;
const KEEP_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

function loadTrash() {
  try {
    return JSON.parse(localStorage.getItem(TRASH_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveTrash(list) {
  localStorage.setItem(TRASH_KEY, JSON.stringify(list.slice(0, MAX_TRASH)));
}

function purgeExpired(list) {
  const now = Date.now();
  return list.filter((e) => !e.deletedAt || now - e.deletedAt < KEEP_MS);
}

export function listTrash() {
  const list = purgeExpired(loadTrash());
  if (list.length !== loadTrash().length) saveTrash(list);
  return list;
}

export function pushTrash({ type, label, payload, meta = {} }) {
  const list = purgeExpired(loadTrash());
  const entry = {
    id: `tr_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`,
    type,
    label: label || type,
    payload,
    meta,
    deletedAt: Date.now(),
  };
  list.unshift(entry);
  saveTrash(list);
  return entry;
}

export function getTrash(id) {
  return listTrash().find((e) => e.id === id) || null;
}

export function removeTrash(id) {
  saveTrash(listTrash().filter((e) => e.id !== id));
}

export function clearTrash() {
  saveTrash([]);
}

/**
 * Modal: «Точно удалить?»
 * @returns {Promise<boolean>}
 */
export function askDelete(what, opts = {}) {
  const title = opts.title || "Точно удалить?";
  const detail = what || "Этот элемент";
  const confirmLabel = opts.confirmLabel || "Да, удалить";
  const cancelLabel = opts.cancelLabel || "Отмена";
  const hint =
    opts.hint === false
      ? ""
      : opts.hint || "Можно будет восстановить из корзины или кнопкой «Отменить».";

  return new Promise((resolve) => {
    const prev = document.querySelector(".confirm-overlay");
    if (prev) prev.remove();

    const overlay = document.createElement("div");
    overlay.className = "confirm-overlay";
    overlay.innerHTML = `
      <div class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h3 id="confirm-title">${escape(title)}</h3>
        <p>${escape(detail)}</p>
        ${hint ? `<p class="confirm-hint">${escape(hint)}</p>` : ""}
        <div class="confirm-actions">
          <button type="button" class="btn" data-confirm="no">${escape(cancelLabel)}</button>
          <button type="button" class="btn danger" data-confirm="yes">${escape(confirmLabel)}</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const finish = (ok) => {
      overlay.remove();
      document.removeEventListener("keydown", onKey);
      resolve(ok);
    };
    const onKey = (e) => {
      if (e.key === "Escape") finish(false);
      if (e.key === "Enter") finish(true);
    };
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) finish(false);
    });
    overlay.querySelector('[data-confirm="no"]').onclick = () => finish(false);
    overlay.querySelector('[data-confirm="yes"]').onclick = () => finish(true);
    overlay.querySelector('[data-confirm="yes"]').focus();
  });
}

function escape(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Confirm → trash → run remove → toast with undo.
 * @param {object} opts
 * @param {string} opts.what - human label for confirm
 * @param {string} opts.type - trash type key
 * @param {*} opts.payload - data to restore
 * @param {object} [opts.meta]
 * @param {() => void} opts.applyRemove
 * @param {(payload:*, meta:*) => void} opts.applyRestore
 * @param {(msg:string, undo?:()=>void) => void} opts.toastUndo
 */
export async function softDelete(opts) {
  const ok = await askDelete(opts.what, opts.confirmOpts);
  if (!ok) return false;
  const entry = pushTrash({
    type: opts.type,
    label: opts.what,
    payload: opts.payload,
    meta: opts.meta || {},
  });
  opts.applyRemove();
  const undo = () => {
    opts.applyRestore(entry.payload, entry.meta || {});
    removeTrash(entry.id);
  };
  if (typeof opts.toastUndo === "function") {
    opts.toastUndo(`Удалено: ${opts.what}`, undo);
  }
  return entry;
}
