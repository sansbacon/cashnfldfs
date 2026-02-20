import random
import re
import sys
import time
from urllib.parse import urlparse
from pathlib import Path
import hashlib
from datetime import date, datetime
import html as html_lib
from typing import Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

BASE_URL = "https://establishtherun.com/category/cash-lineup-review/"
OUTPUT_DIR = Path(__file__).resolve().parent
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_INDEX_HTML = OUTPUT_DIR / "Cash Lineup Review _ Establish The Run.html"


_PUBLISHED_SPAN_RE = re.compile(
    r"<span[^>]*\bclass=[\"']published[\"'][^>]*>(.*?)</span>",
    re.IGNORECASE | re.DOTALL,
)

_HREF_RE = re.compile(r"<a\b[^>]*\bhref=[\"']([^\"']+)[\"']", re.IGNORECASE)
_ARTICLE_BLOCK_RE = re.compile(r"<article\b.*?</article>", re.IGNORECASE | re.DOTALL)


def extract_published_text(html: str) -> Optional[str]:
    match = _PUBLISHED_SPAN_RE.search(html)
    if not match:
        return None
    text = re.sub(r"<[^>]+>", "", match.group(1))
    text = html_lib.unescape(text)
    return text.strip() or None


def parse_published_date(published_text: str) -> Optional[date]:
    text = published_text.strip()
    # Examples observed:
    # - "Sep 8, 2025"
    # - "7:51 Jan 2, 2022"
    text = re.sub(r"^\d{1,2}:\d{2}\s+", "", text)

    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def compute_season_from_date(published_date: date) -> int:
    # NFL season is typically named for the year it starts (Sep–Feb).
    # Jan/Feb posts belong to the prior season.
    return published_date.year - 1 if published_date.month <= 2 else published_date.year


def extract_links_from_html(html: str) -> dict:
    links = {}
    for href in _HREF_RE.findall(html):
        href = html_lib.unescape(href.strip())
        if not href:
            continue
        if "establishtherun.com/levitans-dfs-cash-lineup-review" not in href:
            continue
        links[href] = href
    return links


def extract_published_text_by_url_from_index_html(html: str) -> dict:
    published_by_url = {}
    for block in _ARTICLE_BLOCK_RE.findall(html):
        href = None
        for candidate in _HREF_RE.findall(block):
            candidate = html_lib.unescape(candidate.strip())
            if "establishtherun.com/levitans-dfs-cash-lineup-review" not in candidate:
                continue
            href = candidate
            break
        if not href:
            continue

        published_text = extract_published_text(block)
        if published_text:
            published_by_url[href] = published_text
    return published_by_url

def build_filename(url):
    path = urlparse(url).path.strip("/")
    last_segment = path.split("/")[-1] if path else "page"
    safe_segment = re.sub(r"[^A-Za-z0-9_-]+", "_", last_segment).strip("_")
    if not safe_segment:
        safe_segment = "page"
    url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{safe_segment}_{url_hash}.html"


def build_filename_with_season(url: str, season: Optional[int]) -> str:
    file_name = build_filename(url)
    if season is None:
        return file_name
    p = Path(file_name)
    return f"{p.stem}_{season}{p.suffix}"


def extract_links(page):
    links = {}
    anchor_data = page.eval_on_selector_all(
        "a[href]",
        "els => els.map(el => ({ href: el.getAttribute('href') || '', title: (el.textContent || '').trim() }))",
    )
    for item in anchor_data:
        href = item.get("href")
        if not href:
            continue
        if "establishtherun.com/levitans-dfs-cash-lineup-review" not in href:
            continue
        title = item.get("title") or href
        links[href] = title
    return links


def main():
    all_links = {}
    seen_next_pages = set()
    dry_run = "--dry-run" in sys.argv

    index_html_path = None
    if "--index-html" in sys.argv:
        idx = sys.argv.index("--index-html")
        if idx + 1 < len(sys.argv):
            index_html_path = Path(sys.argv[idx + 1]).expanduser()
    elif DEFAULT_INDEX_HTML.exists():
        index_html_path = DEFAULT_INDEX_HTML

    with sync_playwright() as p:
        interactive = "--interactive" in sys.argv
        if interactive:
            browser = p.chromium.connect_over_cdp(DEFAULT_CDP_URL)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()

        published_text_by_url = {}
        if index_html_path is not None and index_html_path.exists():
            index_html = index_html_path.read_text(
                encoding="utf-8", errors="ignore"
            )
            all_links.update(extract_links_from_html(index_html))
            published_text_by_url = extract_published_text_by_url_from_index_html(
                index_html
            )
        else:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)

            all_links.update(extract_links(page))

            while True:
                load_more = page.locator("div.ajax-load-more")
                if load_more.count() == 0 or not load_more.first.is_visible():
                    break

                next_page = load_more.first.get_attribute("data-href")
                if not next_page or next_page in seen_next_pages:
                    break
                seen_next_pages.add(next_page)

                prev_count = len(all_links)
                try:
                    time.sleep(random.uniform(5, 15))
                    load_more.first.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                except PlaywrightTimeoutError:
                    pass

                page.wait_for_timeout(1000)
                all_links.update(extract_links(page))

                if len(all_links) == prev_count:
                    # No new links, avoid infinite loop.
                    break

        sorted_links = sorted(all_links.items())

        if dry_run:
            for url, _title in sorted_links:
                url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
                exists = any(OUTPUT_DIR.glob(f"*_{url_hash}.html")) or any(
                    OUTPUT_DIR.glob(f"*_{url_hash}_*.html")
                )

                published_text = published_text_by_url.get(url)
                published_date = (
                    parse_published_date(published_text) if published_text else None
                )
                season = (
                    compute_season_from_date(published_date)
                    if published_date is not None
                    else None
                )
                file_name = build_filename_with_season(url, season)
                status = "SKIP" if exists else "DOWNLOAD"
                print(f"{status}\t{file_name}\t{url}")
            browser.close()
            return

        for url, _title in sorted_links:
            url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
            if any(OUTPUT_DIR.glob(f"*_{url_hash}.html")) or any(
                OUTPUT_DIR.glob(f"*_{url_hash}_*.html")
            ):
                continue

            time.sleep(random.uniform(5, 15))
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            html = page.content()
            published_text = extract_published_text(html)
            published_date = (
                parse_published_date(published_text) if published_text else None
            )
            season = (
                compute_season_from_date(published_date)
                if published_date is not None
                else None
            )

            file_name = build_filename_with_season(url, season)
            file_path = OUTPUT_DIR / file_name
            if file_path.exists():
                continue
            file_path.write_text(html, encoding="utf-8")

        browser.close()


if __name__ == "__main__":
    main()
