"""Option B: BOTH canvas and cards darker, cards kept a step LIGHTER than the
canvas so depth holds. Cards use a solid fill (not translucent) so their
darkening is unmistakable across steps. Aurora violet glow kept, subtle."""

from playwright.sync_api import sync_playwright

# name -> (glow, base, edge, card_fill, bg_token, surface, border_alpha)
VARIANTS = {
    "B1-dark": ("#16102a", "#0a0713", "#06040c", "#0f0d16", "#07060d", "#0c0a14", 0.07),
    "B2-darker": ("#120c22", "#06040d", "#030206", "#0b0912", "#050409", "#0a0810", 0.065),
    "B3-deepest": ("#0d0819", "#030208", "#010102", "#08070f", "#020204", "#07060c", 0.06),
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

    for name, (g1, g2, g3, card, bg, surf, ba) in VARIANTS.items():
        css = f"""
            .g-root_theme_dark{{--m-bg:{bg};--m-surface:{surf};--m-border:#1a1626;}}
            body{{background:radial-gradient(120% 90% at 82% -12%,{g1} 0%,{g2} 46%,{g3} 100%);}}
            .g-root_theme_dark .card{{
                background:{card};border:1px solid rgba(255,255,255,{ba});
                border-radius:12px;box-shadow:0 14px 34px -20px rgba(0,0,0,.95);
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
