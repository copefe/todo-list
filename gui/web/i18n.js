// UI translations. Loaded synchronously in <head>, before app.js.
//
// Language: ?lang= (from TODO_LANG), then localStorage "todo.lang" ("tr" | "en", optional developer override; no UI for it), otherwise
// navigator.language — Turkish if it starts with "tr", English otherwise.
// Messages: flat key → text maps in locales/<lang>.json. "{name}" placeholders are filled from params; when
// params.n is a number, "<key>_one" / "<key>_other" (Intl.PluralRules) are tried before "<key>".
// Missing keys fall back to English, then to the key itself.
// Static markup: data-i18n (text), data-i18n-title, data-i18n-aria-label, data-i18n-placeholder.
// Month/day names come from Intl for the selected language.
(function () {
  const SUPPORTED = ["tr", "en"];
  const STORAGE_KEY = "todo.lang";

  function detectLanguage() {
    // ?lang=en|tr: set by app.py / demo_app.py from the TODO_LANG environment variable (testing aid).
    try {
      const fromUrl = new URLSearchParams(window.location.search).get("lang");
      if (SUPPORTED.includes(fromUrl)) return fromUrl;
    } catch (_) { /* ignore */ }
    try {
      const forced = window.localStorage.getItem(STORAGE_KEY);
      if (SUPPORTED.includes(forced)) return forced;
    } catch (_) { /* storage may be unavailable */ }
    return /^tr\b/i.test(navigator.language || "") ? "tr" : "en";
  }

  const LANG = detectLanguage();
  const root = document.documentElement;
  root.lang = LANG;

  // Avoid a flash of the built-in Turkish markup before English texts are applied (Turkish is never hidden).
  let revealTimer = 0;
  if (LANG !== "tr") {
    root.style.visibility = "hidden";
    revealTimer = setTimeout(reveal, 1500);
  }
  function reveal() {
    clearTimeout(revealTimer);
    root.style.removeProperty("visibility");
  }

  let messages = {};
  let fallback = {};
  const plural = new Intl.PluralRules(LANG);

  function lookup(key, n) {
    for (const table of [messages, fallback]) {
      if (typeof n === "number") {
        const form = `${key}_${plural.select(n)}`;
        if (table[form] != null) return table[form];
        if (table[`${key}_other`] != null) return table[`${key}_other`];
      }
      if (table[key] != null) return table[key];
    }
    return null;
  }

  function t(key, params) {
    const text = lookup(key, params && params.n);
    if (text == null) return key;
    return params ? text.replace(/\{(\w+)\}/g, (m, p) => (p in params ? String(params[p]) : m)) : text;
  }

  function applyStatic(scope) {
    const base = scope || document;
    const set = (attr, apply) => base.querySelectorAll(`[${attr}]`).forEach((el) => {
      const text = lookup(el.getAttribute(attr));
      if (text != null) apply(el, text);
    });
    set("data-i18n", (el, text) => { el.textContent = text; });
    set("data-i18n-title", (el, text) => el.setAttribute("title", text));
    set("data-i18n-aria-label", (el, text) => el.setAttribute("aria-label", text));
    set("data-i18n-placeholder", (el, text) => el.setAttribute("placeholder", text));
  }

  async function load(lang) {
    const r = await fetch(`locales/${lang}.json`, { cache: "no-store" });
    if (!r.ok) throw new Error(`locales/${lang}.json: ${r.status}`);
    return r.json();
  }

  const names = (opts, count, date) => [...Array(count)].map((_, i) => new Intl.DateTimeFormat(LANG, opts).format(date(i)));
  const sundayFirst = (opts) => names(opts, 7, (i) => new Date(2000, 0, 2 + i)); // 2000-01-02 is a Sunday
  const mondayFirst = (opts) => { const d = sundayFirst(opts); return d.slice(1).concat(d[0]); };

  const ready = Promise.all([
    load(LANG).catch((e) => { console.warn(e); return {}; }),
    LANG === "en" ? Promise.resolve(null) : load("en").catch(() => ({})),
  ]).then(([own, en]) => {
    messages = own;
    fallback = en || own;
    return new Promise((resolve) => {
      const apply = () => { applyStatic(); reveal(); resolve(); };
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", apply, { once: true });
      else apply();
    });
  });

  window.I18N = Object.freeze({
    lang: LANG,
    t,
    ready,
    applyStatic,
    monthNames: names({ month: "long" }, 12, (i) => new Date(2000, i, 1)),
    dayNames: sundayFirst({ weekday: "long" }),            // Sunday first (Date.getDay order)
    weekdayNames: mondayFirst({ weekday: "long" }),        // Monday first
    weekdayShort: mondayFirst({ weekday: "short" }),
    weekdayLetters: mondayFirst({ weekday: "narrow" }),
  });
})();
