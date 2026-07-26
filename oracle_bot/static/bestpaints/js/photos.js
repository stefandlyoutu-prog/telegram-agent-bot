/** Сжатие фото с камеры — в localStorage без раздувания */

export function compressImageFile(file, maxSide = 1280, quality = 0.72) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
      const w = Math.round(img.width * scale);
      const h = Math.round(img.height * scale);
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      const dataUrl = canvas.toDataURL("image/jpeg", quality);
      resolve({
        id: `ph_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
        dataUrl,
        caption: "",
        createdAt: new Date().toISOString(),
        bytes: Math.round((dataUrl.length * 3) / 4),
      });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Не удалось прочитать фото"));
    };
    img.src = url;
  });
}

export function photosHtml(building) {
  const photos = building.photos || [];
  return `
    <div class="photos-block">
      <div class="photos-head">
        <strong>Фото объекта (общий вид)</strong>
        <label class="btn ghost photo-btn">
          📷 Камера / галерея
          <input type="file" accept="image/*" capture="environment" hidden data-photo-input />
        </label>
      </div>
      <p class="hint">Общий ракурс. Фото сторон — на шаге «Замер».</p>
      <div class="photos-grid">
        ${
          photos.length
            ? photos
                .map(
                  (p) => `
          <figure class="photo-card" data-pid="${p.id}">
            <img src="${p.dataUrl}" alt="фото"/>
            <button type="button" class="photo-del" data-ph-del="${p.id}">✕</button>
          </figure>`
                )
                .join("")
            : `<div class="empty soft">Пока нет общего фото</div>`
        }
      </div>
    </div>
  `;
}

/** Фото одной плоскости — снимать при обходе */
export function wallPhotosHtml(wall) {
  const photos = wall.photos || [];
  return `
    <div class="wall-photos">
      <div class="wall-photos-head">
        <span>Фото стороны ${photos.length ? `(${photos.length})` : "— снимите сейчас"}</span>
        <label class="btn ghost photo-btn sm">
          📷
          <input type="file" accept="image/*" capture="environment" hidden data-wall-photo="${wall.id}" />
        </label>
      </div>
      <div class="wall-photos-row">
        ${
          photos.length
            ? photos
                .map(
                  (p) => `
          <figure class="photo-card sm" data-pid="${p.id}">
            <img src="${p.dataUrl}" alt="сторона"/>
            <button type="button" class="photo-del" data-wall-ph-del="${wall.id}" data-pid="${p.id}">✕</button>
          </figure>`
                )
                .join("")
            : `<div class="empty soft mini">Нет фото стороны</div>`
        }
      </div>
    </div>
  `;
}
