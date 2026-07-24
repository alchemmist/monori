"""
Deepest C4 — background essentially pure black, sections darker too (less
glass), while cards stay a hair lighter than the canvas so the principle holds.
"""

from playwright.sync_api import sync_playwright

VARIANTS = {
    # near-pure-black canvas, faintest glow, cards just barely above black
    "C4d6-pitch": ("#080511", "#020103", "#000000", "#010102", "#050409", 0.045),
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
            .g-root_theme_dark{{--m-bg:{bg};--m-surface:{surf};--m-border:#17141f;}}
            body{{background:radial-gradient(120% 90% at 82% -12%,{g1} 0%,{g2} 46%,{g3} 100%);}}
            .g-root_theme_dark .card{{
                background:rgba(255,255,255,{alpha});border:1px solid rgba(255,255,255,.055);
                border-radius:12px;backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);
                box-shadow:0 14px 34px -22px rgba(0,0,0,1);
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
