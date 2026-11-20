"""Makes the README screenshots (PNG) and the demo GIF from the sample data. Not part of the tests.

    python tests/browser/make_screenshots.py            # writes docs/screenshots/*.png and demo.gif
    python tests/browser/make_screenshots.py <out_dir>

English UI, sample data in a temporary folder (real data is never touched), headless Edge through
Playwright (pip install -r requirements-dev.txt). The GIF needs Pillow (pip install pillow; not a
project dependency). Note: this renders in Chromium/Edge, the desktop app uses the Edge WebView2
runtime, so the glass effects can look slightly different there.
"""
import json, os, subprocess, sys, tempfile, time, shutil, socket
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
HERE = ROOT / "tests" / "browser"
tmp = Path(tempfile.mkdtemp(prefix="todolist-shots-"))
data = tmp / "data"; data.mkdir()
env = dict(os.environ, TODO_DATA_DIR=str(data), TODO_LANG="en")
subprocess.run([sys.executable, "-c", "import storage, sample_data; assert str(storage.DATA_DIR)==%r; sample_data.create_demo_data('en')" % str(data)],
               cwd=ROOT / "gui", env=env, check=True)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
server = subprocess.Popen([sys.executable, str(HERE / "serve.py"), str(ROOT / "gui"), str(port), str(data)], env=env)
SHIM = """window.pywebview = { api: new Proxy({}, { get: (_, m) => async (...a) => {
  const r = await fetch('/__api/' + m, { method: 'POST', body: JSON.stringify(a) });
  if (!r.ok) throw new Error(await r.text()); return r.json(); } }) };"""
errors = []
frames = []
try:
    for _ in range(60):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0: break
        time.sleep(0.2)
    base = f"http://127.0.0.1:{port}/index.html?lang=en"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(locale="en-US", viewport={"width": 1400, "height": 1000})
        ctx.add_init_script(SHIM)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base); page.wait_for_selector(".kart[data-tur] .satir")
        page.evaluate("document.fonts.ready"); page.wait_for_timeout(1200)
        card = lambda i: page.locator(".kart[data-tur]").nth(i)
        shot = lambda name: (page.mouse.move(2, 2), page.wait_for_timeout(400), page.screenshot(path=str(OUT / name)))
        shot("01-task-list.png")
        page.hover(".bar-sutun >> nth=3"); page.wait_for_timeout(400); page.screenshot(path=str(OUT / "02-weekly-chart.png"))
        page.mouse.move(2, 2)
        page.click("#grafik-sekmeleri .sekme-btn >> nth=1"); page.click("#donut-sekmeleri .sekme-btn >> nth=1")
        page.mouse.move(2, 2); page.wait_for_timeout(600); page.screenshot(path=str(OUT / "03-monthly-heatmap.png"))
        page.mouse.move(2, 2)
        # bubble held in glass state
        grp = card(1).locator('[data-rol="sekmeler"]')
        b0 = grp.locator(".sekme-btn").nth(0).bounding_box(); b1 = grp.locator(".sekme-btn").nth(1).bounding_box()
        y = b0["y"] + b0["height"] / 2
        page.mouse.move(b0["x"] + b0["width"] / 2, y); page.mouse.down(); page.wait_for_timeout(500)
        page.mouse.move(b0["x"] + b0["width"] / 2 + (b1["x"] - b0["x"]) * 0.5, y, steps=8); page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "04-selection-bubble.png"))
        page.mouse.up(); page.wait_for_timeout(1200)
        # detail dialog
        card(0).locator(".satir").nth(0).click(); page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "05-task-details.png"))
        page.keyboard.press("Escape"); page.wait_for_timeout(500)

        # ---- GIF frames (fresh page, real clock) ----
        page.goto(base); page.wait_for_selector(".kart[data-tur] .satir"); page.wait_for_timeout(1200)
        def grab(ms=0):
            end = time.time() + ms / 1000
            while True:
                frames.append((time.time(), page.screenshot()))
                if time.time() >= end: break
        grab(600)
        # 1) glass bubble drag: routines card tab 0 -> 1 -> 2 (if present)
        tabs = grp.locator(".sekme-btn"); n = tabs.count()
        def centre(i):
            b = tabs.nth(i).bounding_box(); return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        x0, y0 = centre(0); page.mouse.move(x0, y0); page.mouse.down(); grab(500)
        x1, _ = centre(min(1, n - 1))
        for k in range(1, 9):
            page.mouse.move(x0 + (x1 - x0) * k / 8, y0); grab(0)
        grab(300); page.mouse.up(); grab(900)
        # 2) short clicks slide the bubble back
        tabs.nth(0).click(); grab(900)
        # 3) tasks card: complete a task
        card(0).locator('[data-rol="duzenle-ac"]').click(); grab(500)
        card(0).locator(".satir").nth(0).click(); grab(500)
        card(0).locator('[data-rol="tamamla"]').click(); grab(1400)
        browser.close()
finally:
    server.terminate(); server.wait(10); shutil.rmtree(tmp, ignore_errors=True)
print("browser errors:", errors)


def make_gif(frames, path, width=960, colors=192):
    import io
    from PIL import Image
    t0 = frames[0][0]
    imgs, durs = [], []
    for n, (t, png) in enumerate(frames):
        im = Image.open(io.BytesIO(png)).convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        imgs.append(im.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
        nxt = frames[n + 1][0] if n + 1 < len(frames) else t + 1.0
        durs.append(max(40, int((nxt - t) * 1000 // 10 * 10)))
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=durs, loop=0, optimize=True, disposal=1)
    print(f"{path.name}: {len(imgs)} frames, {sum(durs) / 1000:.1f} s, {path.stat().st_size / 1e6:.2f} MB")


make_gif(frames, OUT / "demo.gif")
