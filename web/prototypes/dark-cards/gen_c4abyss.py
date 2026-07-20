"""Even deeper C4 — near-black canvas, faint violet glow, glass cards still
clearly lighter than the background."""

from playwright.sync_api import sync_playwright

VARIANTS = {
    # deeper than C4-3
    "C4d4-abyss": ("#0d0817", "#040308", "#020103", "#040309", "#080611", 0.055),
    # deepest — glow barely there, cards float on true black
    "C4d5-void": ("#0a0713", "#030205", "#010102", "#020204", "#06050d", 0.060),
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

    for name, (g1, g2, g3, bg, surf, alpha) in VARIANTS.items():
        css = f"""
            .g-root_theme_dark{{--m-bg:{bg};--m-surface:{surf};--m-border:#1e1a2b;}}
            body{{background:radial-gradient(120% 90% at 82% -12%,{g1} 0%,{g2} 46%,{g3} 100%);}}
            .g-root_theme_dark .card{{
                background:rgba(255,255,255,{alpha});border:1px solid rgba(255,255,255,.06);
                border-radius:12px;backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);
                box-shadow:0 14px 34px -20px rgba(0,0,0,.95);
            }}
        """
        pg.evaluate(
            """([id, css]) => {
                let el = document.getElementById(id);
                if (!el) { el = document.createElement('style'); el.id = id; document.head.appendChild(el); }
                el.textContent = css;
            }""",
            ["variant-override", css],
        )
        pg.wait_for_timeout(500)
        pg.screenshot(path=f"{OUT}/{name}.png")
        print("shot", name)
    b.close()
