"""Browser snapshot: python ui_snapshot.py <base_url> <locale> <out.json> [fixed_epoch_ms]  (used by run_check.py)

1) Snapshot pass (clock frozen): walks through UI states and records every visible text line plus
   title / aria-label / placeholder attributes, for old-vs-new comparison.
2) Bubble pass (real clock): press-hold-drag on a tab group, checks glass state, live selection, settle.
3) Overflow pass: every tab label must fit in its column.
Console errors and page errors are collected and reported.
"""
import datetime
import json
import sys

from playwright.sync_api import sync_playwright

base, locale, out = sys.argv[1], sys.argv[2], sys.argv[3]
fixed = int(sys.argv[4]) if len(sys.argv) > 4 else None

SHIM = """
window.pywebview = { api: new Proxy({}, { get: (_, m) => async (...args) => {
  const r = await fetch('/__api/' + m, { method: 'POST', body: JSON.stringify(args) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
} }) };
"""

SNAP_JS = """() => {
  const lines = document.body.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
  const attrs = [];
  document.querySelectorAll('[title],[aria-label],[placeholder]').forEach(el => {
    for (const a of ['title', 'aria-label', 'placeholder']) if (el.hasAttribute(a)) attrs.push(a + '=' + el.getAttribute(a));
  });
  return { lines, attrs, lang: document.documentElement.lang, title: document.title };
}"""

errors = []
result = {"states": {}, "errors": errors, "checks": {}}


def attach(page):
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))


def snap(page, name):
    page.wait_for_timeout(250)
    result["states"][name] = page.evaluate(SNAP_JS)


def card(page, i):
    return page.locator(".kart[data-tur]").nth(i)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)

    # ---------------- snapshot pass ----------------
    ctx = browser.new_context(locale=locale, viewport={"width": 1320, "height": 880})
    ctx.add_init_script(SHIM)
    page = ctx.new_page()
    attach(page)
    if fixed:
        page.clock.set_fixed_time(datetime.datetime.fromtimestamp(fixed / 1000))
    page.goto(base + "/index.html")
    page.wait_for_selector(".kart[data-tur] .satir")
    snap(page, "01-initial")

    page.hover(".bar-sutun >> nth=3"); snap(page, "02-weekly-tooltip")
    page.mouse.move(5, 5)
    page.click("#donem-onceki"); page.wait_for_timeout(300); snap(page, "03-prev-week")
    page.click("#grafik-sekmeleri .sekme-btn >> nth=1"); page.wait_for_timeout(300); snap(page, "04-monthly")
    page.hover(".isi-hucre >> nth=2"); snap(page, "05-monthly-tooltip")
    page.mouse.move(5, 5)
    page.click("#donem-onceki"); page.wait_for_timeout(300); snap(page, "06-prev-month")
    page.click("#donem-sonraki"); page.wait_for_timeout(300); snap(page, "06b-this-month")
    page.click("#donut-sekmeleri .sekme-btn >> nth=1"); page.wait_for_timeout(300); snap(page, "07-donut-routine")

    card(page, 0).locator('[data-rol="sekmeler"] .sekme-btn').nth(1).click(); snap(page, "08-tasks-done-tab")
    card(page, 0).locator('[data-rol="sekmeler"] .sekme-btn').nth(0).click()
    card(page, 0).locator('[data-rol="duzenle-ac"]').click(); snap(page, "09-edit-mode")
    card(page, 0).locator(".satir").nth(0).click(); snap(page, "10-edit-selected")
    card(page, 0).locator('[data-rol="duzenle-kapat"]').click()

    card(page, 0).locator('[data-rol="tumunu-gor"]').click(); snap(page, "11-modal-all")
    page.click("#modal-sekmeleri .sekme-btn >> nth=0"); snap(page, "12-modal-active")
    page.click("#modal-duzenle-ac-btn"); snap(page, "13-modal-edit")
    page.click("#modal-liste .modal-satir >> nth=0"); snap(page, "14-modal-edit-selected")
    page.click("#modal-duzenle-kapat-btn")
    page.keyboard.press("Escape")

    card(page, 1).locator('[data-rol="ekle-ac"]').click(); snap(page, "15-add-routine-name")
    page.fill("#ekleme-ad-input", "Test")
    page.press("#ekleme-ad-input", "Enter"); snap(page, "16-add-routine-date")
    page.click("#ekleme-siklik-alani .gun-daire >> nth=1"); snap(page, "17-add-routine-weekday")
    page.click("#ekleme-siklik-alani .gun-daire >> nth=1")
    page.click("#ekleme-siklik-alani .sayac-btn >> nth=1"); snap(page, "18-add-routine-freq")
    page.fill("#ekleme-kategori-yeni", "Spor"); page.press("#ekleme-kategori-yeni", "Enter"); snap(page, "19-add-existing-cat")
    page.keyboard.press("Escape")

    card(page, 0).locator(".satir").nth(0).click(); snap(page, "20-detail-task")
    page.click('[data-detay-duzenle="tarih"]'); snap(page, "21-detail-date")
    page.click('[data-detay-duzenle="kategori"]'); snap(page, "22-detail-category")
    page.click("#detay-ad-duzenle-btn"); snap(page, "23-detail-name")
    page.fill("#detay-ad-input", "   "); page.click("#detay-ad-kaydet-btn"); snap(page, "24-detail-empty-name")
    page.keyboard.press("Escape")
    card(page, 1).locator(".satir").nth(0).click(); snap(page, "25-detail-routine")
    page.click('[data-detay-duzenle="tarih"]'); snap(page, "26-detail-routine-date")
    page.keyboard.press("Escape")

    card(page, 0).locator('[data-rol="filtre"]').click(); snap(page, "27-filter-picker")
    page.click("#picker-secenekler [data-filtre] >> nth=2"); snap(page, "28-filter-set")
    page.click("#picker-tamam-btn"); snap(page, "29-filter-applied")
    card(page, 0).locator('[data-rol="filtre"]').click()
    page.click("#picker-secenekler [data-filtre] >> nth=1"); page.click("#picker-tamam-btn"); snap(page, "30-filter-uncategorized")
    card(page, 0).locator('[data-rol="filtre"]').click()
    page.click("#picker-secenekler [data-filtre] >> nth=0"); page.click("#picker-tamam-btn")
    card(page, 1).locator('[data-rol="sirala"]').click(); snap(page, "31-sort-picker")
    page.click("#picker-secenekler [data-sirala] >> nth=3"); page.click("#picker-yon .sekme-btn >> nth=1"); snap(page, "32-sort-set")
    page.click("#picker-tamam-btn"); snap(page, "33-sort-applied")

    page.click("#kategori-ekle-ac"); page.fill("#kategori-yeni-input", "Spor"); page.press("#kategori-yeni-input", "Enter"); snap(page, "34-cat-exists")
    page.click("#kategori-duzenle-ac"); page.click("#kategori-liste .satir >> nth=0"); snap(page, "35-cat-edit")
    page.click("#kategori-duzenle-kapat")

    card(page, 0).locator('[data-rol="duzenle-ac"]').click()
    card(page, 0).locator(".satir").nth(0).click()
    card(page, 0).locator('[data-rol="tamamla"]').click(); page.wait_for_timeout(500); snap(page, "36-completed-toast")
    ctx.close()

    # ---------------- bubble pass ----------------
    ctx = browser.new_context(locale=locale, viewport={"width": 1320, "height": 880})
    ctx.add_init_script(SHIM)
    page = ctx.new_page()
    attach(page)
    page.goto(base + "/index.html")
    page.wait_for_selector(".kart[data-tur] .satir")
    page.wait_for_timeout(500)
    grp = card(page, 1).locator('[data-rol="sekmeler"]')
    b0 = grp.locator(".sekme-btn").nth(0).bounding_box()
    b1 = grp.locator(".sekme-btn").nth(1).bounding_box()
    y = b0["y"] + b0["height"] / 2
    page.mouse.move(b0["x"] + b0["width"] / 2, y)
    page.mouse.down()
    page.wait_for_timeout(400)
    held = grp.evaluate("g => ({tut: g.hasAttribute('data-tutuluyor'), sur: g.hasAttribute('data-surukleniyor'), lens: !!g.querySelector('.pil-mercek'), copies: [...g.querySelectorAll('.pil-kopya > span')].map(s => s.textContent)})")
    steps = 12
    for k in range(1, steps + 1):
        page.mouse.move(b0["x"] + b0["width"] / 2 + (b1["x"] - b0["x"]) * k / steps, y)
        page.wait_for_timeout(30)
    mid = grp.evaluate("g => ({active: [...g.querySelectorAll('.sekme-btn')].findIndex(b => b.classList.contains('aktif')), sur: g.hasAttribute('data-surukleniyor')})")
    page.mouse.up()
    page.wait_for_timeout(1500)
    rest = grp.evaluate("g => ({active: [...g.querySelectorAll('.sekme-btn')].findIndex(b => b.classList.contains('aktif')), layers: g.querySelectorAll('.pil-katman').length, sur: g.hasAttribute('data-surukleniyor'), inline: g.querySelector('.sekme-pil').style.left, i: g.style.getPropertyValue('--i')})")
    # short click back: slides without glass
    grp.locator(".sekme-btn").nth(0).click()
    page.wait_for_timeout(100)
    clickmid = grp.evaluate("g => ({sur: g.hasAttribute('data-surukleniyor'), layers: g.querySelectorAll('.pil-katman').length})")
    page.wait_for_timeout(1200)
    clickrest = grp.evaluate("g => ({active: [...g.querySelectorAll('.sekme-btn')].findIndex(b => b.classList.contains('aktif')), inline: g.querySelector('.sekme-pil').style.left})")
    result["checks"]["bubble"] = {"held": held, "mid": mid, "rest": rest, "clickmid": clickmid, "clickrest": clickrest}
    ok = (held["tut"] and held["lens"] and held["sur"] and mid["active"] == 1 and rest["active"] == 1 and rest["layers"] == 0
          and not rest["sur"] and rest["inline"] == "" and not clickmid["sur"] and clickmid["layers"] == 0
          and clickrest["active"] == 0 and clickrest["inline"] == "")
    result["checks"]["bubble_ok"] = bool(ok)

    # ---------------- overflow pass ----------------
    page.click("#donut-sekmeleri .sekme-btn >> nth=0")
    card(page, 0).locator('[data-rol="tumunu-gor"]').click()
    page.wait_for_timeout(300)
    ov = page.evaluate("""() => [...document.querySelectorAll('.sekme-grubu')].filter(g => g.offsetWidth).map(g => ({
        id: g.id || g.dataset.rol, w: g.clientWidth,
        btns: [...g.querySelectorAll(':scope > .sekme-btn')].map(b => ({t: b.textContent.trim(), sw: b.scrollWidth, cw: b.clientWidth}))
    }))""")
    page.keyboard.press("Escape")
    card(page, 1).locator('[data-rol="sirala"]').click(); page.wait_for_timeout(300)
    ov += page.evaluate("""() => [...document.querySelectorAll('#picker-yon')].map(g => ({
        id: g.id, w: g.clientWidth,
        btns: [...g.querySelectorAll(':scope > .sekme-btn')].map(b => ({t: b.textContent.trim(), sw: b.scrollWidth, cw: b.clientWidth}))
    }))""")
    result["checks"]["tabs"] = ov
    result["checks"]["tabs_ok"] = all(b["sw"] <= b["cw"] for g in ov for b in g["btns"])
    ctx.close()
    browser.close()

json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("errors:", len(errors), errors[:5])
print("bubble_ok:", result["checks"]["bubble_ok"], "tabs_ok:", result["checks"]["tabs_ok"])
