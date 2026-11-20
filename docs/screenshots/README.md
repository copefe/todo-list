# Screenshots

The images in this folder are used by the top-level README. They show the English UI with the
sample data only (no personal data).

To regenerate them (needs Playwright and Microsoft Edge; the GIF needs Pillow):

```bash
pip install -r requirements-dev.txt pillow
python tests/browser/make_screenshots.py
```

The script uses a temporary data folder and never touches your real data. It renders in
Chromium/Edge through Playwright; the desktop app uses the Edge WebView2 runtime, so the glass
effects may look slightly different there.
