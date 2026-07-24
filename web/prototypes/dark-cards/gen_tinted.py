"""
Violet-tinted dark-theme explorations on the real /demo dashboard.

The user likes a soft purple background but dislikes neutral near-black cards
sitting on it as "black cubes". These variants tint the whole dark palette
(bg + cards + borders) toward violet so cards read as a harmonious elevated
surface rather than black blocks. Also overrides surface-raised/border/text-dim
so sidebar, header and chart gridlines stay in the same family.
"""

from playwright.sync_api import sync_playwright

# name -> dict of --m-* token overrides (whole family kept in one hue)
VARIANTS = {
    # elevated: cards a step LIGHTER than a soft violet canvas
    "P1-violet-elevated": {
        "bg": "#100e16",
        "card-bg": "#1a1622",
        "card-border": "#282232",
        "surface": "#141019",
        "surface-raised": "#1d1928",
        "border": "#2a2436",
        "border-soft": "#221d2d",
    },
    # subtler violet, less saturated, gentler lift
    "P2-violet-soft": {
        "bg": "#0e0d13",
        "card-bg": "#16131d",
        "card-border": "#221d2a",
        "surface": "#121017",
        "surface-raised": "#1a1622",
        "border": "#241f2d",
        "border-soft": "#1c1826",
    },
    # paler violet canvas, cards a touch lighter still (more "airy")
    "P3-violet-airy": {
        "bg": "#151320",
        "card-bg": "#1e1b2b",
        "card-border": "#2c2740",
        "surface": "#191625",
        "surface-raised": "#232032",
        "border": "#2e2942",
        "border-soft": "#262137",
    },
    # warm-neutral control (no purple) — slightly warm charcoal, elevated cards
    "N-warm-neutral": {
        "bg": "#0f0e0d",
        "card-bg": "#1a1817",
        "card-border": "#26231f",
        "surface": "#141211",
        "surface-raised": "#1c1a18",
        "border": "#282521",
        "border-soft": "#201e1b",
    },
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

    for name, t in VARIANTS.items():
        decls = ";".join(f"--m-{k}:{v}" for k, v in t.items())
        css = f".g-root_theme_dark{{{decls}}}body{{background:{t['bg']}}}"
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
