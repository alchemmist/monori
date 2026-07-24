"""
C4 (aurora glass), shifted DARKER — canvas + sections deeper, keeping the
violet glow and the principle 'background darker than the (translucent) cards'.
Three depth steps to pick the exact darkness.
"""

from playwright.sync_api import sync_playwright

# name -> (grad_top, grad_mid, grad_edge, --m-bg, --m-surface, card_alpha)
VARIANTS = {
    "C4d1-minus1": ("#17102a", "#0a0812", "#060509", "#08070d", "#0d0b15", 0.040),
    "C4d2-minus2": ("#130d23", "#08060f", "#050407", "#070610", "#0b0912", 0.044),
    "C4d3-deepest": ("#100b1d", "#06050c", "#040306", "#050409", "#09070f", 0.050),
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
            .g-root_theme_dark{{--m-bg:{bg};--m-surface:{surf};--m-border:#221d31;}}
            body{{background:radial-gradient(120% 90% at 82% -12%,{g1} 0%,{g2} 46%,{g3} 100%);}}
            .g-root_theme_dark .card{{
                background:rgba(255,255,255,{alpha});border:1px solid rgba(255,255,255,.065);
                border-radius:12px;backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);
                box-shadow:0 14px 34px -20px rgba(0,0,0,.9);
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
