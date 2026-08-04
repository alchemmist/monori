"""Headless check that the Transactions page virtualizes list rendering.

Only a windowed slice of the 6802 rows is ever in the DOM; spacers stand in for
the rest. Scrolling recycles rendered rows while the sticky header stays pinned.
"""

import pathlib
import logging
import sys

from playwright.sync_api import Page, sync_playwright
from pydantic import TypeAdapter
from pydantic.dataclasses import dataclass as pydantic_dataclass

TOKEN_FILE = pathlib.Path("/tmp/monori-token.txt")
WINDOWED_ROW_LIMIT = 200
WINDOW_TOP_OFFSET_PX = 2
TALL_SCROLL_MIN_PX = 200_000
TOTAL_TRANSACTIONS_TEXTS = ("6802", "6 802")
logger = logging.getLogger(__name__)


@pydantic_dataclass
class Measure:
    """Collected runtime measurement metrics for a page snapshot."""

    renderedRows: int
    spacers: int
    scrollHeight: int
    scrollY: int
    headerTop: int | None
    firstDate: str | None
    countText: str | None


def load_token() -> str:
    """Load token."""
    if not TOKEN_FILE.exists():
        sys.exit(
            f"{TOKEN_FILE} not found — mint one first, e.g.:\n"
            "  cd server && uv run python -c "
            "'from app.security import create_access_token; print(create_access_token(1))'"
            f" > {TOKEN_FILE}"
        )
    return TOKEN_FILE.read_text().strip()


def measure(page: Page) -> Measure:
    """Measure for this module."""
    return TypeAdapter(Measure).validate_python(
        page.evaluate(
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
    )


def main() -> None:
    """Run this module as a CLI entrypoint and return its exit code."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    token = load_token()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page: Page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script(f"localStorage.setItem('monori_token', {token!r});")
        page.goto("http://localhost:5173/", wait_until="networkidle")
        page.get_by_text("Transactions", exact=True).first.click()
        page.wait_for_selector("tr.cat-row", timeout=15000)
        page.wait_for_timeout(500)

        top = measure(page)
        logger.info("AT TOP: %s", top)

        page.evaluate("window.scrollTo(0, 120000)")
        page.wait_for_timeout(400)
        mid = measure(page)
        logger.info("SCROLLED MID: %s", mid)

        page.evaluate("window.scrollTo(0, document.scrollingElement.scrollHeight)")
        page.wait_for_timeout(400)
        bot = measure(page)
        logger.info("AT BOTTOM: %s", bot)

        # filter: type in search, expect the count to shrink and scroll reset
        page.get_by_placeholder("Search description").fill("Ростелеком")
        page.wait_for_timeout(500)
        filt = measure(page)
        logger.info("FILTERED 'Ростелеком': %s", filt)

        browser.close()

        logger.info("\n=== checks ===")
        ok = True

        def check(name: str, *, cond: bool) -> None:
            nonlocal ok
            ok = ok and cond
            logger.info("[%s] %s", "PASS" if cond else "FAIL", name)

        check("count shows all 6802", cond=top.countText in TOTAL_TRANSACTIONS_TEXTS)
        check(
            "windowed DOM (<200 rows, not 6802)",
            cond=0 < top.renderedRows < WINDOWED_ROW_LIMIT,
        )
        check("tall scroll height (>200k px)", cond=top.scrollHeight > TALL_SCROLL_MIN_PX)
        check("spacers present", cond=top.spacers >= 1)
        check("mid still windowed", cond=0 < mid.renderedRows < WINDOWED_ROW_LIMIT)
        check("mid recycled (date changed vs top)", cond=mid.firstDate != top.firstDate)
        header_top = mid.headerTop
        assert header_top is not None
        check(
            "sticky header pinned at mid (top≈0)",
            cond=abs(header_top) <= WINDOW_TOP_OFFSET_PX,
        )
        check("bottom still windowed", cond=0 < bot.renderedRows < WINDOWED_ROW_LIMIT)
        check("filter shrank the set", cond=filt.countText not in TOTAL_TRANSACTIONS_TEXTS)
        check("filter reset scroll to top", cond=filt.scrollY <= WINDOW_TOP_OFFSET_PX)
        logger.info("\nRESULT: %s", "ALL PASS" if ok else "SOME FAILED")


if __name__ == "__main__":
    main()
