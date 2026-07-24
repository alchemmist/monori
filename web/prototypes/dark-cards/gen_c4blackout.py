"""
Bottom of the depth scale — pure black canvas, glow all but gone, sections at
the faintest lift so cards are held mostly by a hairline border + shadow.
"""

from playwright.sync_api import sync_playwright

VARIANTS = {
    # true black, whisper of glow, cards ~3.2% white held by border
    "C4d7-blackout": ("#060409", "#010102", "#000000", "#000000", "#040308", 0.032),
    # absolute floor — no visible glow, cards 2.6% white, stronger hairline
    "C4d8-obsidian": ("#030205", "#000000", "#000000", "#000000", "#030307", 0.026),
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
        border = 0.07 if alpha < 0.03 else 0.055
        css = f"""
            .g-root_theme_dark{{--m-bg:{bg};--m-surface:{surf};--m-border:#141019;}}
            body{{background:radial-gradient(120% 90% at 82% -12%,{g1} 0%,{g2} 46%,{g3} 100%);}}
            .g-root_theme_dark .card{{
                background:rgba(255,255,255,{alpha});border:1px solid rgba(255,255,255,{border});
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
