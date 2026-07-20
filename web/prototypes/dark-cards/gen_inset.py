"""Card = background slightly DARKENED + a readable border (the border defines
the card, not a lighter fill). Neutral palette kept; only card-bg/card-border
change, across a few border strengths so the right weight can be picked."""

from playwright.sync_api import sync_playwright

BG = "#0a0a0a"

# name -> (card bg = darkened bg, card border)
VARIANTS = {
    "Q1-soft-border": ("#070707", "#1d1d1b"),
    "Q2-clear-border": ("#070707", "#232320"),
    "Q3-darker-card": ("#050504", "#201f1c"),
    "Q4-strong-border": ("#080807", "#2a2925"),
}

OUT = "/Users/antonmoss/code/monori/web/prototypes/dark-cards"

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 880}, device_scale_factor=2)
    pg.goto("http://localhost:5173/demo", wait_until="domcontentloaded")
    pg.evaluate("localStorage.setItem('theme','dark')")
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(1200)
    pg.get_by_text("Dashboard", exact=True).first.click()
    pg.wait_for_timeout(2000)

    for name, (card, border) in VARIANTS.items():
        css = (
            ".g-root_theme_dark{"
            f"--m-bg:{BG};--m-card-bg:{card};--m-card-border:{border};"
            "}"
            f"body{{background:{BG}}}"
        )
        pg.evaluate(
            """([id, css]) => {
                let el = document.getElementById(id);
                if (!el) { el = document.createElement('style'); el.id = id; document.head.appendChild(el); }
                el.textContent = css;
            }""",
            ["variant-override", css],
        )
        pg.wait_for_timeout(400)
        pg.screenshot(path=f"{OUT}/{name}.png")
        print("shot", name)
    b.close()
