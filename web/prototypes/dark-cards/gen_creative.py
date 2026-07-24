"""
Creative, from-scratch dark-theme directions on the real /demo dashboard.
Each variant injects full CSS (canvas + .card restyle) so we can explore depth
via shadows, gradients, glass, and warm/cool tone — not just fill+border.
"""

from playwright.sync_api import sync_playwright

VARIANTS = {
    # 1. Floating: borderless cards lifted by soft shadow on a neutral canvas
    "C1-floating": """
        .g-root_theme_dark{--m-bg:#0b0b0c;--m-surface:#0e0e10;--m-border:#1b1b1e;}
        body{background:#0b0b0c;}
        .g-root_theme_dark .card{
            background:#111113;border:1px solid transparent;border-radius:10px;
            box-shadow:0 0 0 1px rgba(255,255,255,.02),0 10px 30px -16px rgba(0,0,0,.9);
        }
    """,
    # 2. Elevated slate: cool blue-grey, subtle border + shadow (Linear/GitHub vibe)
    "C2-cool-slate": """
        .g-root_theme_dark{--m-bg:#0d0f13;--m-surface:#10131a;--m-border:#232b39;--m-text-dim:#9aa4b3;}
        body{background:#0d0f13;}
        .g-root_theme_dark .card{
            background:#141924;border:1px solid #222b3a;border-radius:10px;
            box-shadow:0 8px 26px -18px rgba(0,0,0,.95);
        }
    """,
    # 3. Warm ink: warm near-black, gradient card fill, warm hairline — accent feels at home
    "C3-warm-ink": """
        .g-root_theme_dark{--m-bg:#0c0b0a;--m-surface:#100e0c;--m-border:#241d15;}
        body{background:#0c0b0a;}
        .g-root_theme_dark .card{
            background:linear-gradient(#17130f,#120f0b);border:1px solid #241e15;border-radius:9px;
            box-shadow:0 8px 22px -16px rgba(0,0,0,.85);
        }
    """,
    # 4. Aurora glass: subtle violet radial canvas, translucent frosted cards
    "C4-aurora-glass": """
        .g-root_theme_dark{--m-bg:#0a0910;--m-surface:#100d1a;--m-border:#241f33;}
        body{background:radial-gradient(120% 90% at 82% -12%,#1d1536 0%,#0d0a16 46%,#08070c 100%);}
        .g-root_theme_dark .card{
            background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.07);border-radius:12px;
            backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px);
            box-shadow:0 14px 34px -20px rgba(0,0,0,.85);
        }
    """,
    # 5. Hairline accent: pure black, cards defined by a thin warm accent-tinted line
    "C5-accent-hairline": """
        .g-root_theme_dark{--m-bg:#0a0a0a;--m-surface:#0d0d0d;--m-border:#1c1c1a;}
        body{background:#0a0a0a;}
        .g-root_theme_dark .card{
            background:#0b0a0a;border:1px solid #2b221b;border-radius:8px;
            box-shadow:inset 0 1px 0 rgba(255,122,60,.05);
        }
    """,
    # 6. Two-tone depth: darkest canvas, clearly lifted lighter cards w/ top highlight
    "C6-two-tone": """
        .g-root_theme_dark{--m-bg:#08080a;--m-surface:#0c0c0f;--m-border:#20202a;}
        body{background:#08080a;}
        .g-root_theme_dark .card{
            background:#16161b;border:1px solid #212129;border-radius:10px;
            box-shadow:inset 0 1px 0 rgba(255,255,255,.05),0 10px 28px -16px rgba(0,0,0,.95);
        }
    """,
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

    for name, css in VARIANTS.items():
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
