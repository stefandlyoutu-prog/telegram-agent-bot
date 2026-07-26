/** Калькулятор «замер по проекту» — как в обучающих скринах калькулятора */

export function scaleCoef(drawn, realMeters) {
  const a = Number(String(drawn).replace(",", "."));
  const b = Number(String(realMeters).replace(",", "."));
  if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return null;
  return a / b;
}

export function applyScale(drawnLength, coef) {
  const x = Number(String(drawnLength).replace(",", "."));
  if (!Number.isFinite(x) || coef == null) return null;
  return Math.round(x * coef * 1000) / 1000;
}

/** Как в обучении: K = отрезок_на_чертеже ÷ известные_метры; метры = длина_на_чертеже × K */
export function scalePanelHtml(state = {}) {
  const drawnRef = state.drawnRef ?? "3.35";
  const realRef = state.realRef ?? "4.5";
  const sample = state.sample ?? "8.4";
  const k = scaleCoef(drawnRef, realRef);
  const meters = applyScale(sample, k);
  return `
    <div class="scale-card" id="scale-card">
      <div class="scale-head">
        <strong>По проекту · масштаб</strong>
        <span class="hint">Как в обучении: 3,35 ÷ 4,5 ≈ 0,74 → × на отрезки чертежа</span>
      </div>
      <div class="grid two">
        <div class="field">
          <label>Отрезок на чертеже / экране</label>
          <input id="sc-drawn" value="${drawnRef}" inputmode="decimal" data-force-keypad="1">
        </div>
        <div class="field">
          <label>Тот же размер в метрах (с подписи)</label>
          <input id="sc-real" value="${realRef}" inputmode="decimal" data-force-keypad="1">
        </div>
      </div>
      <div class="callout ok">K = <b id="sc-k">${k != null ? k.toFixed(4) : "—"}</b></div>
      <div class="grid two">
        <div class="field">
          <label>Длина на чертеже → в метры</label>
          <input id="sc-sample" value="${sample}" inputmode="decimal" data-force-keypad="1">
        </div>
        <div class="field">
          <label>Результат, м</label>
          <input id="sc-out" value="${meters != null ? meters : ""}" readonly>
        </div>
      </div>
      <div class="scale-actions">
        <button type="button" class="btn" id="sc-to-wall">→ в длину активной плоскости</button>
        <button type="button" class="btn ghost" id="sc-to-open">→ в ширину проёма</button>
      </div>
    </div>
  `;
}

export function bindScalePanel(root, { onToWall, onToOpen, onChange } = {}) {
  const card = root.querySelector("#scale-card");
  if (!card) return;

  const readState = () => ({
    drawnRef: root.querySelector("#sc-drawn")?.value ?? "",
    realRef: root.querySelector("#sc-real")?.value ?? "",
    sample: root.querySelector("#sc-sample")?.value ?? "",
  });

  const refresh = () => {
    const state = readState();
    const k = scaleCoef(state.drawnRef, state.realRef);
    const out = applyScale(state.sample, k);
    const kEl = root.querySelector("#sc-k");
    const outEl = root.querySelector("#sc-out");
    if (kEl) kEl.textContent = k != null ? k.toFixed(4) : "—";
    if (outEl) outEl.value = out != null ? String(out) : "";
    onChange?.(state);
    return out;
  };

  ["#sc-drawn", "#sc-real", "#sc-sample"].forEach((sel) => {
    root.querySelector(sel)?.addEventListener("input", refresh);
  });

  root.querySelector("#sc-to-wall")?.addEventListener("click", () => {
    const m = refresh();
    if (m != null) onToWall?.(m);
  });
  root.querySelector("#sc-to-open")?.addEventListener("click", () => {
    const m = refresh();
    if (m != null) onToOpen?.(m);
  });
}
