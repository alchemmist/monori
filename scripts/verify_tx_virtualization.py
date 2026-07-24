"""
Headless check that the Transactions page virtualizes: only a windowed slice
of the 6802 rows is ever in the DOM, spacers stand in for the rest, and
scrolling recycles the rendered rows while the sticky header stays pinned.
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

TOKEN_FILE = pathlib.Path("/tmp/monori-token.txt")


def load_token():
    if not TOKEN_FILE.exists():
        sys.exit(
            f"{TOKEN_FILE} not found — mint one first, e.g.:\n"
            "  cd server && uv run python -c "
            "'from app.security import create_access_token; print(create_access_token(1))'"
            f" > {TOKEN_FILE}"
        )
    return TOKEN_FILE.read_text().strip()


def measure(page):
    return page.evaluate(
        """() => {
        const rows = document.querySelectorAll('tr.cat-row');
        const spacers = document.querySelectorAll('tr[aria-hidden="true"]');
        const th = document.querySelector('.budget-grid th');
        const firstRow = rows[0];
        const firstDate = firstRow ? firstRow.querySelector('td')?.innerText : null;
        const countText = document.querySelector('.budget-toolbar')
            ? document.body.innerText.match(/(\\d[\\d\\s]*) transactions/)?.[1] : null;
        return {
            renderedRows: rows.length,
            spacers: spacers.length,
            scrollHeight: document.scrollingElement.scrollHeight,
            scrollY: Math.round(window.scrollY),
            headerTop: th ? Math.round(th.getBoundingClientRect().top) : null,
            firstDate,
            countText: countText ? countText.trim() : null,
        };
    }"""
    )


def main():
    token = load_token()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script(f"localStorage.setItem('monori_token', {token!r});")
        page.goto("http://localhost:5173/", wait_until="networkidle")
        page.get_by_text("Transactions", exact=True).first.click()
        page.wait_for_selector("tr.cat-row", timeout=15000)
        page.wait_for_timeout(500)

        top = measure(page)
        print("AT TOP:", top)

        page.evaluate("window.scrollTo(0, 120000)")
        page.wait_for_timeout(400)
        mid = measure(page)
        print("SCROLLED MID:", mid)

        page.evaluate("window.scrollTo(0, document.scrollingElement.scrollHeight)")
        page.wait_for_timeout(400)
        bot = measure(page)
        print("AT BOTTOM:", bot)

        # filter: type in search, expect the count to shrink and scroll reset
        page.get_by_placeholder("Search description").fill("Ростелеком")
        page.wait_for_timeout(500)
        filt = measure(page)
        print("FILTERED 'Ростелеком':", filt)

        browser.close()

        print("\n=== checks ===")
        ok = True

        def check(name, cond):
            nonlocal ok
            ok = ok and cond
            print(f"[{'PASS' if cond else 'FAIL'}] {name}")

        check("count shows all 6802", top["countText"] in ("6802", "6 802"))
        check("windowed DOM (<200 rows, not 6802)", 0 < top["renderedRows"] < 200)
        check("tall scroll height (>200k px)", top["scrollHeight"] > 200_000)
        check("spacers present", top["spacers"] >= 1)
        check("mid still windowed", 0 < mid["renderedRows"] < 200)
        check("mid recycled (date changed vs top)", mid["firstDate"] != top["firstDate"])
        check("sticky header pinned at mid (top≈0)", abs(mid["headerTop"]) <= 2)
        check("bottom still windowed", 0 < bot["renderedRows"] < 200)
        check("filter shrank the set", filt["countText"] not in ("6802", "6 802"))
        check("filter reset scroll to top", filt["scrollY"] <= 2)
        print("\nRESULT:", "ALL PASS" if ok else "SOME FAILED")


if __name__ == "__main__":
    main()
