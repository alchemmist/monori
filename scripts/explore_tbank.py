"""Interactive T-Bank markup explorer / driver.

Launches a headed persistent Chromium and stays alive, driven by single-line
commands so selectors can be verified and clicked against the real markup — no
screenshots. The persistent profile (trusted-device identity) survives restarts,
mirroring what the real connector relies on.

Command protocol — write one line to <ctl>/cmd; the result lands in
<ctl>/result and <ctl>/done flips:
  dump                      -> page.html (url + full HTML) + summary.txt (hooks)
  goto <url>                -> navigate
  click <selector>          -> click first match (5s)
  clicktext <text>          -> click first element containing text
  type <selector> <text>    -> fill
  keys <text>               -> keyboard.type into focused element
  download <selector>       -> click selector inside expect_download, save csv
  url                       -> just report current url
  stop                      -> close and exit
"""

import json
import os
import pathlib
import re
import time

from playwright.sync_api import sync_playwright

CTL = pathlib.Path(os.environ.get("TBANK_CTL", "/tmp/tbank-explore"))
LOGIN = "https://www.tbank.ru/auth/login/"
ATTR_RE = re.compile(r'(automation-id|data-qa-type|data-qa-file)="([^"]+)"')


def dump(page):
    html = page.content()
    (CTL / "page.html").write_text(f"<!-- url: {page.url} -->\n{html}", encoding="utf-8")
    seen = []
    for m in ATTR_RE.finditer(html):
        key = f"{m.group(1)}={m.group(2)}"
        if key not in seen:
            seen.append(key)
    (CTL / "summary.txt").write_text(
        "\n".join([f"URL: {page.url}", ""] + seen), encoding="utf-8"
    )
    return f"dumped {len(html)} bytes, url={page.url}"


def handle(page, line):
    parts = line.split(" ", 1)
    cmd = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ""
    if cmd == "dump":
        return dump(page)
    if cmd == "url":
        return page.url
    if cmd == "goto":
        page.goto(arg, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        return f"at {page.url}"
    if cmd == "click":
        page.locator(arg).first.click(timeout=8000)
        page.wait_for_timeout(1200)
        return f"clicked {arg}; url={page.url}"
    if cmd == "clicktext":
        page.get_by_text(arg, exact=False).first.click(timeout=8000)
        page.wait_for_timeout(1200)
        return f"clicked text '{arg}'; url={page.url}"
    if cmd == "forceclick":
        page.locator(arg).first.click(timeout=8000, force=True)
        page.wait_for_timeout(1200)
        return f"force-clicked {arg}; url={page.url}"
    if cmd == "eval":
        val = page.evaluate(arg)
        page.wait_for_timeout(1000)
        return f"eval -> {val}"
    if cmd == "type":
        sel, _, text = arg.partition(" ")
        page.fill(sel, text, timeout=8000)
        return f"typed into {sel}"
    if cmd == "keys":
        page.keyboard.type(arg)
        page.wait_for_timeout(800)
        return f"typed keys {arg}"
    if cmd == "download":
        out = CTL / "export.csv"
        with page.expect_download(timeout=45000) as dl:
            page.locator(arg).first.click(timeout=8000)
        dl.value.save_as(str(out))
        return f"downloaded to {out} ({out.stat().st_size} bytes)"
    return f"unknown command: {cmd}"


def main():
    CTL.mkdir(parents=True, exist_ok=True)
    profile = CTL / "profile"
    profile.mkdir(exist_ok=True)
    for name in ("cmd", "done", "result"):
        (CTL / name).unlink(missing_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(profile),
            headless=False,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            ),
            accept_downloads=True,
            args=["--disk-cache-size=1"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_navigation_timeout(45_000)
        page.set_default_timeout(45_000)
        page.goto(LOGIN, wait_until="domcontentloaded")
        (CTL / "ready").write_text("ready", encoding="utf-8")

        while True:
            cmd_file = CTL / "cmd"
            if not cmd_file.exists():
                time.sleep(0.3)
                continue
            line = cmd_file.read_text(encoding="utf-8").strip()
            cmd_file.unlink(missing_ok=True)
            if line == "stop":
                break
            try:
                result = handle(page, line)
            except Exception as e:  # noqa: BLE001
                result = f"ERROR: {type(e).__name__}: {e}"
            (CTL / "result").write_text(result, encoding="utf-8")
            (CTL / "done").write_text(str(time.time()), encoding="utf-8")

        context.close()


if __name__ == "__main__":
    main()
