"""UI-Smoke-Test: ruft jede Seite auf, sammelt Exceptions und Screenshots."""
import sys, asyncio
from playwright.sync_api import sync_playwright
PAGES = ["", "revenue", "attribution", "alerts", "history", "newsletter", "subjects", "products", "funnel",
         "ai-analyst", "data", "settings"]
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"
only = sys.argv[2:] or PAGES
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1680, "height": 1050})
    for name in only:
        pg.goto(f"http://localhost:8501/{name}", wait_until="networkidle")
        pg.wait_for_timeout(2500)
        for _ in range(60):
            if pg.locator('[data-testid="stStatusWidget"]').count() == 0:
                break
            pg.wait_for_timeout(500)
        pg.wait_for_timeout(1500)
        exc = pg.locator('[data-testid="stException"]')
        errs = [exc.nth(i).inner_text()[:600] for i in range(exc.count())]
        pg.screenshot(path=f"{out}/{name or 'overview'}.png", full_page=True)
        print(name, "ERRORS:" if errs else "ok", *errs, sep="\n  " if errs else " ")
    b.close()
