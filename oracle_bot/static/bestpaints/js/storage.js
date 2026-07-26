const KEY = "bp_surveys_v1";

export function loadAll() {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

export function saveAll(list) {
  localStorage.setItem(KEY, JSON.stringify(list));
}

export function upsert(survey) {
  const list = loadAll();
  survey.updatedAt = new Date().toISOString();
  const i = list.findIndex((s) => s.id === survey.id);
  if (i >= 0) list[i] = survey;
  else list.unshift(survey);
  saveAll(list);
  return survey;
}

export function remove(id) {
  saveAll(loadAll().filter((s) => s.id !== id));
}

export function get(id) {
  return loadAll().find((s) => s.id === id) || null;
}

export function exportJson(survey) {
  const blob = new Blob([JSON.stringify(survey, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `zamer_${(survey.client?.name || "object").replace(/\s+/g, "_")}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}
