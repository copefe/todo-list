const msg = I18N.t;
const MONTH_NAMES = I18N.monthNames;
const DAY_NAMES = I18N.dayNames;
const WEEKDAY_SHORT = I18N.weekdayShort;
const WEEKDAY_LETTERS = I18N.weekdayLetters;
const WEEKDAY_NAMES_FULL = I18N.weekdayNames;
// Colour values are defined in style.css :root (--isi-*, --donut-*); only the tokens are referenced here.
const GREEN = ["var(--isi-0)", "var(--isi-1)", "var(--isi-2)", "var(--isi-3)"];
const DONUT_RAMP = ["var(--donut-1)", "var(--donut-2)", "var(--donut-3)", "var(--donut-4)", "var(--donut-5)"];
const DONUT_EMPTY_COLOR = "var(--donut-bos)";
const DONUT_OTHER_COLOR = "var(--donut-diger)";
const DONUT_MAX_SLICES = 5;
// If "reduce motion" is on, the donut's JS animation does not run (HRK-05); style.css turns off the CSS animations.
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");
const ROW = 38;
const WHEEL_TAU = 75; // ms: scroll smoothing constant (smaller = snappier)
const DONUT_DURATION = 600;
// Filter value; carried in a data-* attribute, so it is a plain string that cannot clash with a real category name.
const UNCATEGORIZED = "__uncategorized__";
const ROUTINE_ICON =
  '<svg class="rutin-ikon" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M2 5.2A4 4 0 0 1 9.3 3.3"/><path d="M9.6 1.2v2.4H7.2"/><path d="M10 6.8A4 4 0 0 1 2.7 8.7"/><path d="M2.4 10.8V8.4h2.4"/></svg>';

function routineIconHtml() {
  return ROUTINE_ICON + `<span class="gorsel-gizli">${escapeHtml(msg("a11y.routine"))} </span>`;
}

const S = {
  tasks: [], routines: [], categories: [], routinesByStreak: [],
  taskTab: "active", routineTab: "active",
  taskEditMode: false, routineEditMode: false,
  taskSelection: [], routineSelection: [],
  categoryEditMode: false, categorySelection: [], categoryAddOpen: false,
  chartKind: "weekly", chartOffset: 0, donutKind: "task",
  weeklyData: null, monthlyData: null, donutData: [],
  donutShownPercents: null, donutPrevious: null, donutStartTime: 0, donutTimer: null,
  modal: null, modalTab: "active",
  // Filter/sort is kept per card; the card on the main screen and the full-list window share the same setting.
  filter: { tasks: "all", routines: "all" },
  sortBy: { tasks: "remaining", routines: "remaining" },
  sortDir: { tasks: "asc", routines: "asc" },
  picker: null, pickerList: null,
  addStep: "ad", addName: "", addDate: null, addFrequency: "1", addWeekdays: [], addCategory: "", addError: null,
  detail: null, detailEditing: null, detailNameDraft: "", detailDateDraft: null, detailDateWasPast: false, detailWeekdays: [], detailFrequency: "1",
  saving: false,
};

// Slice colour from the token ramp: neighbouring slices are picked as far apart on the ramp as possible. "Other" uses its own token.
function donutColor(sliceItem, rank, count) {
  if (sliceItem.other) return DONUT_OTHER_COLOR;
  if (count <= 1) return DONUT_RAMP[2];
  return DONUT_RAMP[Math.round((rank * (DONUT_RAMP.length - 1)) / (count - 1))];
}

// Rest position is in CSS (--i/--n). If the selection changed, the bubble slides with spring physics (bubbleSelectionChanged, below).
function updateTabPill(groupEl, activeIndex) {
  const n = groupEl.querySelectorAll(".sekme-btn").length || 2;
  const next = Math.max(0, activeIndex);
  const previous = parseInt(groupEl.style.getPropertyValue("--i"), 10);
  groupEl.style.setProperty("--n", n);
  groupEl.style.setProperty("--i", next);
  bubbleSelectionChanged(groupEl, Number.isNaN(previous) ? next : previous, next);
}

async function callApi(method, ...args) {
  try {
    return await window.pywebview.api[method](...args);
  } catch (error) {
    showToast(msg("toast.callFailed", { message: (error && error.message) || error }), "hata");
    throw error;
  }
}

function showToast(text, kind) {
  const field = document.getElementById("bildirim-alani");
  const el = document.createElement("div");
  el.className = "bildirim " + (kind || "bilgi");
  el.textContent = text;
  field.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, "&quot;");
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

function toDate(item) {
  return new Date(item.year, item.month - 1, item.day, item.hour, item.minute);
}

function dateFields(d) {
  return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(), hour: d.getHours(), minute: d.getMinutes() };
}

function sameDate(a, b) {
  return a.year === b.year && a.month === b.month && a.day === b.day && a.hour === b.hour && a.minute === b.minute;
}

function dateText(t) {
  const d = toDate(t);
  return msg("date.full", { weekday: DAY_NAMES[d.getDay()], day: t.day, month: MONTH_NAMES[t.month - 1], year: t.year, time: `${pad2(t.hour)}:${pad2(t.minute)}` });
}

function minutesLeft(item) {
  return Math.round((toDate(item).getTime() - Date.now()) / 60000);
}

function formatRemaining(mins) {
  if (mins == null || Number.isNaN(mins)) return "—";
  if (mins < 0) return msg("time.overdue");
  if (mins < 60) return msg("time.min", { n: mins });
  if (mins < 1440) {
    const h = Math.floor(mins / 60), m = mins % 60;
    return msg("time.hours", { n: h }) + (m ? " " + msg("time.min", { n: m }) : "");
  }
  const day = Math.floor(mins / 1440);
  if (day < 3) {
    const h = Math.floor((mins % 1440) / 60);
    return msg("time.days", { n: day }) + (h ? " " + msg("time.hours", { n: h }) : "");
  }
  return msg("time.days", { n: day });
}

// The stored streak only increases at the end of a cycle; so that a routine completed in this cycle
// also counts, +1 is added for display. It is not written to the data.
function displayStreak(r) {
  return (r.streak || 0) + (r.done ? 1 : 0);
}

function parseFrequency(raw) {
  const n = Number(String(raw).trim());
  return Number.isInteger(n) && n >= 1 ? n : null;
}

// ---------- Routine repeat: frequency (every N days) XOR weekdays ----------

// Frequency and weekdays contradict each other; both cannot be selected at the same time:
//  - if any day is selected, the frequency box is locked (fixed to 1)
//  - if the frequency is greater than 1, the days are locked
function repeatBlockHtml(prefix, frequency) {
  const dayCircles = WEEKDAY_LETTERS.map((h, i) =>
    `<button type="button" class="gun-daire" data-gun="${i}" title="${WEEKDAY_NAMES_FULL[i]}" aria-label="${WEEKDAY_NAMES_FULL[i]}" aria-pressed="false">${h}</button>`
  ).join("");
  return `
    <div class="bolum-satiri">
      <span class="etiket-kucuk">${escapeHtml(msg("repeat.everyNDays"))}</span>
      <div class="sayac-kontrol">
        <button type="button" class="sayac-btn" data-adim="-1" aria-label="${escapeAttr(msg("repeat.decrease"))}" title="${escapeAttr(msg("repeat.decrease"))}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14"/></svg></button>
        <input class="metin-input kisa tekrar-siklik" id="${prefix}-siklik-input" type="number" min="1" step="1" value="${escapeHtml(frequency)}" aria-label="${escapeAttr(msg("repeat.everyNDays"))}">
        <button type="button" class="sayac-btn" data-adim="1" aria-label="${escapeAttr(msg("repeat.increase"))}" title="${escapeAttr(msg("repeat.increase"))}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button>
      </div>
    </div>
    <div class="bolum-satiri" style="margin-top:12px">
      <span class="etiket-kucuk">${escapeHtml(msg("repeat.weekdays"))}</span>
      <div class="gun-secici" role="group" aria-label="${escapeAttr(msg("repeat.weekdays"))}">${dayCircles}</div>
    </div>
    <div class="ipucu tekrar-not" hidden></div>`;
}

// Enabled state of the − / + buttons: disabled if the field is locked or the value reached min/max.
function updateStepperButtons(root, input) {
  const v = Number(String(input.value).trim());
  const valid = String(input.value).trim() !== "" && Number.isFinite(v);
  const min = input.min !== "" ? Number(input.min) : -Infinity, max = input.max !== "" ? Number(input.max) : Infinity;
  root.querySelectorAll(".sayac-btn").forEach((b) => {
    const isDecrement = b.dataset.adim === "-1";
    const off = input.disabled || (valid && (isDecrement ? v <= min : v >= max));
    b.disabled = off;
    b.setAttribute("aria-disabled", off ? "true" : "false");
  });
}

function applyRepeatState(root, days) {
  const input = root.querySelector(".tekrar-siklik");
  const hasWeekdays = days.length > 0;
  if (hasWeekdays) input.value = "1";
  const frequency = parseFrequency(input.value);
  const hasFrequency = !hasWeekdays && frequency != null && frequency > 1;
  input.disabled = hasWeekdays;
  updateStepperButtons(root, input);
  root.querySelectorAll(".gun-daire").forEach((d) => {
    const pressed = days.includes(Number(d.dataset.gun));
    d.classList.toggle("secili", pressed);
    d.setAttribute("aria-pressed", pressed ? "true" : "false");
    d.disabled = hasFrequency;
  });
  const note = root.querySelector(".tekrar-not");
  note.hidden = !(hasWeekdays || hasFrequency);
  note.textContent = msg(hasWeekdays ? "repeat.daysLockFreq" : "repeat.freqLockDays");
}

// getWeekdays/setWeekdays: state holding the selected days; changed: called after every change.
function bindRepeat(root, getWeekdays, setWeekdays, changed) {
  root.querySelector(".gun-secici").addEventListener("click", (e) => {
    const btn = e.target.closest(".gun-daire");
    if (!btn || btn.disabled) return;
    const g = Number(btn.dataset.gun);
    const next = getWeekdays().slice();
    const i = next.indexOf(g);
    if (i >= 0) next.splice(i, 1); else next.push(g);
    next.sort((a, b) => a - b);
    setWeekdays(next);
    applyRepeatState(root, next);
    if (changed) changed();
  });
  const freqInput = root.querySelector(".tekrar-siklik");
  freqInput.addEventListener("input", () => {
    applyRepeatState(root, getWeekdays());
    if (changed) changed();
  });
  // − / +: native stepUp/stepDown (same min, max, step rules); then the field's own 'input' flow runs
  root.querySelector(".sayac-kontrol").addEventListener("click", (e) => {
    const b = e.target.closest(".sayac-btn");
    if (!b || b.disabled) return;
    if (b.dataset.adim === "-1") freqInput.stepDown(); else freqInput.stepUp();
    freqInput.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function weekdaysText(days) {
  return days.map((g) => WEEKDAY_SHORT[g]).join(", ");
}

function filterByTab(list, tab) {
  if (tab === "done") return list.filter((o) => o.done);
  if (tab === "active") return list.filter((o) => !o.done);
  return list.slice();
}

// In the "time left" sort, overdue items come after upcoming ones.
function remainingSortKey(item) {
  const mins = minutesLeft(item);
  return mins < 0 ? 1e9 - mins : mins;
}

function filterLabel(raw) {
  return raw === UNCATEGORIZED ? msg("filter.uncategorized") : raw;
}

// Tab + category filter + sort; shared by the card and the full-list window.
function prepareList(kind, tab) {
  const base = filterByTab(S[kind], tab);
  const filter = S.filter[kind];
  let list = base;
  if (filter === UNCATEGORIZED) list = list.filter((o) => !o.category);
  else if (filter !== "all") list = list.filter((o) => (o.category || "") === filter);
  const direction = S.sortDir[kind] === "desc" ? -1 : 1;
  const field = S.sortBy[kind];
  list = list.slice().sort((a, b) => {
    let result;
    if (field === "name") result = a.title.localeCompare(b.title, I18N.lang);
    else if (field === "category") result = (a.category || "").localeCompare(b.category || "", I18N.lang);
    else if (field === "streak") result = displayStreak(a) - displayStreak(b);
    else result = remainingSortKey(a) - remainingSortKey(b);
    return result * direction;
  });
  return { list, baseCount: base.length };
}

function isInteracting() {
  return (S.modal && S.addStep === "tarih") || !!S.detailEditing || !!S.picker;
}

// ---------- Date limits ----------

// Earliest selectable moment: the first 5-minute slot after now.
function earliestDate() {
  const d = new Date(Date.now() + 60000);
  d.setSeconds(0, 0);
  d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5);
  return dateFields(d);
}

function normalizeDate(t) {
  const n = Object.assign({}, t);
  const e = earliestDate();
  n.minute = Math.floor(n.minute / 5) * 5;
  if (n.year < e.year) n.year = e.year;
  if (n.year === e.year && n.month < e.month) n.month = e.month;
  const maxDay = new Date(n.year, n.month, 0).getDate();
  if (n.day > maxDay) n.day = maxDay;
  const sameMonth = n.year === e.year && n.month === e.month;
  if (sameMonth && n.day < e.day) n.day = e.day;
  const sameDay = sameMonth && n.day === e.day;
  if (sameDay && n.hour < e.hour) n.hour = e.hour;
  if (sameDay && n.hour === e.hour && n.minute < e.minute) n.minute = e.minute;
  return n;
}

// ---------- Clock ----------

function updateClock() {
  const now = new Date();
  document.getElementById("saat-zaman").textContent = pad2(now.getHours()) + ":" + pad2(now.getMinutes());
  document.getElementById("saat-tarih").textContent = msg("date.weekdayDayMonth", { weekday: DAY_NAMES[now.getDay()], day: now.getDate(), month: MONTH_NAMES[now.getMonth()] });
}

function updateHeader() {
  const activeCount = S.tasks.filter((g) => !g.done).length;
  document.getElementById("ust-alt-bilgi").textContent = msg("header.activeTasks", { n: activeCount });

  const highest = S.routines.reduce((m, r) => Math.max(m, displayStreak(r)), 0);
  document.getElementById("seri-gostergesi").classList.toggle("var", highest > 0);
  document.getElementById("seri-gostergesi-metin").textContent = highest > 0 ? msg("header.streak", { n: highest }) : msg("header.noStreak");
}

// ---------- Data refresh ----------

async function refresh(options) {
  const force = !!(options && options.force);
  if (!force && isInteracting()) return;
  const state = await callApi("get_state");
  S.tasks = state.tasks;
  S.routines = state.routines;
  S.categories = state.categories;
  S.routinesByStreak = state.routines_by_streak;

  updateHeader();
  renderCard("tasks");
  renderCard("routines");
  renderCategoryCard();
  renderStreakList();
  await refreshCharts();
  await refreshDonut();
  if (S.modal) renderModalList();
}

function weekStart(offset) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + offset * 7);
  return d;
}

function isoDate(d) {
  return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
}

function monthStart(offset) {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth() + offset, 1);
}

async function refreshCharts() {
  if (S.chartKind === "weekly") {
    S.weeklyData = await callApi("weekly_completions", isoDate(weekStart(S.chartOffset)));
  } else {
    const a = monthStart(S.chartOffset);
    S.monthlyData = await callApi("monthly_completions", a.getFullYear(), a.getMonth() + 1);
  }
  renderChart();
}

// With 6 or more categories the 5 most populated are shown, the rest are grouped under "Other".
function donutSlices(data) {
  if (data.length <= DONUT_MAX_SLICES) return data;
  const sorted = data.slice().sort((a, b) => b.count - a.count);
  const first = sorted.slice(0, DONUT_MAX_SLICES);
  const remaining = sorted.slice(DONUT_MAX_SLICES);
  first.push({
    category: msg("donut.other"), other: true,
    count: remaining.reduce((t, d) => t + d.count, 0),
    percent: Math.round(remaining.reduce((t, d) => t + d.percent, 0) * 10) / 10,
  });
  return first;
}

async function refreshDonut() {
  S.donutData = donutSlices(await callApi("donut_data", S.donutKind));
  const targets = S.donutData.map((d) => d.percent);
  if (!REDUCED_MOTION.matches && S.donutShownPercents && S.donutShownPercents.length === targets.length) {
    S.donutPrevious = S.donutShownPercents.slice();
  } else {
    S.donutPrevious = null;
  }
  S.donutStartTime = performance.now();
  if (S.donutTimer) clearInterval(S.donutTimer);
  if (S.donutPrevious) {
    S.donutTimer = setInterval(() => {
      const k = (performance.now() - S.donutStartTime) / DONUT_DURATION;
      renderDonut();
      if (k >= 1) { clearInterval(S.donutTimer); S.donutTimer = null; }
    }, 16);
  }
  renderDonut();
}

function easeInOutCubic(k) {
  return k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
}

// ---------- Task / routine cards ----------

function emptyStateHtml(kind, tab, total, showAddButton) {
  const isRoutines = kind === "routines";
  let text;
  if (!total) text = msg(isRoutines ? "empty.noRoutines" : "empty.noTasks");
  else if (tab === "active") text = msg(isRoutines ? "empty.noActiveRoutines" : "empty.noActiveTasks");
  else if (tab === "done") text = msg("empty.noCompleted");
  else text = msg("empty.noItems");
  // In edit mode the "add" button is invisible but keeps its space: the card height and everything below stay the same in both modes.
  // The placeholder is hidden from screen readers and the focus order (aria-hidden, visibility:hidden, tabindex=-1).
  const label = escapeHtml(msg(isRoutines ? "card.addRoutine" : "card.addTask"));
  const buttonOf = tab === "done" ? ""
    : showAddButton
      ? `<button class="pill-btn vurgu" data-rol="ekle-ac">${label}</button>`
      : `<button class="pill-btn vurgu" data-gizli aria-hidden="true" tabindex="-1">${label}</button>`;
  return `<div class="bos-durum"><span>${escapeHtml(text)}</span>${buttonOf}</div>`;
}

function rowHtml(item, kind, editMode, isSelected) {
  const done = !!item.done;
  const on = editMode ? isSelected : done;
  const dotClass = "nokta" + (on ? (editMode ? " secili" : " acik") : "");
  const check = on ? '<span class="tik' + (editMode ? " secim-tik" : "") + '">✓</span>' : "";
  const mins = minutesLeft(item);
  const remainingText = done ? msg("row.done") : formatRemaining(mins);
  const remainingClass = done ? "bitti" : (mins < 0 ? "gecikti" : "");
  const nameClass = (done && !editMode) ? "bitmis" : "";
  const routineIcon = kind === "routines" ? routineIconHtml() : "";
  return `
    <div class="satir ${isSelected ? "secili-satir" : ""}" data-id="${escapeHtml(item.id)}" role="button" tabindex="0">
      <span class="${dotClass}">${check}</span>
      <span class="satir-ad ${nameClass}">${routineIcon}<span class="ad-metin" title="${escapeHtml(item.title).replace(/"/g, "&quot;")}">${escapeHtml(item.title)}</span></span>
      <span class="satir-kalan ${remainingClass}">${remainingText}</span>
    </div>`;
}

function updateSelectionButtons(deleteBtn, completeBtn, selectionCount, tab) {
  const suffix = selectionCount ? ` (${selectionCount})` : "";
  deleteBtn.disabled = !selectionCount;
  // Trash button: round (icon only) with no selection, icon + (n) pill with a selection
  deleteBtn.querySelector(".sil-sayi").textContent = selectionCount ? `(${selectionCount})` : "";
  deleteBtn.classList.toggle("dolu", selectionCount > 0);
  deleteBtn.setAttribute("aria-label", selectionCount ? msg("sel.deleteN", { n: selectionCount }) : msg("common.delete"));
  if (completeBtn) {
    completeBtn.disabled = !selectionCount;
    completeBtn.textContent = msg("common.complete") + suffix;
    completeBtn.hidden = tab === "done";
  }
}

function renderCard(kind) {
  const cardEl = document.getElementById(kind + "-card");
  const itemList = S[kind];
  const tab = kind === "tasks" ? S.taskTab : S.routineTab;
  const editMode = kind === "tasks" ? S.taskEditMode : S.routineEditMode;
  const selection = kind === "tasks" ? S.taskSelection : S.routineSelection;

  const { list: visible, baseCount } = prepareList(kind, tab);

  cardEl.querySelector('[data-rol="liste"]').innerHTML = visible.length
    ? visible.map((o) => rowHtml(o, kind, editMode, selection.includes(o.id))).join("")
    : (baseCount
      ? `<div class="bos-durum">${escapeHtml(msg("empty.noFilterMatch"))}</div>`
      : emptyStateHtml(kind, tab, itemList.length, !editMode));

  const filterBtn = cardEl.querySelector('[data-rol="filtre"]');
  const filterActive = S.filter[kind] !== "all";
  filterBtn.textContent = filterActive ? msg("filter.buttonActive", { name: filterLabel(S.filter[kind]) }) : msg("filter.button");
  filterBtn.classList.toggle("vurgu", filterActive);
  const sortBtn = cardEl.querySelector('[data-rol="sirala"]');
  const sortIsDefault = S.sortBy[kind] === "remaining" && S.sortDir[kind] === "asc";
  sortBtn.textContent = sortIsDefault ? msg("sort.button") : msg("sort.buttonActive", { field: msg("sort.field." + S.sortBy[kind]), dir: msg("sort.dir." + S.sortDir[kind]).toLocaleLowerCase(I18N.lang) });
  sortBtn.classList.toggle("vurgu", !sortIsDefault);

  cardEl.querySelector('[data-rol="sayac"]').textContent = msg("count.items", { n: visible.length }) + (editMode ? " · " + msg("tab." + tab) : "");

  const tabsEl = cardEl.querySelector('[data-rol="sekmeler"]');
  tabsEl.querySelectorAll("[data-sekme]").forEach((btn) => btn.classList.toggle("aktif", btn.dataset.sekme === tab));
  updateTabPill(tabsEl, tab === "done" ? 1 : 0);

  // Normal ↔ edit: elements are hidden with visibility (data-gizli), not display:none; they all share the same grid cell,
  // so the row height and the position of other elements do not change (style.css .kart[data-tur] .kart-ust).
  const editOpenBtn = cardEl.querySelector('[data-rol="duzenle-ac"]');
  const editCloseBtn = cardEl.querySelector('[data-rol="duzenle-kapat"]');
  const focused = document.activeElement;
  tabsEl.toggleAttribute("data-gizli", editMode);
  editOpenBtn.toggleAttribute("data-gizli", editMode);
  editCloseBtn.toggleAttribute("data-gizli", !editMode);
  cardEl.querySelector('[data-rol="duzenle-aksiyonlari"]').toggleAttribute("data-gizli", !editMode);
  // If the focused button gets hidden, focus moves to the opposite button (keyboard users keep their place)
  if (focused === editOpenBtn && editMode) editCloseBtn.focus({ preventScroll: true });
  else if (focused === editCloseBtn && !editMode) editOpenBtn.focus({ preventScroll: true });
  cardEl.querySelector('[data-rol="baslik"]').classList.toggle("acilir", !editMode);

  updateSelectionButtons(cardEl.querySelector('[data-rol="sil"]'), cardEl.querySelector('[data-rol="tamamla"]'), selection.length, tab);

  const seeAllBtn = cardEl.querySelector('[data-rol="tumunu-gor"]');
  seeAllBtn.hidden = !itemList.length;
  seeAllBtn.textContent = msg("card.seeAllCount", { n: itemList.length });
}

function onRowClick(kind, id, editMode) {
  if (editMode) {
    const key = kind === "tasks" ? "taskSelection" : "routineSelection";
    const idx = S[key].indexOf(id);
    if (idx >= 0) S[key].splice(idx, 1); else S[key].push(id);
    renderCard(kind);
    if (S.modal === kind) renderModalList();
  } else {
    S.detail = { kind, id };
    S.detailEditing = null;
    renderDetail();
  }
}

async function deleteSelected(kind) {
  const key = kind === "tasks" ? "taskSelection" : "routineSelection";
  if (!S[key].length) return;
  const result = await callApi("delete_items", S[key]);
  S[key] = [];
  await refresh({ force: true });
  if (result && result.deleted_count) showToast(msg("toast.deleted", { n: result.deleted_count }));
}

async function completeSelected(kind) {
  const key = kind === "tasks" ? "taskSelection" : "routineSelection";
  if (!S[key].length) return;
  const source = kind === "tasks" ? S.tasks : S.routines;
  const count = source.filter((o) => S[key].includes(o.id) && !o.done).length;
  await callApi("complete_items", S[key]);
  S[key] = [];
  await refresh({ force: true });
  if (count) showToast(msg("toast.completed", { n: count }));
}

function setEditMode(kind, pressed) {
  if (kind === "tasks") { S.taskEditMode = pressed; S.taskSelection = []; } else { S.routineEditMode = pressed; S.routineSelection = []; }
  renderCard(kind);
  if (S.modal === kind) renderModalList();
}

function onCardClick(kind, e) {
  const editMode = kind === "tasks" ? S.taskEditMode : S.routineEditMode;
  const tabBtn = e.target.closest("[data-sekme]");
  if (tabBtn) {
    if (kind === "tasks") S.taskTab = tabBtn.dataset.sekme; else S.routineTab = tabBtn.dataset.sekme;
    renderCard(kind);
    return;
  }
  if (e.target.closest('[data-rol="duzenle-ac"]')) { setEditMode(kind, true); return; }
  if (e.target.closest('[data-rol="duzenle-kapat"]')) { setEditMode(kind, false); return; }
  if (e.target.closest('[data-rol="sil"]')) { deleteSelected(kind); return; }
  if (e.target.closest('[data-rol="tamamla"]')) { completeSelected(kind); return; }
  if (e.target.closest('[data-rol="ekle-ac"]')) { openModal(kind, true); return; }
  if (e.target.closest('[data-rol="tumunu-gor"]')) { openModal(kind, false, "all"); return; }
  if (e.target.closest('[data-rol="filtre"]')) { openPicker(kind, "filtre"); return; }
  if (e.target.closest('[data-rol="sirala"]')) { openPicker(kind, "sirala"); return; }
  const rowEl = e.target.closest(".satir");
  if (rowEl) {
    onRowClick(kind, rowEl.dataset.id, editMode);
    return;
  }
  if (!editMode && !e.target.closest("button")) openModal(kind, false);
}

// ---------- Categories card ----------

function renderCategoryCard() {
  const list = document.getElementById("kategori-liste");
  const allItems = S.tasks.concat(S.routines);
  list.innerHTML = S.categories.length ? S.categories.map((name) => {
    const count = allItems.filter((o) => o.category === name).length;
    const selected = S.categorySelection.includes(name);
    const a11yAttrs = S.categoryEditMode ? 'role="button" tabindex="0"' : "";
    return `
      <div class="satir ${selected ? "secili-satir" : ""} ${S.categoryEditMode ? "" : "pasif"}" data-kategori="${escapeHtml(name)}" ${a11yAttrs}>
        <span class="nokta ${selected ? "secili" : ""}">${selected ? '<span class="tik secim-tik">✓</span>' : ""}</span>
        <span class="satir-ad"><span class="ad-metin" title="${escapeHtml(name).replace(/"/g, "&quot;")}">${escapeHtml(name)}</span></span>
        <span class="satir-kalan">${escapeHtml(msg("count.items", { n: count }))}</span>
      </div>`;
  }).join("") : `<div class="bos-durum">${escapeHtml(msg("empty.noCategoriesHint"))}</div>`;
  document.getElementById("kategori-sayac").textContent = msg("count.categories", { n: S.categories.length });
  document.getElementById("kategori-duzenle-ac").hidden = S.categoryEditMode;
  document.getElementById("kategori-duzenle-kapat").hidden = !S.categoryEditMode;
  document.getElementById("kategori-duzenle-aksiyonlari").hidden = !S.categoryEditMode;
  updateSelectionButtons(document.getElementById("kategori-sil-btn"), null, S.categorySelection.length);
}

// ---------- Charts ----------

function renderChart() {
  const weeklyEl = document.getElementById("haftalik-grafik");
  const monthlyEl = document.getElementById("aylik-grafik");
  const captionEl = document.getElementById("grafik-aciklama");
  const futureLegend = document.getElementById("lejant-gelecek");
  document.querySelectorAll("#grafik-sekmeleri [data-grafik]").forEach((btn) => btn.classList.toggle("aktif", btn.dataset.grafik === S.chartKind));
  updateTabPill(document.getElementById("grafik-sekmeleri"), S.chartKind === "monthly" ? 1 : 0);
  document.getElementById("donem-sonraki").disabled = S.chartOffset >= 0;

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (S.chartKind === "weekly") {
    weeklyEl.hidden = false; monthlyEl.hidden = true; futureLegend.hidden = true;
    weeklyEl.setAttribute("role", "group");
    weeklyEl.setAttribute("aria-label", msg("chart.weeklyAria"));
    const begin = weekStart(S.chartOffset);
    const last = new Date(begin); last.setDate(begin.getDate() + 6);
    captionEl.textContent = S.chartOffset === 0
      ? msg("chart.thisWeek")
      : begin.getMonth() !== last.getMonth()
        ? msg("chart.weekRangeCrossMonth", { d1: begin.getDate(), month1: MONTH_NAMES[begin.getMonth()], d2: last.getDate(), month2: MONTH_NAMES[last.getMonth()], year: last.getFullYear() })
        : msg("chart.weekRangeSameMonth", { d1: begin.getDate(), d2: last.getDate(), month: MONTH_NAMES[last.getMonth()], year: last.getFullYear() });
    const todayIndex = S.chartOffset === 0 ? (today.getDay() + 6) % 7 : -1;
    const data = S.weeklyData;
    if (data) {
      weeklyEl.innerHTML = data.counts.map((count, i) => {
        const barHeight = Math.max(10, Math.round((Math.min(count, 10) / 10) * 150));
        const bucket = data.buckets[i];
        return `
          <div class="bar-sutun" role="img" data-i="${i}" aria-label="${escapeHtml(tooltipText(weeklyTooltip(data, i)))}${i === todayIndex ? ` (${escapeHtml(msg("chart.today"))})` : ""}">
            <span class="bar-sayi">${count}</span>
            <div class="bar" style="height:${barHeight}px;background:${GREEN[bucket]}"></div>
            <span class="bar-etiket ${i === todayIndex ? "bugun" : ""}">${WEEKDAY_SHORT[i]}</span>
          </div>`;
      }).join("");
    }
  } else {
    weeklyEl.hidden = true; monthlyEl.hidden = false;
    monthlyEl.setAttribute("role", "group");
    monthlyEl.setAttribute("aria-label", msg("chart.monthlyAria"));
    const period = monthStart(S.chartOffset);
    captionEl.textContent = msg("chart.monthlyCaption", {
      period: S.chartOffset === 0 ? msg("chart.thisMonth") : msg("chart.monthYear", { month: MONTH_NAMES[period.getMonth()], year: period.getFullYear() }),
    });
    const data = S.monthlyData;
    let hasFuture = false;
    if (data) {
      monthlyEl.innerHTML = data.days.map((g) => {
        const isFuture = new Date(period.getFullYear(), period.getMonth(), g.day) > today;
        if (isFuture) hasFuture = true;
        const title = tooltipText(monthlyTooltip(period, g, isFuture));
        const inlineStyle = isFuture ? "" : `background:${GREEN[g.bucket]}`;
        return `<div class="isi-hucre ${isFuture ? "gelecek" : ""}" role="img" data-gun="${g.day}" aria-label="${escapeHtml(title)}" style="${inlineStyle}"></div>`;
      }).join("");
    }
    futureLegend.hidden = !hasFuture;
  }
}

// ---------- Chart tooltip (custom tooltip) ----------
// Records only store the date and the kind (task/routine); the tooltip shows these.
function tooltipContent(date, count, tasks, routines, future) {
  return { title: date, future, count, tasks, routines };
}
function weeklyTooltip(data, i) {
  const d = new Date(data.days[i] + "T00:00:00");
  const date = msg("date.weekdayDayMonth", { weekday: WEEKDAY_NAMES_FULL[i], day: d.getDate(), month: MONTH_NAMES[d.getMonth()] });
  return tooltipContent(date, data.counts[i], (data.tasks || [])[i] || 0, (data.routines || [])[i] || 0, false);
}
function monthlyTooltip(period, g, future) {
  const d = new Date(period.getFullYear(), period.getMonth(), g.day);
  const date = msg("date.weekdayDayMonth", { weekday: WEEKDAY_NAMES_FULL[(d.getDay() + 6) % 7], day: g.day, month: MONTH_NAMES[period.getMonth()] });
  return tooltipContent(date, g.count, g.tasks || 0, g.routines || 0, future);
}
function tooltipText(c) {
  if (c.future) return c.title + " · " + msg("chart.notYet");
  return c.title + " · " + (c.count ? `${msg("tip.completions", { n: c.count })} (${msg("tip.tasks", { n: c.tasks })}, ${msg("tip.routines", { n: c.routines })})` : msg("tip.none"));
}
function tooltipHtml(c, color) {
  if (c.future) return `<b>${escapeHtml(c.title)}</b><div class="ip-alt">${escapeHtml(msg("tip.notYetTitle"))}</div>`;
  if (!c.count) return `<b>${escapeHtml(c.title)}</b><div class="ip-alt">${escapeHtml(msg("tip.noneTitle"))}</div>`;
  return `<b>${escapeHtml(c.title)}</b>
    <div class="ip-sayi"><span class="ip-nokta" style="background:${color}"></span>${escapeHtml(msg("tip.completions", { n: c.count }))}</div>
    <div class="ip-alt">${escapeHtml(msg("tip.tasks", { n: c.tasks }))} · ${escapeHtml(msg("tip.routines", { n: c.routines }))}</div>`;
}
// Right above the bar/cell: the height is not fixed, it is computed from the target's top edge; if it does not fit it goes below.
function showTooltip(anchorEl, html) {
  const tooltip = document.getElementById("grafik-ipucu");
  tooltip.innerHTML = html;
  tooltip.hidden = false;
  const r = anchorEl.getBoundingClientRect();
  const w = tooltip.offsetWidth, h = tooltip.offsetHeight, gap = 10;
  const leftX = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
  let topY = r.top - h - gap;
  if (topY < 8) topY = r.bottom + gap;
  tooltip.style.transform = `translate(${Math.round(leftX)}px, ${Math.round(topY)}px)`;
}
function hideTooltip() { document.getElementById("grafik-ipucu").hidden = true; }
function bindTooltips() {
  const weekly = document.getElementById("haftalik-grafik");
  const monthly = document.getElementById("aylik-grafik");
  weekly.addEventListener("pointerover", (e) => {
    const col = e.target.closest(".bar-sutun");
    if (!col || !S.weeklyData) return;
    const i = Number(col.dataset.i);
    showTooltip(col.querySelector(".bar"), tooltipHtml(weeklyTooltip(S.weeklyData, i), GREEN[S.weeklyData.buckets[i]]));
  });
  monthly.addEventListener("pointerover", (e) => {
    const cell = e.target.closest(".isi-hucre");
    if (!cell || !S.monthlyData) return;
    const g = S.monthlyData.days.find((x) => String(x.day) === cell.dataset.gun);
    if (!g) return;
    const period = monthStart(S.chartOffset);
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const future = new Date(period.getFullYear(), period.getMonth(), g.day) > today;
    showTooltip(cell, tooltipHtml(monthlyTooltip(period, g, future), GREEN[g.bucket]));
  });
  [weekly, monthly].forEach((el) => {
    el.addEventListener("pointerout", (e) => { if (!el.contains(e.relatedTarget) || !e.relatedTarget.closest(".bar-sutun, .isi-hucre")) hideTooltip(); });
  });
  window.addEventListener("scroll", hideTooltip, true);
}

// ---------- Draggable selection bubble (LQG-10/16/21/22/23) ----------
// Method and defaults: skill prototype references/stiller/ornekler/liquid-glass-mercek-v2.html (adapted to the app).
// At rest the bubble is flat and opaque; its position comes from CSS (updateTabPill → --i/--n), no loop runs.
// - Short click: no glass; the bubble only slides to its new place on a spring (frequent action: no stretch, HRK-10).
// - Keyboard (←/→/Home/End, Enter/Space): critically damped spring, no overshoot/stretch/glass.
// - Press and hold (HOLD_MS) or a DRAG_START_PX drag, from ANY tab: the bubble "lifts" and turns into glass
//   (grows, overhangs the bar's outline by BUBBLE.overhang px, lens + edge magnification + edge blur + strong spectrum turn on),
//   follows the pointer with a gel lag and stretches with speed. The MOMENT its centre passes the midpoint of two items the new
//   item is selected (through the existing click flow: .click()) and a short squash is seen. On release it settles on an
//   underdamped spring (wobble) and becomes opaque again within ≤ 200ms.
// - Reduce motion: no spring/stretch/wobble/dispersion; the bubble jumps straight to item centres.
// - Reduce transparency / more contrast: stays opaque while dragging too (no glass, lens, dispersion or blur).
// Lens trap: no ancestor of the filtered copy has transform: scale; magnification is done via font/column/padding sizes.
// Cost: the glass layers, map and filter only exist in the glass state; when it stops the loop ends and the layers are removed.
const REDUCED_TRANSPARENCY = window.matchMedia("(prefers-reduced-transparency: reduce)");
const MORE_CONTRAST = window.matchMedia("(prefers-contrast: more)");

// === Bubble settings: single constants block (v2 prototype defaults, 2026-11-17). There is no settings panel in the app. ===
const BUBBLE = Object.freeze({
  refraction: 12,          // refraction strength: feDisplacementMap scale of the shared refraction (outermost shift ≈ refraction / 2 px)
  band: 0.6,            // refraction band / bubble height (refraction profile)
  sharpness: 2.6,       // edge sharpness: shift = (1 − d/band)^sharpness
  vertical: 1,             // vertical refraction ratio on the flat top/bottom edge
  dispersion: "strong",     // colour dispersion mode: "off" | "thin" (R–B ≤ 4px) | "strong" (≤ 10px; only while dragging)
  dispersionPx: 7,         // shift between the two ends of the spectrum (violet ↔ red) (R–B, px); clamped to the mode limit
  edgeBlur: 2,      // edge blur (Gaussian deviation, px); 0 = off
  ring: 0,             // edge ring opacity; 0 = none
  innerGlow: 0.03,   // peak alpha of the inner glow from the pressed point
  magnification: 1.4,         // lens magnification (size multiplier of the copy)
  glassOpacity: 0.3,      // glass opacity: tint alpha in the glass state = glassOpacity × 0.1 (style.css --cam-opaklik)
  growWidth: 1.2,        // width growth in the glass state
  overhang: 5.5,           // overhang beyond the bar's outer outline (px)
  stretch: true,         // speed-based stretch (drag and settling after a drag)
  wobble: true,       // settling wobble (underdamped spring, ζ ≈ 0.67)
});
const DISPERSION_LIMIT = { off: 0, thin: 4, strong: 10 };
const STRIP_RATIO = { off: 0.10, thin: 0.12, strong: 0.20 };   // spectrum strip thickness / bubble height
const STRIP_SIDE = 0.3;                                           // strength of the strip at the (horizontal) ends
const SPECTRUM_SAMPLES = 7;                                            // number of spectrum samples (violet → red)
const HOLD_MS = 220;                                            // threshold for turning into glass when pressed and held
const DRAG_START_PX = 4;
document.documentElement.style.setProperty("--cam-opaklik", BUBBLE.glassOpacity);
document.documentElement.style.setProperty("--isilti-a", BUBBLE.innerGlow);

const bubbles = new WeakMap();      // .sekme-grubu → spring state
const liveBubbles = new Set();     // the ones currently in the loop (empty at rest)
let bubbleFrame = 0, bubbleLastTime = 0, DRAG = null, dragEndTime = 0, lastKeyboardSelect = -1e9, mapKey = "", spectrumReady = false;
const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
const glassDisabled = () => REDUCED_TRANSPARENCY.matches || MORE_CONTRAST.matches;
const reducedMotion = () => REDUCED_MOTION.matches;

// Pill-shaped displacement map (v2 haritaUret). feDisplacementMap: out(x,y) = in(x + s·(R−0.5), y + s·(G−0.5)).
// "main": in the edge band the sample is taken from the CENTRE side, content stretches and grows toward the edge (LQG-22); magnitude (1 − d/band)^exponent.
// "strip": flat plateau + soft falloff only in the outermost strip (spectrum). "mask": blur mask, alpha 1 at the edge, 0 at the end of the band.
function makeMap(w, h, band, vertical, exponent, kind, horizontal = 1) {
  const c = document.createElement("canvas");
  c.width = Math.max(2, Math.round(w)); c.height = Math.max(2, Math.round(h));
  const ctx = c.getContext("2d"), img = ctx.createImageData(c.width, c.height);
  const r = h / 2, ax = r, bx = w - r, cy = h / 2;
  for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
    const px = x + 0.5, py = y + 0.5, qx = clamp(px, ax, bx);
    const nx = px - qx, ny = py - cy, uz = Math.hypot(nx, ny) || 1e-6, d = r - uz;
    const i = (y * c.width + x) * 4;
    if (kind === "mask") {
      img.data[i] = img.data[i + 1] = img.data[i + 2] = 255;
      img.data[i + 3] = d <= 0 ? 255 : d >= band ? 0 : Math.round(255 * Math.pow(1 - d / band, exponent));
      continue;
    }
    let dx = 0, dy = 0;
    if (d > -2 && d < band) {
      const t = clamp(d / band, 0, 1);
      const m = kind === "strip" ? (t < 0.5 ? 1 : 1 - Math.pow((t - 0.5) / 0.5, 2) * (3 - 2 * (t - 0.5) / 0.5)) : Math.pow(1 - t, exponent);
      dx = -(nx / uz) * m * horizontal; dy = -(ny / uz) * m * vertical;   // minus: sample from the centre side
    }
    img.data[i] = Math.round(128 + dx * 127); img.data[i + 1] = Math.round(128 + dy * 127); img.data[i + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  return c.toDataURL();
}

// The spectrum step is added once to the #mercek filter: SPECTRUM_SAMPLES copies are sampled from the strip map with increasing shift,
// each multiplied by a spectrum colour and summed. Weights sum to 1 per channel, alpha 1/samples → at shift 0 the result equals the input.
function buildSpectrum() {
  if (spectrumReady) return;
  const filter = document.getElementById("mercek");
  if (!filter) return;
  const NS = "http://www.w3.org/2000/svg";
  const spectrumColors = [[0.55, 0, 1], [0, 0.35, 1], [0, 0.8, 0.8], [0.1, 1, 0.1], [1, 1, 0], [1, 0.45, 0], [1, 0, 0.05]]; // violet → red
  const top = [0, 1, 2].map((j) => spectrumColors.reduce((t, r) => t + r[j], 0));
  const el = (name, attrs) => { const e = document.createElementNS(NS, name); for (const k in attrs) e.setAttribute(k, attrs[k]); filter.appendChild(e); return e; };
  for (let k = 0; k < SPECTRUM_SAMPLES; k++) {
    const w = spectrumColors[k].map((v, j) => (v / top[j]).toFixed(4));
    el("feDisplacementMap", { id: "mercek-t" + k, in: "kG", in2: "serit", scale: 0, xChannelSelector: "R", yChannelSelector: "G", result: "t" + k });
    el("feColorMatrix", { in: "t" + k, type: "matrix", result: "c" + k,
      values: `${w[0]} 0 0 0 0  0 ${w[1]} 0 0 0  0 0 ${w[2]} 0 0  0 0 0 ${(1 / SPECTRUM_SAMPLES).toFixed(5)} 0` });
    if (k > 0) el("feComposite", { in: k === 1 ? "c0" : "s" + (k - 1), in2: "c" + k, operator: "arithmetic", k1: 0, k2: 1, k3: 1, k4: 0, result: "s" + k });
  }
  const ct = el("feComponentTransfer", { in: "s" + (SPECTRUM_SAMPLES - 1) });
  for (const f of ["feFuncR", "feFuncG", "feFuncB"]) { const e = document.createElementNS(NS, f); e.setAttribute("type", "linear"); e.setAttribute("slope", SPECTRUM_SAMPLES); ct.appendChild(e); }
  spectrumReady = true;
}

function getBubble(group) {
  let B = bubbles.get(group);
  if (!B) {
    const pill = group.querySelector(":scope > .sekme-pil");
    if (!pill) return null;
    B = { group, pill, x: 0, vx: 0, g: 0, vg: 0, c: 0, cH: 0, e: 0, mode: "settle",
      selected: parseInt(group.style.getPropertyValue("--i"), 10) || 0, layers: null, hasMask: false };
    bubbles.set(group, B);
  }
  B.buttons = [...group.querySelectorAll(":scope > .sekme-btn")];
  return B;
}

// Sizes are in the bar's padding box; identical to the resting CSS position (top 4px, width (100% − 8px) / n)
function bubbleMetrics(B) {
  const b0 = B.buttons[0], pad = b0.offsetLeft, topY = b0.offsetTop, n = B.buttons.length;
  const col = (B.group.clientWidth - 2 * pad) / n, inner = B.group.clientHeight - 2 * topY;
  return { col, inner, pad, n, CY: topY + inner / 2, Hfull: inner + 2 * (topY + B.group.clientTop + BUBBLE.overhang),
    center: (i) => pad + col * (i + 0.5) };
}
const nearestIndex = (x, o) => clamp(Math.round((x - o.pad - o.col / 2) / o.col), 0, o.n - 1);

// Glass layers (glass state only): clear tint, lens copy (+ spectrum strips, optional ring), inner glow
function buildLayers(B) {
  if (B.layers) return;
  buildSpectrum();
  const make = (cls, parent, label = "div") => { const e = document.createElement(label); e.className = cls; parent.appendChild(e); return e; };
  const back = make("pil-katman pil-arka", B.pill);
  const lens = make("pil-katman pil-mercek", B.pill);
  lens.setAttribute("aria-hidden", "true");
  const copy = make("pil-kopya", lens);
  const copies = B.buttons.map((b) => { const s = make("", copy, "span"); s.textContent = b.textContent.trim(); return s; });
  const spectrumStrips = [make("pil-tayf", copy, "i"), make("pil-tayf", copy, "i")];
  const ring = BUBBLE.ring > 0 ? make("pil-halka", copy, "i") : null;
  const glow = make("pil-katman pil-isilti", B.pill);
  B.layers = { back, lens, copy, copies, spectrumStrips, ring, glow, fs: parseFloat(getComputedStyle(B.buttons[0]).fontSize) || 13 };
}
function removeLayers(B) {
  if (!B.layers) return;
  for (const k of ["back", "lens", "glow"]) B.layers[k].remove();
  B.layers = null;
}

// Per-frame drawing (v2 ciz): size, amount of glass (--c), light angle, lens, map placement, spectrum, hole mask
function drawBubble(B) {
  const o = bubbleMetrics(B), c = B.c, glass = c > 0.001 && !!B.layers, st = B.pill.style;
  let W = o.col * (1 + (BUBBLE.growWidth - 1) * B.g) * (1 + 0.25 * B.e);
  const H = (o.inner + (o.Hfull - o.inner) * B.g) * (1 - 0.14 * B.e);
  W = Math.min(W, o.col * 1.4);                                     // upper limit of speed-based widening (LQG-10)
  const leftX = B.x - W / 2, topY = o.CY - H / 2;
  st.left = leftX.toFixed(2) + "px"; st.top = topY.toFixed(2) + "px"; st.width = W.toFixed(2) + "px"; st.height = H.toFixed(2) + "px";
  st.setProperty("--c", c.toFixed(3));
  B.group.toggleAttribute("data-surukleniyor", glass);
  const lightAngle = reducedMotion() ? 135 : 135 + clamp(B.vx / 60, -18, 18);   // LQG-13: ±18°, fixed under reduce motion
  st.setProperty("--isik", lightAngle.toFixed(1) + "deg");
  if (DRAG && DRAG.B === B && DRAG.px != null) st.setProperty("--px", clamp((DRAG.px - leftX) / W * 100, 0, 100).toFixed(1) + "%");

  if (glass) {
    const K = B.layers, M = 1 + (BUBBLE.magnification - 1) * c;             // LQG-16: magnification and refraction "materialise" from zero
    // R–B shift clamped to the mode limit; 0 under reduce motion/transparency and more contrast (LQG-09); fades before the glass via c²
    const dispersionOff = reducedMotion() || glassDisabled() || BUBBLE.dispersion === "off";
    const rb = dispersionOff ? 0 : Math.min(BUBBLE.dispersionPx, DISPERSION_LIMIT[BUBBLE.dispersion]) * c * c;
    const ks = K.copy.style;
    ks.setProperty("--k-sutun", (o.col * M).toFixed(3) + "px");
    ks.setProperty("--k-dolgu", (o.pad * M).toFixed(3) + "px");
    ks.setProperty("--k-ic", (o.inner * M).toFixed(3) + "px");
    ks.setProperty("--k-fs", (K.fs * M).toFixed(3) + "px");
    ks.left = (W / 2 - M * B.x).toFixed(2) + "px"; ks.top = (H / 2 - M * o.CY).toFixed(2) + "px";
    // Maps are generated once at full (grown) size; during lift-off and stretch they are fitted via the feImage size
    const W1 = o.col * BUBBLE.growWidth, H1 = o.Hfull;
    const sizeKey = Math.round(W1) + "|" + Math.round(H1);
    const dispMap = document.getElementById("mercek-harita"), stripMap = document.getElementById("mercek-serit");
    const blurMask = document.getElementById("mercek-bmaske"), filter = document.getElementById("mercek");
    if (sizeKey !== mapKey) {
      dispMap.setAttribute("href", makeMap(W1, H1, H1 * BUBBLE.band, BUBBLE.vertical, BUBBLE.sharpness, "main"));
      stripMap.setAttribute("href", makeMap(W1, H1, H1 * STRIP_RATIO[BUBBLE.dispersion], 1, 1, "strip", STRIP_SIDE));
      blurMask.setAttribute("href", makeMap(W1, H1, H1 * BUBBLE.band, 1, 1.5, "mask"));
      mapKey = sizeKey;
    }
    const hx = M * B.x - W / 2, hy = M * o.CY - H / 2;
    for (const h of [dispMap, stripMap, blurMask]) {
      h.setAttribute("x", hx.toFixed(2)); h.setAttribute("y", hy.toFixed(2));
      h.setAttribute("width", W.toFixed(2)); h.setAttribute("height", H.toFixed(2));
    }
    document.getElementById("mercek-ana").setAttribute("scale", (BUBBLE.refraction * c).toFixed(2));
    document.getElementById("mercek-bulanik").setAttribute("stdDeviation", (glassDisabled() ? 0 : BUBBLE.edgeBlur * c).toFixed(2));
    // Filter region is only the bubble (+ spectrum margin): few pixels are processed per frame
    const margin = 12;
    filter.setAttribute("x", (hx - margin).toFixed(1)); filter.setAttribute("y", (hy - margin).toFixed(1));
    filter.setAttribute("width", (W + 2 * margin).toFixed(1)); filter.setAttribute("height", (H + 2 * margin).toFixed(1));
    for (let k = 0; k < SPECTRUM_SAMPLES; k++) {
      const d = document.getElementById("mercek-t" + k);
      if (d) d.setAttribute("scale", (rb * (2 * k / (SPECTRUM_SAMPLES - 1) - 1)).toFixed(2));
    }
    // Spectrum source: a thin light strip R–B/2 inside the top/bottom edge, fading toward the ends; alpha 0 when dispersion is off
    const tk = Math.max(1.5, rb * 0.4), r0 = H / 2, inner = 1 + rb * 0.5;
    const tl = (hx + r0 * 0.7).toFixed(2), tw = Math.max(0, W - r0 * 1.4).toFixed(2);
    K.spectrumStrips[0].style.cssText = `left:${tl}px;width:${tw}px;top:${(hy + inner).toFixed(2)}px;height:${tk.toFixed(2)}px`;
    K.spectrumStrips[1].style.cssText = `left:${tl}px;width:${tw}px;top:${(hy + H - inner - tk).toFixed(2)}px;height:${tk.toFixed(2)}px`;
    ks.setProperty("--tayf-a", rb > 0 ? "0.9" : "0");
    if (K.ring) {
      const hi = 2;
      Object.assign(K.ring.style, { left: (hx + hi) + "px", top: (hy + hi) + "px", width: (W - 2 * hi) + "px", height: (H - 2 * hi) + "px",
        padding: Math.max(1.5, rb * 0.65).toFixed(2) + "px" });
      K.ring.style.setProperty("--halka-a", BUBBLE.ring);
    }
    K.copies.forEach((s, j) => s.toggleAttribute("data-secili", j === B.selected));
    // The part of the real text under the bubble is hidden; only the copy in the lens is visible in its place
    const rightX = leftX + W;
    B.buttons.forEach((b) => {
      const l = (leftX - b.offsetLeft).toFixed(1), r = (rightX - b.offsetLeft).toFixed(1);
      b.style.setProperty("--delik", `linear-gradient(90deg, #000 ${l}px, transparent ${l}px, transparent ${r}px, #000 ${r}px)`);
    });
    B.hasMask = true;
  } else if (B.hasMask) {
    B.buttons.forEach((b) => b.style.removeProperty("--delik"));
    B.hasMask = false;
  }
}

// Physics step (v2 adim): position spring, lift spring (g), amount of glass (c), speed stretch (e), live selection
function bubbleStep(B, dt) {
  const o = bubbleMetrics(B), dragging = !!(DRAG && DRAG.B === B && DRAG.started);
  const target = dragging ? DRAG.target : o.center(B.selected);
  if (reducedMotion()) {
    B.x = dragging ? o.center(nearestIndex(target, o)) : target; B.vx = 0; B.c = B.cH; B.g = B.cH; B.vg = 0; B.e = 0;
  } else {
    // tight while dragging (gel lag), underdamped on release/click (wobble), critically damped for keyboard
    const [k, d] = B.mode === "drag" ? [1100, 44] : B.mode === "keyboard" ? [700, 53] : BUBBLE.wobble ? [380, 26] : [380, 39];
    B.vx += (k * (target - B.x) - d * B.vx) * dt; B.x += B.vx * dt;
    B.vg += (520 * (B.cH - B.g) - 30 * B.vg) * dt; B.g = clamp(B.g + B.vg * dt, -0.08, 1.2);
    B.c += clamp(B.cH - B.c, -dt / 0.18, dt / 0.18);                // rest ↔ glass ≤ 200ms
    const eH = BUBBLE.stretch && (B.mode === "drag" || B.mode === "release") ? Math.min(Math.abs(B.vx) / 1600, 1) : 0;
    B.e += (eH - B.e) * Math.min(1, dt * 18);
  }
  const a = o.center(0), b = o.center(o.n - 1);                        // the centre cannot leave the first/last item
  if (B.x < a) { B.x = a; B.vx = Math.max(0, B.vx); } else if (B.x > b) { B.x = b; B.vx = Math.min(0, B.vx); }
  if (dragging) {
    const h = nearestIndex(B.x, o);
    if (h !== B.selected) {
      B.selected = h;
      B.buttons[h].click();                                            // existing selection flow (data/settings flow unchanged)
      if (!reducedMotion()) B.vg -= 3.2;                          // threshold crossed: short squash (visual "click")
      if (navigator.vibrate && navigator.userActivation && navigator.userActivation.hasBeenActive) { try { navigator.vibrate(8); } catch (_) { /* ignored */ } }
    }
  }
}

function bubbleLoop(t) {
  const dt = clamp((t - bubbleLastTime) / 1000, 0, 1 / 30); bubbleLastTime = t;
  const stepCount = Math.max(1, Math.ceil(dt * 120));
  for (const B of [...liveBubbles]) {
    if (!B.group.isConnected || !B.group.offsetWidth) { restBubble(B); continue; }
    for (let i = 0; i < stepCount; i++) bubbleStep(B, dt / stepCount);
    drawBubble(B);
    const dragging = DRAG && DRAG.B === B && DRAG.started, o = bubbleMetrics(B);
    if (!dragging && B.cH === 0 && B.c < 0.001 && Math.abs(B.x - o.center(B.selected)) < 0.05 && Math.abs(B.vx) < 1
        && Math.abs(B.g) < 0.002 && Math.abs(B.vg) < 0.02 && B.e < 0.002) restBubble(B);
  }
  bubbleFrame = liveBubbles.size ? requestAnimationFrame(bubbleLoop) : 0;
}
function startBubble(B) {
  liveBubbles.add(B);
  if (!bubbleFrame) { bubbleLastTime = performance.now(); bubbleFrame = requestAnimationFrame(bubbleLoop); }
}
// Back to rest: inline sizes are removed, the position comes from CSS (--i) again; glass layers are removed
function restBubble(B) {
  liveBubbles.delete(B);
  Object.assign(B, { vx: 0, g: 0, vg: 0, c: 0, cH: 0, e: 0, mode: "settle" });
  for (const p of ["left", "top", "width", "height", "--c", "--isik", "--px"]) B.pill.style.removeProperty(p);
  B.group.removeAttribute("data-surukleniyor");
  if (B.hasMask) { B.buttons.forEach((b) => b.style.removeProperty("--delik")); B.hasMask = false; }
  removeLayers(B);
}

// From updateTabPill: the selection changed via click/keyboard/data flow → the bubble slides to its new place on a spring (no glass)
function bubbleSelectionChanged(group, previous, next) {
  const B = bubbles.get(group) || (previous !== next ? getBubble(group) : null);
  if (!B) return;
  const changed = B.selected !== next || previous !== next;
  B.selected = next;
  if (!changed || (DRAG && DRAG.B === B && DRAG.started)) return;          // while dragging the pointer decides the target
  if (!group.isConnected || !group.offsetWidth) { if (liveBubbles.has(B)) restBubble(B); return; }
  B.buttons = [...group.querySelectorAll(":scope > .sekme-btn")];
  if (!liveBubbles.has(B)) { B.x = bubbleMetrics(B).center(Math.min(previous, B.buttons.length - 1)); B.vx = 0; }
  B.mode = performance.now() - lastKeyboardSelect < 400 ? "keyboard" : "settle";
  B.cH = 0;
  startBubble(B);
}

const innerX = (B, clientX) => clientX - B.group.getBoundingClientRect().left - B.group.clientLeft;
function updateTarget(clientX) {
  const o = bubbleMetrics(DRAG.B);
  DRAG.px = innerX(DRAG.B, clientX);
  DRAG.target = clamp(DRAG.px - DRAG.offset, o.center(0), o.center(o.n - 1));
}
// Press and hold or drag: the bubble "lifts" and turns into glass; the grab point is preserved
function liftBubble(clientX) {
  if (!DRAG || DRAG.started) return;
  clearTimeout(DRAG.holdTimer);
  DRAG.started = true;
  const B = DRAG.B, o = bubbleMetrics(B);
  try { B.group.setPointerCapture(DRAG.id); } catch (_) { /* the pointer may already have been released */ }
  for (const D of liveBubbles) if (D !== B && D.c > 0) { D.c = D.cH = 0; drawBubble(D); }   // single filter: the previous glass fades immediately
  if (!liveBubbles.has(B)) { B.x = o.center(B.selected); B.vx = 0; }
  DRAG.offset = innerX(B, DRAG.x0) - o.center(DRAG.i);
  updateTarget(clientX);
  B.mode = "drag"; B.cH = glassDisabled() ? 0 : 1;
  if (B.cH) buildLayers(B);
  B.group.setAttribute("data-tutuluyor", "");
  startBubble(B);
}

function onDragStart(e) {
  if (e.button !== 0 || DRAG || !e.target.closest) return;
  const held = e.target.closest(".sekme-grubu > .sekme-btn, .sekme-grubu > .sekme-pil");
  if (!held) return;
  const group = held.parentElement;
  if (group.hasAttribute("data-gizli")) return;
  const B = getBubble(group);
  if (!B || B.buttons.length < 2) return;
  if (!liveBubbles.has(B)) B.selected = parseInt(group.style.getPropertyValue("--i"), 10) || 0;
  const i = held.classList.contains("sekme-pil") ? B.selected : B.buttons.indexOf(held);
  DRAG = { B, id: e.pointerId, x0: e.clientX, i, started: false, offset: 0, px: null, target: 0 };
  const x = e.clientX;
  DRAG.holdTimer = setTimeout(() => liftBubble(x), HOLD_MS);
}

function onDragMove(e) {
  if (!DRAG || e.pointerId !== DRAG.id) return;
  if (!DRAG.started) {
    if (Math.abs(e.clientX - DRAG.x0) < DRAG_START_PX) return;
    liftBubble(e.clientX);
  }
  e.preventDefault();
  updateTarget(e.clientX);
}

function onDragEnd(e) {
  if (!DRAG || e.pointerId !== DRAG.id) return;
  clearTimeout(DRAG.holdTimer);
  const { B, started } = DRAG;
  DRAG = null;
  if (!started) return; // short click: normal click flow (no glass)
  dragEndTime = performance.now();
  B.group.removeAttribute("data-tutuluyor");
  B.mode = "release"; B.cH = 0;                                          // selection already made; settle on the spring and flatten
  startBubble(B);
}

// Selection with arrow keys: with focus on a tab, ←/→ moves to the neighbour, Home/End to the ends, and selects.
function onTabKeydown(e) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
  const btn = e.target.closest && e.target.closest(".sekme-grubu > .sekme-btn");
  if (!btn) return;
  const buttons = [...btn.parentElement.querySelectorAll(":scope > .sekme-btn")];
  const i = buttons.indexOf(btn);
  const j = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1
    : Math.min(buttons.length - 1, Math.max(0, i + (e.key === "ArrowRight" ? 1 : -1)));
  e.preventDefault();
  if (j === i) return;
  buttons[j].focus();
  lastKeyboardSelect = performance.now();
  if (!buttons[j].classList.contains("aktif")) buttons[j].click();
}

function bindDrag() {
  document.addEventListener("pointerdown", onDragStart);
  document.addEventListener("pointermove", onDragMove, { passive: false });
  document.addEventListener("pointerup", onDragEnd);
  document.addEventListener("pointercancel", onDragEnd);
  document.addEventListener("keydown", onTabKeydown);
  document.addEventListener("click", (e) => {
    if (!e.target.closest) return;
    // Selection with Enter/Space (detail 0, not a drag): keyboard spring (no overshoot)
    if (e.detail === 0 && !(DRAG && DRAG.started) && e.target.closest(".sekme-grubu > .sekme-btn")) lastKeyboardSelect = performance.now();
    // Clicking the bubble or releasing a drag must not trigger the "open all" click of the card behind it.
    const afterDrag = e.isTrusted && !DRAG && performance.now() - dragEndTime < 350 && e.target.closest(".sekme-grubu");
    if (e.target.closest(".sekme-pil") || afterDrag) { e.stopPropagation(); e.preventDefault(); }
  }, true);
}

// ---------- Glass buttons (arrow, plus, pencil) ----------
// When a button is pressed (mouse, touch or Space/Enter) data-basili is set: style.css slightly enlarges and brightens it. It
// stays like that while held. The pointer is captured (setPointerCapture): even if it leaves the button before release, the release
// reaches us and the state returns to normal. A press released outside the button is not a click (native button behaviour). So
// that the growth is visible even on a very short tap, the pressed state lasts at least GLASS_PRESS_MIN_MS ms. It does not clash with
// the selection bubble's drag code (onDragStart): that only listens to elements inside .sekme-grubu.
const GLASS_PRESS_MIN_MS = 120;
function bindGlassButtons() {
  const state = new WeakMap();   // button -> { t0, timer }
  const active = new Map();       // pointer id -> pressed button (lets the release find the button even without capture)
  const begin = (btn, id) => {
    const d = state.get(btn) || {};
    clearTimeout(d.timer);
    d.t0 = performance.now(); d.timer = 0;
    state.set(btn, d);
    active.set(id, btn);
    btn.setAttribute("data-basili", "");
  };
  const release = (btn) => {
    const d = state.get(btn);
    if (!d || !btn.hasAttribute("data-basili")) return;
    clearTimeout(d.timer);
    const remaining = REDUCED_MOTION.matches ? 0 : Math.max(0, GLASS_PRESS_MIN_MS - (performance.now() - d.t0));
    d.timer = setTimeout(() => btn.removeAttribute("data-basili"), remaining);
  };
  const buttonOf = (e) => (e.target && e.target.closest ? e.target.closest(".cam-btn") : null);

  document.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const btn = buttonOf(e);
    if (!btn || btn.disabled) return;
    begin(btn, e.pointerId);
    try { btn.setPointerCapture(e.pointerId); } catch (_) { /* the pointer may already have been released */ }
  });
  const finish = (e) => {
    const btn = active.get(e.pointerId);
    if (!btn) return;
    active.delete(e.pointerId);
    const r = btn.getBoundingClientRect();
    const inside = e.type === "pointerup" && e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    if (e.type === "pointerup" && !inside) {
      // Because of the capture the browser still sends the click to the button; cancel it if released outside the button.
      const swallow = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
      document.addEventListener("click", swallow, { capture: true, once: true });
      setTimeout(() => document.removeEventListener("click", swallow, true), 60);
    }
    release(btn);
  };
  document.addEventListener("pointerup", finish);
  document.addEventListener("pointercancel", finish);
  // Keyboard: same look while Space/Enter is held
  document.addEventListener("keydown", (e) => {
    if ((e.key !== " " && e.key !== "Enter") || e.repeat) return;
    const btn = buttonOf(e);
    if (btn && !btn.disabled) begin(btn, -1);
  });
  document.addEventListener("keyup", (e) => {
    if (e.key !== " " && e.key !== "Enter") return;
    const btn = buttonOf(e);
    if (btn && active.get(-1) === btn) active.delete(-1);
    if (btn) release(btn);
  });
  document.addEventListener("focusout", (e) => { const btn = buttonOf(e); if (btn && active.get(-1) === btn) { active.delete(-1); release(btn); } });
}

// ---------- Scrollbar: thickens while scrolling ----------
// Every scrolled element (including the page) gets data-kaydiriyor while scrolling; it is removed SCROLL_END_MS ms after stopping.
// The look is in style.css (::-webkit-scrollbar-thumb): the total width is fixed, only the thumb's transparent border changes.
// The scroll event does not bubble; it is listened to in the capture phase. The wheel picker without a scrollbar (.wheel) is skipped.
const SCROLL_END_MS = 600;
function bindScrollbars() {
  const timer = new WeakMap();
  document.addEventListener("scroll", (e) => {
    const el = e.target === document ? document.documentElement : e.target;
    if (!el || el.nodeType !== 1 || el.classList.contains("wheel")) return;
    if (!el.hasAttribute("data-kaydiriyor")) el.setAttribute("data-kaydiriyor", "");
    clearTimeout(timer.get(el));
    timer.set(el, setTimeout(() => el.removeAttribute("data-kaydiriyor"), SCROLL_END_MS));
  }, { capture: true, passive: true });
}

function renderDonut() {
  document.querySelectorAll("#donut-sekmeleri [data-donut]").forEach((btn) => btn.classList.toggle("aktif", btn.dataset.donut === S.donutKind));
  updateTabPill(document.getElementById("donut-sekmeleri"), S.donutKind === "routine" ? 1 : 0);

  const data = S.donutData;
  const total = data.reduce((a, b) => a + b.count, 0);
  const allCount = (S.donutKind === "routine" ? S.routines : S.tasks).length;
  document.getElementById("donut-aciklama").textContent = msg(S.donutKind === "routine" ? "donut.captionRoutines" : "donut.captionTasks", { all: allCount, n: total });
  document.getElementById("donut-toplam").textContent = total;

  const targets = data.map((d) => d.percent);
  let shownValues = targets;
  if (S.donutPrevious && S.donutPrevious.length === targets.length) {
    const k = Math.min(1, (performance.now() - S.donutStartTime) / DONUT_DURATION);
    const e = easeInOutCubic(k);
    shownValues = S.donutPrevious.map((v, i) => v + (targets[i] - v) * e);
  }
  S.donutShownPercents = shownValues;

  const otherCount = data.filter((d) => d.other).length;
  const colors = data.map((d, i) => donutColor(d, i, data.length - otherCount));
  const donutEl = document.getElementById("donut-grafik");
  const separatorAngles = [];

  if (!data.length || total === 0) {
    donutEl.style.background = DONUT_EMPTY_COLOR;
  } else {
    let acc = 0;
    const stops = data.map((sliceItem, i) => {
      if (shownValues[i] > 0.01) separatorAngles.push(acc * 3.6);
      const part = `${colors[i]} ${acc.toFixed(2)}% ${(acc + shownValues[i]).toFixed(2)}%`;
      acc += shownValues[i];
      return part;
    });
    donutEl.style.background = `conic-gradient(${stops.join(",")})`;
  }
  // 2 px separator between slices (no separator with a single slice).
  drawDonutSeparators(donutEl, separatorAngles.length > 1 ? separatorAngles : []);
  donutEl.setAttribute("role", "img");
  donutEl.setAttribute("aria-label", data.length && total
    ? msg("donut.aria", { list: data.map((d) => msg("donut.slice", { name: d.category, pct: Math.round(d.percent) })).join(", ") })
    : msg("donut.ariaEmpty"));

  document.getElementById("donut-lejant").innerHTML = data.length ? data.map((sliceItem, i) => `
      <div class="donut-lejant-satir">
        <span class="donut-renk" style="background:${colors[i]}"></span>
        <span class="donut-lejant-ad">${escapeHtml(sliceItem.category)}</span>
        <span class="donut-lejant-yuzde">${Math.round(shownValues[i])}%</span>
      </div>`).join("") : `<div class="bos-durum" style="padding:8px 0">${escapeHtml(msg("empty.noCategories"))}</div>`;
}

// Separator lines: each is a 2 px radial piece of the ring from the centre outward (style.css .donut-ayirac).
function drawDonutSeparators(donutEl, angles) {
  let separators = donutEl.querySelectorAll(".donut-ayirac");
  while (separators.length < angles.length) {
    const el = document.createElement("i");
    el.className = "donut-ayirac";
    el.setAttribute("aria-hidden", "true");
    donutEl.appendChild(el);
    separators = donutEl.querySelectorAll(".donut-ayirac");
  }
  separators.forEach((el, i) => {
    el.hidden = i >= angles.length;
    if (i < angles.length) el.style.setProperty("--a", angles[i].toFixed(2) + "deg");
  });
}

function renderStreakList() {
  const list = document.getElementById("seri-liste");
  const rows = S.routinesByStreak.slice().sort((a, b) => displayStreak(b) - displayStreak(a));
  list.innerHTML = rows.length ? rows.map((r) => {
    const streak = displayStreak(r);
    const active = streak > 0 ? " aktif" : "";
    const flameColor = streak > 0 ? "var(--alev)" : "var(--metin-3)";
    const countColor = streak > 0 ? "var(--seri)" : "var(--metin-2)";
    return `
      <div class="seri-satir">
        <span class="alev-kutu${active}" style="color:${flameColor}">
          <svg width="16" height="18" viewBox="0 0 14 16" fill="currentColor" aria-hidden="true"><path d="M8.1.4c.35 2.05-.6 3.2-1.7 4.25C4.85 5.95 3.4 7.3 3.4 9.6c0 .95.3 1.8.85 2.5-.15-.5-.2-1-.1-1.5.25-1.25 1.25-2.1 2.2-2.9C7.5 6.75 8.3 5.8 8.4 4.6c1.4 1.35 2.2 3.05 2.2 4.9 0 .85-.15 1.6-.45 2.25.75-.75 1.25-1.85 1.25-3.2C11.4 5.3 10.1 2.2 8.1.4Z"></path><path d="M7.4 9.15c.15 1-.5 1.6-1.15 2.2-.55.5-1 1.1-1 1.95 0 1.5 1.2 2.3 2.5 2.3s2.5-.85 2.5-2.35c0-1.35-.75-2.35-1.6-3.25-.3.6-.65.9-1 .9-.15 0-.25-.6-.25-1.75Z"></path></svg>
        </span>
        <span class="seri-sayi${active}" style="color:${countColor}">${streak}</span>
        <span class="seri-ad" title="${escapeHtml(r.title).replace(/"/g, "&quot;")}">${escapeHtml(r.title)}</span>
      </div>`;
  }).join("") : `<div class="bos-durum">${escapeHtml(msg("empty.noStreaks"))}</div>`;
}

// ---------- Wheel picker ----------

function makeWheel(options, currentValue, onSelect, title, flexRatio) {
  const column = document.createElement("div");
  column.className = "tekerlek-kolon";
  column.style.flex = flexRatio || 1;

  if (title) {
    const titleEl = document.createElement("div");
    titleEl.className = "tekerlek-baslik";
    titleEl.textContent = title;
    column.appendChild(titleEl);
  }

  const highlight = document.createElement("div");
  highlight.className = "tekerlek-vurgu";
  column.appendChild(highlight);

  const wheelEl = document.createElement("div");
  wheelEl.className = "wheel";
  wheelEl.tabIndex = 0;
  if (title) wheelEl.setAttribute("aria-label", title);
  const optionEls = options.map((s) => {
    const opt = document.createElement("div");
    opt.className = "wheel-secenek" + (s.value === currentValue ? " secili" : "");
    opt.textContent = s.label;
    wheelEl.appendChild(opt);
    return opt;
  });
  column.appendChild(wheelEl);

  // Single source of truth targetIdx: every wheel notch/click/key advances it by as many steps as it scrolled
  // (no waiting in between). The on-screen scroll approaches the target with a continuous, smooth
  // animation; when it settles (and only then) the selection is reported via onSelect.
  const clampIndex = (i) => Math.max(0, Math.min(options.length - 1, i));
  let targetIdx = Math.max(0, options.findIndex((s) => s.value === currentValue));
  let pos = targetIdx * ROW;
  let anim = null;
  let isDragging = false;
  let animEnd = 0;
  let lastDragTime = 0;
  let touchTimer = null;
  requestAnimationFrame(() => { wheelEl.scrollTop = pos; });

  function updateHighlight() {
    optionEls.forEach((el, k) => el.classList.toggle("secili", k === targetIdx));
  }

  function startAnimation() {
    if (anim) return;
    let last = performance.now();
    const frame = (t) => {
      const dt = Math.min(48, t - last);
      last = t;
      const target = targetIdx * ROW;
      const diff = target - pos;
      if (Math.abs(diff) < 0.6) {
        pos = target;
        wheelEl.scrollTop = target;
        anim = null;
        animEnd = performance.now();
        if (options[targetIdx].value !== currentValue) onSelect(options[targetIdx].value);
        return;
      }
      pos += diff * (1 - Math.exp(-dt / WHEEL_TAU));
      wheelEl.scrollTop = pos;
      anim = requestAnimationFrame(frame);
    };
    anim = requestAnimationFrame(frame);
  }

  function goTo(i) {
    targetIdx = clampIndex(i);
    updateHighlight();
    if (!anim) pos = wheelEl.scrollTop;
    startAnimation();
  }

  // Mouse wheel: one notch = one step. Spinning fast advances the steps cumulatively.
  let accumulated = 0;
  wheelEl.addEventListener("wheel", (e) => {
    e.preventDefault();
    let dy = e.deltaY;
    if (e.deltaMode === 1) dy *= 33; else if (e.deltaMode === 2) dy *= 300;
    let step = 0;
    if (Math.abs(dy) >= 50) {
      step = Math.sign(dy) * Math.max(1, Math.round(Math.abs(dy) / 100));
      accumulated = 0;
    } else {
      // Fine-grained devices (touchpad): small values accumulate into a step.
      accumulated += dy;
      if (Math.abs(accumulated) >= 40) { step = Math.sign(accumulated); accumulated = 0; }
    }
    if (step) goTo(targetIdx + step);
  }, { passive: false });

  wheelEl.addEventListener("click", (e) => {
    if (Date.now() - lastDragTime < 250) return;
    const opt = e.target.closest(".wheel-secenek");
    if (!opt) return;
    goTo(optionEls.indexOf(opt));
  });

  // Touch/external scrolling: snap to the nearest option when it stops.
  wheelEl.addEventListener("scroll", () => {
    if (anim || isDragging || performance.now() - animEnd < 150) return;
    clearTimeout(touchTimer);
    touchTimer = setTimeout(() => goTo(Math.round(wheelEl.scrollTop / ROW)), 140);
  });

  wheelEl.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); goTo(targetIdx + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); goTo(targetIdx - 1); }
  });

  wheelEl.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    wheelEl.focus();
    if (anim) { cancelAnimationFrame(anim); anim = null; }
    isDragging = true;
    wheelEl.classList.add("suruklemede");
    const startY = e.clientY;
    const startScroll = wheelEl.scrollTop;
    let moved = false;

    function onMove(ev) {
      const diff = ev.clientY - startY;
      if (Math.abs(diff) > 3) moved = true;
      wheelEl.scrollTop = startScroll - diff;
    }
    function release() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", release);
      wheelEl.classList.remove("suruklemede");
      isDragging = false;
      if (moved) {
        lastDragTime = Date.now();
        pos = wheelEl.scrollTop;
        goTo(Math.round(wheelEl.scrollTop / ROW));
      }
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", release);
  });

  return column;
}

// Past moments never appear in the list; the date must always have gone through normalizeDate.
function buildDateWheels(date, onApply) {
  const e = earliestDate();
  const years = [];
  for (let y = e.year; y <= Math.max(e.year + 3, date.year); y++) years.push({ label: String(y), value: y });
  const months = MONTH_NAMES.map((name, i) => ({ label: name, value: i + 1 })).filter((a) => date.year !== e.year || a.value >= e.month);
  const sameMonth = date.year === e.year && date.month === e.month;
  const daysInMonth = new Date(date.year, date.month, 0).getDate();
  const days = [];
  for (let g = sameMonth ? e.day : 1; g <= daysInMonth; g++) days.push({ label: String(g), value: g });
  const sameDay = sameMonth && date.day === e.day;
  const hours = [];
  for (let s = sameDay ? e.hour : 0; s < 24; s++) hours.push({ label: pad2(s), value: s });
  const minutes = [];
  for (let d = (sameDay && date.hour === e.hour) ? e.minute : 0; d < 60; d += 5) minutes.push({ label: pad2(d), value: d });

  const change = (patch) => onApply(normalizeDate(Object.assign({}, date, patch)));

  return [
    makeWheel(years, date.year, (v) => change({ year: v }), msg("wheel.year"), 1.1),
    makeWheel(months, date.month, (v) => change({ month: v }), msg("wheel.month"), 1.5),
    makeWheel(days, date.day, (v) => change({ day: v }), msg("wheel.day"), 0.8),
    makeWheel(hours, date.hour, (v) => change({ hour: v }), msg("wheel.hour"), 0.8),
    makeWheel(minutes, date.minute, (v) => change({ minute: v }), msg("wheel.minute"), 0.8),
  ];
}

function quickOptions() {
  const now = new Date();
  const evening = new Date(now); evening.setHours(21, 0, 0, 0);
  const tomorrow = new Date(now); tomorrow.setDate(now.getDate() + 1); tomorrow.setHours(9, 0, 0, 0);
  const nextWeek = new Date(now); nextWeek.setDate(now.getDate() + 7); nextWeek.setHours(9, 0, 0, 0);
  return [
    { label: msg("quick.tonight"), date: evening, valid: evening > now },
    { label: msg("quick.tomorrow"), date: tomorrow, valid: true },
    { label: msg("quick.nextWeek"), date: nextWeek, valid: true },
  ];
}

// Wheels + "Selected: …" line + quick-pick chips.
function buildDatePicker(el, date, onApply) {
  el.wheels.innerHTML = "";
  buildDateWheels(date, onApply).forEach((k) => el.wheels.appendChild(k));
  el.selectedText.innerHTML = escapeHtml(msg("date.selected")) + " <b>" + escapeHtml(dateText(date)) + "</b>";
  const options = quickOptions();
  el.chips.innerHTML = options.map((h, i) => {
    const selected = h.valid && sameDate(dateFields(h.date), date);
    return `<button type="button" class="kategori-cip ${selected ? "secili" : ""}" data-hizli="${i}" ${h.valid ? "" : "disabled"}>${escapeHtml(h.label)}</button>`;
  }).join("");
  el.chips.onclick = (e) => {
    const btn = e.target.closest("[data-hizli]");
    if (!btn) return;
    onApply(normalizeDate(dateFields(options[Number(btn.dataset.hizli)].date)));
  };
}

// ---------- Modal (full list) ----------

function openModal(kind, startAdding, tab) {
  S.modal = kind;
  S.modalTab = tab || (startAdding ? "active" : (kind === "tasks" ? S.taskTab : S.routineTab));
  if (startAdding) resetAdd();
  document.getElementById("modal-overlay").hidden = false;
  renderModalList();
  if (startAdding) document.getElementById("ekleme-ad-input").focus();
}

function closeModal() {
  S.modal = null;
  document.getElementById("modal-overlay").hidden = true;
}

function modalRowHtml(item, kind, editMode, isSelected) {
  const done = !!item.done;
  const on = editMode ? isSelected : done;
  const mins = minutesLeft(item);
  const remainingText = done ? msg("row.done") : formatRemaining(mins);
  const remainingClass = done ? "bitti" : (mins < 0 ? "gecikti" : "");
  const nameClass = (done && !editMode) ? "bitmis" : "";
  const categoryTag = item.category ? `<span class="satir-kategori-etiket">${escapeHtml(item.category)}</span>` : "";
  const routineIcon = kind === "routines" ? routineIconHtml() : "";
  return `
    <div class="modal-satir ${isSelected ? "secili-satir" : ""}" data-id="${escapeHtml(item.id)}" role="button" tabindex="0">
      <span class="nokta ${on ? (editMode ? "secili" : "acik") : ""}">${on ? '<span class="tik' + (editMode ? " secim-tik" : "") + '">✓</span>' : ""}</span>
      <span class="satir-ad ${nameClass}">${routineIcon}<span class="ad-metin" title="${escapeHtml(item.title).replace(/"/g, "&quot;")}">${escapeHtml(item.title)}</span></span>
      ${categoryTag}
      <span class="satir-kalan ${remainingClass}">${remainingText}</span>
    </div>`;
}

function renderModalList() {
  const kind = S.modal;
  const editMode = kind === "tasks" ? S.taskEditMode : S.routineEditMode;
  const selection = kind === "tasks" ? S.taskSelection : S.routineSelection;
  const { list, baseCount } = prepareList(kind, S.modalTab);

  document.getElementById("modal-baslik").textContent = msg(kind === "routines" ? "card.routines" : "card.tasks");
  const filtered = S.filter[kind] !== "all";
  document.getElementById("modal-meta").textContent =
    msg("count.items", { n: list.length }) + (filtered ? " · " + filterLabel(S.filter[kind]) : "") + (editMode ? " · " + msg("modal.editing") : "");

  const tabsEl = document.getElementById("modal-sekmeleri");
  const tabs = ["active", "done", "all"];
  tabsEl.querySelectorAll("[data-modal-sekme]").forEach((btn) => btn.classList.toggle("aktif", btn.dataset.modalSekme === S.modalTab));
  updateTabPill(tabsEl, tabs.indexOf(S.modalTab));

  document.getElementById("modal-duzenle-ac-btn").hidden = editMode;
  document.getElementById("modal-duzenle-kapat-btn").hidden = !editMode;

  const listEl = document.getElementById("modal-liste");
  if (list.length) {
    listEl.innerHTML = list.map((o) => modalRowHtml(o, kind, editMode, selection.includes(o.id))).join("");
  } else if (baseCount) {
    listEl.innerHTML = `<div class="bos-durum">${escapeHtml(msg("empty.noFilterMatch"))}</div>`;
  } else {
    listEl.innerHTML = emptyStateHtml(kind, S.modalTab, S[kind].length, false);
  }

  document.getElementById("modal-duzenle-cubuk").hidden = !editMode;
  document.getElementById("modal-secim-etiketi").textContent = selection.length ? msg("sel.count", { n: selection.length }) : msg("sel.hint");
  updateSelectionButtons(document.getElementById("modal-sil-btn"), document.getElementById("modal-tamamla-btn"), selection.length, S.modalTab);

  renderAddArea();
}

// ---------- Add flow ----------

function resetAdd() {
  const inAnHour = new Date(Date.now() + 60 * 60000);
  inAnHour.setSeconds(0, 0);
  inAnHour.setMinutes(Math.ceil(inAnHour.getMinutes() / 5) * 5);
  S.addStep = "ad";
  S.addName = "";
  S.addDate = normalizeDate(dateFields(inAnHour));
  S.addFrequency = "1";
  S.addWeekdays = [];
  S.addCategory = "";
  S.addError = null;
}

function renderAddDatePicker() {
  S.addDate = normalizeDate(S.addDate);
  buildDatePicker({
    wheels: document.getElementById("ekleme-tekerlekler"),
    selectedText: document.getElementById("ekleme-secilen-tarih"),
    chips: document.getElementById("ekleme-hizli-cipler"),
  }, S.addDate, (newDate) => { S.addDate = newDate; renderAddDatePicker(); });
}

function categoryChipsHtml(selectedCategory) {
  return `<button type="button" class="kategori-cip yok ${selectedCategory ? "" : "secili"}" data-kategori="">${escapeHtml(msg("chips.none"))}</button>` +
    S.categories.map((k) => `<button type="button" class="kategori-cip ${k === selectedCategory ? "secili" : ""}" data-kategori="${escapeHtml(k)}">${escapeHtml(k)}</button>`).join("");
}

function renderAddCategoryChips() {
  document.getElementById("ekleme-kategori-cipler").innerHTML = categoryChipsHtml(S.addCategory);
}

function renderAddArea() {
  const nameInput = document.getElementById("ekleme-ad-input");
  const dateArea = document.getElementById("ekleme-tarih-alani");
  const commitBtn = document.getElementById("ekleme-commit-btn");
  const frequencyArea = document.getElementById("ekleme-siklik-alani");
  const kind = S.modal;
  const isRoutine = kind === "routines";

  nameInput.placeholder = msg(isRoutine ? "add.routinePlaceholder" : "add.taskPlaceholder");
  commitBtn.disabled = S.saving;

  // Frequency/day selection is synced with the state on every render (when the form resets the circles turn off too).
  if (isRoutine) {
    document.getElementById("ekleme-siklik-input").value = S.addFrequency;
    applyRepeatState(frequencyArea, S.addWeekdays);
    S.addFrequency = document.getElementById("ekleme-siklik-input").value;
  }

  if (S.addStep === "ad") {
    dateArea.hidden = true;
    nameInput.hidden = false;
    nameInput.value = S.addName;
    commitBtn.textContent = msg("add.pickDate");
  } else {
    nameInput.hidden = true;
    dateArea.hidden = false;
    commitBtn.textContent = msg("add.add");
    document.getElementById("ekleme-ad-onizleme").textContent = S.addName;
    document.getElementById("ekleme-tarih-soru").textContent = msg(isRoutine ? "add.routineQuestion" : "add.taskQuestion");
    const hint = document.getElementById("ekleme-tarih-ipucu");
    hint.hidden = !isRoutine;
    hint.textContent = msg("add.routineHint");
    frequencyArea.hidden = !isRoutine;
    renderAddDatePicker();
    renderAddCategoryChips();
  }

  const errorEl = document.getElementById("ekleme-hata");
  errorEl.hidden = !S.addError;
  errorEl.textContent = S.addError || "";
}

function addGoNext() {
  if (!S.addName.trim()) return;
  S.addStep = "tarih";
  renderAddArea();
}

async function saveAdd() {
  if (S.saving) return;
  const name = S.addName.trim();
  if (!name) return;
  const isRoutine = S.modal === "routines";
  const days = isRoutine ? S.addWeekdays.slice() : [];
  // If days are selected the frequency counts as 1 (they are mutually exclusive).
  const frequency = days.length ? 1 : parseFrequency(S.addFrequency);
  if (isRoutine && frequency == null) {
    S.addError = msg("err.frequencyInteger");
    renderAddArea();
    return;
  }
  const t = normalizeDate(S.addDate);
  const commitBtn = document.getElementById("ekleme-commit-btn");
  S.saving = true;
  commitBtn.disabled = true;
  try {
    const result = isRoutine
      ? await callApi("add_routine", name, frequency, t.year, t.month, t.day, t.hour, t.minute, S.addCategory, days)
      : await callApi("add_task", name, t.year, t.month, t.day, t.hour, t.minute, S.addCategory);
    if (!result.success) {
      S.addError = msg(result.error);
      return;
    }
    resetAdd();
    await refresh({ force: true });
    showToast(msg("toast.added", { name }));
  } finally {
    S.saving = false;
    commitBtn.disabled = false;
    if (S.modal) {
      renderAddArea();
      if (S.addStep === "ad") document.getElementById("ekleme-ad-input").focus();
    }
  }
}

// ---------- Detail panel ----------

function findDetailItem() {
  if (!S.detail) return null;
  const source = S.detail.kind === "routines" ? S.routines : S.tasks;
  return source.find((o) => o.id === S.detail.id) || null;
}

function showDetailError(message) {
  const el = document.getElementById("detay-hata");
  if (!el) return;
  el.hidden = false;
  el.textContent = message || msg("common.error");
}

async function updateDetail(item, fields) {
  if (S.saving) return false;
  S.saving = true;
  const buttons = document.querySelectorAll("#detay-kutu .ekle-btn");
  buttons.forEach((b) => { b.disabled = true; });
  let success = false;
  try {
    const result = await callApi("update_item", item.id, fields);
    if (!result.success) { showDetailError(msg(result.error)); return false; }
    S.detailEditing = null;
    await refresh({ force: true });
    success = true;
    return true;
  } finally {
    S.saving = false;
    // On error do not re-render the panel; otherwise the error message is cleared.
    if (success) renderDetail(); else buttons.forEach((b) => { b.disabled = false; });
  }
}

async function saveDetailName() {
  const item = findDetailItem();
  if (!item) return;
  const name = S.detailNameDraft.trim();
  if (!name) { showDetailError(msg("err.nameEmpty")); return; }
  await updateDetail(item, { title: name });
}

async function saveDetailDate() {
  const item = findDetailItem();
  if (!item) return;
  const t = normalizeDate(S.detailDateDraft);
  const fields = { year: t.year, month: t.month, day: t.day, hour: t.hour, minute: t.minute };
  if (S.detail.kind === "routines") {
    // If days are selected the frequency counts as 1; if the days are empty the weekly repeat is turned off.
    const frequency = S.detailWeekdays.length ? 1 : parseFrequency(S.detailFrequency);
    if (frequency == null) { showDetailError(msg("err.frequencyInteger")); return; }
    fields["frequency"] = frequency;
    fields["weekdays"] = S.detailWeekdays.slice();
  }
  await updateDetail(item, fields);
}

function toggleDetailEdit(field, item) {
  if (S.detailEditing === field) { S.detailEditing = null; renderDetail(); return; }
  S.detailEditing = field;
  if (field === "ad") S.detailNameDraft = item.title;
  if (field === "tarih") {
    S.detailDateWasPast = toDate(item) < new Date();
    S.detailDateDraft = normalizeDate({ year: item.year, month: item.month, day: item.day, hour: item.hour, minute: item.minute });
    S.detailWeekdays = (item.weekdays || []).slice();
    S.detailFrequency = String(item.frequency || 1);
  }
  renderDetail();
  if (field === "ad") {
    const input = document.getElementById("detay-ad-input");
    input.focus();
    input.select();
  }
}

function closeDetail() {
  S.detail = null;
  S.detailEditing = null;
  renderDetail();
}

function renderDetail() {
  const overlay = document.getElementById("detay-overlay");
  const box = document.getElementById("detay-kutu");
  const item = findDetailItem();
  if (!item) { overlay.hidden = true; return; }
  overlay.hidden = false;

  const isRoutine = S.detail.kind === "routines";
  const mins = minutesLeft(item);
  const remainingText = item.done ? msg("detail.completed") : formatRemaining(mins);
  const remainingColor = item.done ? "var(--basari)" : (mins < 0 ? "var(--tehlike)" : "var(--metin-1)");
  const editLabel = (field) => escapeHtml(msg(S.detailEditing === field ? "common.cancel" : "common.editPencil"));
  const dateValue = msg("date.dayMonthYearTime", { day: item.day, month: MONTH_NAMES[item.month - 1], year: item.year, time: `${pad2(item.hour)}:${pad2(item.minute)}` })
    + (isRoutine ? " · " + (item.weekdays && item.weekdays.length
      ? msg("detail.everyWeek", { days: weekdaysText(item.weekdays) })
      : msg("detail.everyNDays", { n: Number(item.frequency || 1) })) : "");

  box.innerHTML = `
    <div class="detay-ust">
      <div style="flex:1;min-width:0">
        <div class="etiket-kucuk">${escapeHtml(msg(isRoutine ? "detail.routine" : "detail.task"))}</div>
        <div class="detay-baslik">${escapeHtml(item.title)}</div>
      </div>
      <button class="metin-btn" id="detay-ad-duzenle-btn">${editLabel("ad")}</button>
      <button class="kapat-btn" id="detay-kapat-btn" title="${escapeAttr(msg("common.closeTitle"))}">${escapeHtml(msg("common.close"))}</button>
    </div>

    <div class="detay-ad-alani" id="detay-ad-alani" ${S.detailEditing === "ad" ? "" : "hidden"}>
      <input class="metin-input" id="detay-ad-input" style="flex:1;height:40px" value="${escapeHtml(S.detailNameDraft)}">
      <button class="ekle-btn" id="detay-ad-kaydet-btn" style="min-height:40px">${escapeHtml(msg("common.save"))}</button>
    </div>

    <div class="detay-satirlari">
      <div class="detay-satir">
        <span class="detay-etiket">${escapeHtml(msg("detail.timeLeft"))}</span>
        <span class="detay-deger" style="color:${remainingColor}">${remainingText}</span>
      </div>

      <div class="detay-satir tiklanabilir" data-detay-duzenle="tarih" role="button" tabindex="0">
        <span class="detay-etiket">${escapeHtml(msg(isRoutine ? "detail.cycleEnd" : "detail.due"))}</span>
        <span class="detay-deger">${escapeHtml(dateValue)}</span>
        <span class="metin-btn" style="display:inline-flex;align-items:center">${editLabel("tarih")}</span>
      </div>
      <div class="detay-duzenle-alani" ${S.detailEditing === "tarih" ? "" : "hidden"}>
        ${S.detailDateWasPast ? `<div class="tarih-notu">${escapeHtml(msg("detail.pastDateNote"))}</div>` : ""}
        <div class="secilen-tarih" id="detay-secilen-tarih"></div>
        <div class="hizli-cipler" id="detay-hizli-cipler"></div>
        <div class="tekerlek-satiri" id="detay-tekerlekler"></div>
        <div class="ipucu tarih-ipucu">${escapeHtml(msg("detail.wheelHint"))}</div>
        ${isRoutine ? `<div class="ekleme-bolum" id="detay-tekrar">${repeatBlockHtml("detay", S.detailFrequency)}</div>` : ""}
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:12px">
          <button class="ekle-btn kucuk" id="detay-tarih-kaydet-btn">${escapeHtml(msg("common.save"))}</button>
        </div>
      </div>

      <div class="detay-satir tiklanabilir" data-detay-duzenle="kategori" role="button" tabindex="0">
        <span class="detay-etiket">${escapeHtml(msg("detail.category"))}</span>
        <span style="flex:1;min-width:0">${item.category ? `<span class="satir-kategori-etiket">${escapeHtml(item.category)}</span>` : `<span style="color:var(--metin-2)">${escapeHtml(msg("common.none"))}</span>`}</span>
        <span class="metin-btn" style="display:inline-flex;align-items:center">${editLabel("kategori")}</span>
      </div>
      <div class="detay-duzenle-alani" ${S.detailEditing === "kategori" ? "" : "hidden"}>
        <div class="cip-listesi" id="detay-kategori-cipler"></div>
        <input class="metin-input" id="detay-kategori-yeni" placeholder="${escapeAttr(msg("category.newPlaceholder"))}" style="margin-top:12px">
      </div>

      <div class="hata-mesaji" id="detay-hata" hidden></div>
    </div>
  `;

  document.getElementById("detay-kapat-btn").addEventListener("click", closeDetail);
  document.getElementById("detay-ad-duzenle-btn").addEventListener("click", () => toggleDetailEdit("ad", item));
  box.querySelectorAll("[data-detay-duzenle]").forEach((detailRow) => {
    detailRow.addEventListener("click", () => toggleDetailEdit(detailRow.dataset.detayDuzenle, item));
  });

  if (S.detailEditing === "ad") {
    const input = document.getElementById("detay-ad-input");
    input.addEventListener("input", (e) => { S.detailNameDraft = e.target.value; });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") saveDetailName(); });
    document.getElementById("detay-ad-kaydet-btn").addEventListener("click", saveDetailName);
  }

  if (S.detailEditing === "tarih") {
    buildDatePicker({
      wheels: document.getElementById("detay-tekerlekler"),
      selectedText: document.getElementById("detay-secilen-tarih"),
      chips: document.getElementById("detay-hizli-cipler"),
    }, S.detailDateDraft, (next) => {
      S.detailDateDraft = next;
      renderDetail();
    });
    const repeatRoot = document.getElementById("detay-tekrar");
    if (repeatRoot) {
      applyRepeatState(repeatRoot, S.detailWeekdays);
      S.detailFrequency = repeatRoot.querySelector(".tekrar-siklik").value;
      bindRepeat(repeatRoot, () => S.detailWeekdays, (g) => { S.detailWeekdays = g; },
        () => { S.detailFrequency = repeatRoot.querySelector(".tekrar-siklik").value; });
    }
    document.getElementById("detay-tarih-kaydet-btn").addEventListener("click", saveDetailDate);
  }

  if (S.detailEditing === "kategori") {
    const container = document.getElementById("detay-kategori-cipler");
    container.innerHTML = categoryChipsHtml(item.category || "");
    container.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-kategori]");
      if (!btn) return;
      updateDetail(item, { category: btn.dataset.kategori });
    });
    document.getElementById("detay-kategori-yeni").addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      const name = e.target.value.trim();
      if (!name) return;
      const result = await callApi("add_category", name);
      S.categories = result.categories;
      if (!result.success && !result.categories.includes(name)) { showDetailError(msg(result.error)); return; }
      updateDetail(item, { category: name });
    });
  }
}

// ---------- Filter / sort picker ----------

function choiceChips(options, selected, attrName) {
  return '<div class="cip-listesi">' + options.map((s) =>
    `<button type="button" class="kategori-cip ${s.value === selected ? "secili" : ""}" data-${attrName}="${escapeHtml(s.value)}">${escapeHtml(s.label)}</button>`
  ).join("") + "</div>";
}

function pickerHint() {
  return `<div class="ipucu" style="margin-top:16px">${escapeHtml(msg("picker.hint"))}</div>`;
}

function openPicker(kind, which) {
  S.picker = which;
  S.pickerList = kind;
  renderPicker();
}

function renderPicker() {
  const overlay = document.getElementById("picker-overlay");
  const content = document.getElementById("picker-secenekler");
  if (!S.picker) { overlay.hidden = true; content.innerHTML = ""; return; }
  overlay.hidden = false;
  const kind = S.pickerList;
  const isRoutines = kind === "routines";

  if (S.picker === "filtre") {
    document.getElementById("picker-baslik").textContent = msg(isRoutines ? "picker.filterRoutines" : "picker.filterTasks");
    const options = [{ label: msg("filter.all"), value: "all" }, { label: msg("filter.uncategorized"), value: UNCATEGORIZED }]
      .concat(S.categories.map((k) => ({ label: k, value: k })));
    content.innerHTML = choiceChips(options, S.filter[kind], "filtre") + pickerHint();
  } else {
    document.getElementById("picker-baslik").textContent = msg(isRoutines ? "picker.sortRoutines" : "picker.sortTasks");
    const fields = isRoutines ? ["remaining", "name", "category", "streak"] : ["remaining", "name", "category"];
    content.innerHTML = `
      <div class="secim-grubu">
        <div class="etiket-kucuk">${escapeHtml(msg("picker.sortBy"))}</div>
        ${choiceChips(fields.map((a) => ({ label: msg("sort.field." + a), value: a })), S.sortBy[kind], "sirala")}
      </div>
      <div class="secim-grubu">
        <div class="etiket-kucuk">${escapeHtml(msg("picker.direction"))}</div>
        <div class="sekme-grubu" id="picker-yon">
          <div class="sekme-pil"></div>
          <button class="sekme-btn ${S.sortDir[kind] === "asc" ? "aktif" : ""}" data-yon="asc">${escapeHtml(msg("sort.dir.asc"))}</button>
          <button class="sekme-btn ${S.sortDir[kind] === "desc" ? "aktif" : ""}" data-yon="desc">${escapeHtml(msg("sort.dir.desc"))}</button>
        </div>
      </div>${pickerHint()}`;
    updateTabPill(document.getElementById("picker-yon"), S.sortDir[kind] === "desc" ? 1 : 0);
  }

  // The selection is updated in place without re-rendering the window (so the sliding tab animation is not broken).
  // Clicking the already selected filter/sort again turns it off (back to the default).
  content.onclick = (e) => {
    const btn = e.target.closest("[data-filtre],[data-sirala],[data-yon]");
    if (!btn) return;
    if (btn.dataset.filtre != null) {
      S.filter[kind] = btn.dataset.filtre === S.filter[kind] ? "all" : btn.dataset.filtre;
    } else if (btn.dataset.sirala != null) {
      if (btn.dataset.sirala === S.sortBy[kind] && !(S.sortBy[kind] === "remaining" && S.sortDir[kind] === "asc")) {
        S.sortBy[kind] = "remaining";
        S.sortDir[kind] = "asc";
      } else {
        S.sortBy[kind] = btn.dataset.sirala;
      }
    } else {
      S.sortDir[kind] = btn.dataset.yon;
    }

    content.querySelectorAll("[data-filtre]").forEach((el) => el.classList.toggle("secili", el.dataset.filtre === S.filter[kind]));
    content.querySelectorAll("[data-sirala]").forEach((el) => el.classList.toggle("secili", el.dataset.sirala === S.sortBy[kind]));
    const direction = document.getElementById("picker-yon");
    if (direction) {
      direction.querySelectorAll("[data-yon]").forEach((el) => el.classList.toggle("aktif", el.dataset.yon === S.sortDir[kind]));
      updateTabPill(direction, S.sortDir[kind] === "desc" ? 1 : 0);
    }
    renderCard(kind);
    if (S.modal === kind) renderModalList();
  };
}

function closePicker() {
  S.picker = null;
  S.pickerList = null;
  renderPicker();
}
// ---------- Event binding ----------

function showCategoryError(message) {
  const el = document.getElementById("kategori-hata");
  el.hidden = !message;
  el.textContent = message || "";
}

function bindEvents() {
  document.getElementById("tasks-card").addEventListener("click", (e) => onCardClick("tasks", e));
  document.getElementById("routines-card").addEventListener("click", (e) => onCardClick("routines", e));

  document.getElementById("kategori-duzenle-ac").addEventListener("click", () => { S.categoryEditMode = true; S.categorySelection = []; renderCategoryCard(); });
  document.getElementById("kategori-duzenle-kapat").addEventListener("click", () => { S.categoryEditMode = false; S.categorySelection = []; renderCategoryCard(); });
  document.getElementById("kategori-ekle-ac").addEventListener("click", () => {
    S.categoryAddOpen = !S.categoryAddOpen;
    document.getElementById("kategori-ekleme-alani").hidden = !S.categoryAddOpen;
    showCategoryError(null);
    if (S.categoryAddOpen) document.getElementById("kategori-yeni-input").focus();
  });
  document.getElementById("kategori-yeni-input").addEventListener("input", () => showCategoryError(null));
  document.getElementById("kategori-yeni-input").addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const name = e.target.value.trim();
    if (!name) return;
    const result = await callApi("add_category", name);
    if (!result.success) { showCategoryError(msg(result.error)); return; }
    e.target.value = "";
    S.categoryAddOpen = false;
    document.getElementById("kategori-ekleme-alani").hidden = true;
    await refresh({ force: true });
  });
  document.getElementById("kategori-sil-btn").addEventListener("click", async () => {
    const count = S.categorySelection.length;
    if (!count) return;
    for (const name of S.categorySelection) await callApi("delete_category", name);
    S.categorySelection = [];
    await refresh({ force: true });
    showToast(msg("toast.categoriesDeleted", { n: count }));
  });
  document.getElementById("kategori-liste").addEventListener("click", (e) => {
    if (!S.categoryEditMode) return;
    const row = e.target.closest("[data-kategori]");
    if (!row) return;
    const name = row.dataset.kategori;
    const idx = S.categorySelection.indexOf(name);
    if (idx >= 0) S.categorySelection.splice(idx, 1); else S.categorySelection.push(name);
    renderCategoryCard();
  });

  document.getElementById("grafik-sekmeleri").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-grafik]");
    if (!btn || btn.dataset.grafik === S.chartKind) return;
    S.chartKind = btn.dataset.grafik;
    S.chartOffset = 0;
    refreshCharts();
  });
  document.getElementById("donem-onceki").addEventListener("click", () => { S.chartOffset -= 1; refreshCharts(); });
  document.getElementById("donem-sonraki").addEventListener("click", () => {
    if (S.chartOffset >= 0) return;
    S.chartOffset += 1;
    refreshCharts();
  });
  document.getElementById("donut-sekmeleri").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-donut]");
    if (!btn) return;
    S.donutKind = btn.dataset.donut;
    refreshDonut();
  });

  document.getElementById("modal-overlay").addEventListener("click", (e) => { if (e.target.id === "modal-overlay") closeModal(); });
  document.getElementById("modal-kutu").addEventListener("click", (e) => e.stopPropagation());
  document.getElementById("modal-kapat-btn").addEventListener("click", closeModal);
  document.getElementById("modal-sekmeleri").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-modal-sekme]");
    if (!btn) return;
    S.modalTab = btn.dataset.modalSekme;
    renderModalList();
  });
  document.getElementById("modal-liste").addEventListener("click", (e) => {
    const row = e.target.closest("[data-id]");
    if (!row) return;
    const kind = S.modal;
    onRowClick(kind, row.dataset.id, kind === "tasks" ? S.taskEditMode : S.routineEditMode);
  });
  document.getElementById("modal-duzenle-ac-btn").addEventListener("click", () => setEditMode(S.modal, true));
  document.getElementById("modal-duzenle-kapat-btn").addEventListener("click", () => setEditMode(S.modal, false));
  document.getElementById("modal-sil-btn").addEventListener("click", () => deleteSelected(S.modal));
  document.getElementById("modal-tamamla-btn").addEventListener("click", () => completeSelected(S.modal));

  document.getElementById("picker-tamam-btn").addEventListener("click", closePicker);
  document.getElementById("picker-overlay").addEventListener("click", (e) => { if (e.target.id === "picker-overlay") closePicker(); });

  document.getElementById("ekleme-ad-input").addEventListener("input", (e) => { S.addName = e.target.value; });
  document.getElementById("ekleme-ad-input").addEventListener("keydown", (e) => { if (e.key === "Enter") addGoNext(); });
  document.getElementById("ekleme-commit-btn").addEventListener("click", () => { if (S.addStep === "ad") addGoNext(); else saveAdd(); });
  document.getElementById("ekleme-geri-btn").addEventListener("click", () => { S.addStep = "ad"; S.addError = null; renderAddArea(); document.getElementById("ekleme-ad-input").focus(); });
  const addRepeatRoot = document.getElementById("ekleme-siklik-alani");
  addRepeatRoot.innerHTML = repeatBlockHtml("ekleme", "1");
  bindRepeat(addRepeatRoot, () => S.addWeekdays, (g) => { S.addWeekdays = g; },
    () => { S.addFrequency = addRepeatRoot.querySelector(".tekrar-siklik").value; });
  document.getElementById("ekleme-kategori-cipler").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-kategori]");
    if (!btn) return;
    const k = btn.dataset.kategori;
    S.addCategory = (k && k === S.addCategory) ? "" : k;
    renderAddCategoryChips();
  });
  document.getElementById("ekleme-kategori-yeni").addEventListener("keydown", async (e) => {
    if (e.key !== "Enter") return;
    const name = e.target.value.trim();
    if (!name) return;
    const result = await callApi("add_category", name);
    S.categories = result.categories;
    if (!result.success && !result.categories.includes(name)) {
      S.addError = msg(result.error);
      renderAddArea();
      return;
    }
    S.addCategory = name;
    S.addError = null;
    e.target.value = "";
    renderAddCategoryChips();
    document.getElementById("ekleme-hata").hidden = true;
  });

  document.getElementById("detay-overlay").addEventListener("click", (e) => {
    if (e.target.id === "detay-overlay") closeDetail();
  });

  bindTooltips();
  bindDrag();
  bindGlassButtons();
  bindScrollbars();

  // Fullscreen: button or F11 (the window frame/title bar disappears in fullscreen).
  const toggleFullscreen = () => { callApi("toggle_fullscreen").catch(() => {}); };
  document.getElementById("tam-ekran-btn").addEventListener("click", toggleFullscreen);

  document.addEventListener("keydown", (e) => {
    if (e.key === "F11") { e.preventDefault(); toggleFullscreen(); return; }
    if (e.key === "Escape") {
      if (S.picker) { closePicker(); return; }
      if (S.detail) { closeDetail(); return; }
      if (S.modal) { closeModal(); return; }
      return;
    }
    // Clickable rows that are not buttons should open with the keyboard too.
    if ((e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches('[role="button"]:not(button)')) {
      e.preventDefault();
      e.target.click();
    }
  });
}

// ---------- Start ----------

function init() {
  updateClock();
  setInterval(updateClock, 1000);
  bindEvents();
  refresh();
  setInterval(refresh, 60000);
}

// Translations (i18n.js) are loaded before the first render.
function boot() {
  I18N.ready.then(init);
}

if (window.pywebview) {
  boot();
} else {
  window.addEventListener("pywebviewready", boot);
}
