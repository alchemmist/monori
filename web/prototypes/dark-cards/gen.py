"""Render the real /demo dashboard in dark mode with different card-token
overrides, so the card treatments can be compared on the actual UI (real colors,
fonts, layout) instead of a hand-built mock. Run with the server venv's python
while `npm run dev` serves the web app on :5173."""

from playwright.sync_api import sync_playwright

# name -> (page bg, card bg, card border)
VARIANTS = {
    "0-current": ("#0a0a0a", "#0e0e0d", "#171716"),
    "A-soft-elevated": ("#0a0a0a", "#151412", "#1a1917"),
    "B-elevated-hairline": ("#0a0a0a", "#141312", "#242320"),
    "C-borderless": ("#0a0a0a", "#161513", "transparent"),
    "D-seamless": ("#0a0a0a", "#0d0d0c", "#131211"),
    "E-inset": ("#141311", "#0c0c0b", "#1c1b19"),
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

    for name, (bg, card, border) in VARIANTS.items():
        css = (
            ".g-root_theme_dark{"
            f"--m-bg:{bg};--m-card-bg:{card};--m-card-border:{border};"
            "}"
            "body{" f"background:{bg};" "}"
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
