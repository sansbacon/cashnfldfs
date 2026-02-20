from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ArticleMeta:
    source_file: str
    title: str
    author: str
    published_text: str
    published_date: Optional[date]
    season: Optional[int]


BLOCK_TAGS = ("h2", "h3", "h4", "p", "li")


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_for_boilerplate(text: str) -> str:
    text = (text or "").strip().lower()
    # Normalize curly quotes/apostrophes and dashes.
    text = (
        text.replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
    )
    # Remove punctuation to make matching robust.
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_BOILERPLATE_NORMALIZED = {
    _normalize_for_boilerplate(
        "Each week, I’ll review my cash-game lineups in this space. Sometimes I’ll lose, but hopefully I’ll win more often. Either way, I’ll post it here and give you my thought process."
    ),
    _normalize_for_boilerplate(
        "Each week, I’ll review my cash-game lineup in this space. Sometimes I’ll lose, but hopefully I’ll win more often. Either way, I’ll post it here and give you my thought process."
    ),
}


def parse_published_date(published_text: str) -> Optional[date]:
    text = (published_text or "").strip()
    if not text:
        return None

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


def compute_nfl_season(published_date: date) -> int:
    # NFL season is typically named for the year it starts (Sep–Feb).
    # Jan/Feb posts belong to the prior season.
    return published_date.year - 1 if published_date.month <= 2 else published_date.year


def extract_article_meta_and_blocks(html: str, source_file: str) -> tuple[Optional[ArticleMeta], list[str]]:
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.select_one("h1.entry-title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    author = ""
    published_text = ""
    meta = soup.select_one("p.post-meta")
    if meta:
        author_tag = meta.select_one("span.author a, span.author")
        if author_tag:
            author = author_tag.get_text(strip=True)
        date_tag = meta.select_one("span.published")
        if date_tag:
            published_text = date_tag.get_text(strip=True)

    body_div = soup.select_one("div.entry-content")
    if not body_div:
        return None, []

    for tag in body_div(["script", "style"]):
        tag.decompose()

    blocks: list[str] = []
    for el in body_div.find_all(BLOCK_TAGS, recursive=True):
        txt = _clean_text(el.get_text(" ", strip=True))
        if not txt:
            continue

        if _normalize_for_boilerplate(txt) in _BOILERPLATE_NORMALIZED:
            continue

        # Filter common junk while keeping DFS-relevant short headers.
        if len(txt) < 12 and txt.upper() != txt and txt.lower() not in {"qb", "rb", "wr", "te", "dst"}:
            continue
        blocks.append(txt)

    published_dt = parse_published_date(published_text)
    season = compute_nfl_season(published_dt) if published_dt else None

    meta_out = ArticleMeta(
        source_file=source_file,
        title=title,
        author=author,
        published_text=published_text,
        published_date=published_dt,
        season=season,
    )
    return meta_out, blocks


LABELS_IN_ORDER = [
    "general_strategy",
    "roster_structure",
    "position_qb",
    "position_rb",
    "position_wr",
    "position_te",
    "position_dst",
    "tiebreakers",
    "pitfalls",
]


_LABEL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "general_strategy": [
        re.compile(r"\bcash\b|\bdouble[- ]?up\b|\b50/50\b|\bh2h\b", re.I),
        re.compile(r"\bfloor\b|\bmedian\b|\bvolatility\b|\bvariance\b", re.I),
        re.compile(r"\bownership\b|\bchalk\b", re.I),
        re.compile(r"\bprocess\b|\bprojection\b|\bvalue\b", re.I),
    ],
    "roster_structure": [
        re.compile(r"\broster\b|\bbuild\b|\bconstruction\b", re.I),
        re.compile(r"\bsalary\b|\bcap\b|\bpunt\b|\bpay up\b|\bmid[- ]?range\b", re.I),
        re.compile(r"\bstack\b|\bcorrelation\b|\bbring[- ]?back\b", re.I),
        re.compile(r"\b2\s*rb\b|\b3\s*wr\b|\bflex\b", re.I),
    ],
    "position_qb": [
        re.compile(r"\bqb\b|quarterback", re.I),
        re.compile(
            r"\bpassing\b|\bpass attempts?\b|\bdropbacks?\b|\binterception\b|\bthrow(?:ing)?\b",
            re.I,
        ),
    ],
    "position_rb": [
        re.compile(r"\brb\b|running back", re.I),
        re.compile(r"\bcarry\b|\brushing\b|\btouch\b|\bworkload\b|\bsnap\b", re.I),
        re.compile(r"\btarget\b|\breception\b|\bpass[- ]?catch\b", re.I),
    ],
    "position_wr": [
        re.compile(r"\bwr\b|wide receiver", re.I),
        re.compile(r"\btarget\b|\bair yards\b|\broute\b|\bsnap\b", re.I),
    ],
    "position_te": [
        re.compile(r"\bte\b|tight end", re.I),
        re.compile(r"\btarget\b|\broute\b|\bsnap\b|\bred zone\b", re.I),
    ],
    "position_dst": [
        re.compile(
            r"\bdst\b|d\s*/\s*st|\bdefense\s*(?:/|and)\s*special\s*teams\b|\bteam\s*defen[cs]e\b",
            re.I,
        ),
        re.compile(r"\bsack\b|\bturnover\b|\binterception\b|\bfumble\b", re.I),
    ],
    "tiebreakers": [
        re.compile(r"\bif you\b|\bwhen deciding\b|\bclose call\b", re.I),
        re.compile(r"\btie\b\s*breaker|\bprefer\b|\blean\b|\bin a vacuum\b", re.I),
        re.compile(r"\bdepends\b|\bconditional\b|\bassuming\b", re.I),
    ],
    "pitfalls": [
        re.compile(r"\bavoid\b|\bdon't\b|\bdo not\b|\btrap\b", re.I),
        re.compile(r"\boverpriced\b|\bbad chalk\b|\bthin\b", re.I),
        re.compile(r"\bchasing\b|\btilt\b|\boverreact\b", re.I),
    ],
}


def score_labels(text: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for label, patterns in _LABEL_PATTERNS.items():
        score = 0
        for pat in patterns:
            if pat.search(text):
                score += 1
        scores[label] = score
    return scores


def choose_labels(scores: dict[str, int], min_score: int) -> list[str]:
    labels = [label for label in LABELS_IN_ORDER if scores.get(label, 0) >= min_score]
    return labels


def choose_labels_with_thresholds(
    text: str, scores: dict[str, int], *, min_score: int, min_score_position: int
) -> list[str]:
    labels: list[str] = []
    for label in LABELS_IN_ORDER:
        if label.startswith("position_"):
            # Prefer explicit position mentions (QB/RB/WR/TE/DST) to avoid false positives.
            anchor = _LABEL_PATTERNS[label][0]
            if label == "position_qb":
                # QB is especially prone to incidental matches like "at QB" inside D/ST blurbs.
                # Require either a higher score OR some secondary QB evidence.
                has_anchor = bool(anchor.search(text))
                has_secondary = any(p.search(text) for p in _LABEL_PATTERNS[label][1:])
                if scores.get(label, 0) >= min_score_position or (has_anchor and has_secondary):
                    labels.append(label)
            else:
                if anchor.search(text) or scores.get(label, 0) >= min_score_position:
                    labels.append(label)
        else:
            if scores.get(label, 0) >= min_score:
                labels.append(label)
    return labels


def resolve_label_conflicts(text: str, labels: list[str], scores: dict[str, int]) -> list[str]:
    # If a block is about a specific position, keep it out of general strategy.
    # This prevents "cash strategy" catch-alls from duplicating position-specific notes.
    if "general_strategy" in labels and any(l.startswith("position_") for l in labels):
        labels = [l for l in labels if l != "general_strategy"]

    # Avoid duplicating the same block across multiple position sections.
    # Keep only the strongest position label (by score, then by anchor hit as tiebreaker).
    position_labels = [l for l in labels if l.startswith("position_")]
    if len(position_labels) > 1:
        def pos_strength(label: str) -> tuple[int, int]:
            score = scores.get(label, 0)
            anchor = _LABEL_PATTERNS[label][0]
            anchor_hit = 1 if anchor.search(text) else 0
            return (score, anchor_hit)

        best = max(position_labels, key=pos_strength)
        labels = [l for l in labels if not l.startswith("position_") or l == best]
    return labels


def iter_html_files(input_dirs: list[Path], glob_pattern: str) -> Iterable[Path]:
    seen: set[Path] = set()
    for root in input_dirs:
        for path in root.glob(glob_pattern):
            if not path.is_file():
                continue
            if path.suffix.lower() != ".html":
                continue
            if path.name == "Cash Lineup Review _ Establish The Run.html":
                continue
            # Avoid accidentally ingesting Playwright traces or other large artifacts.
            if any(part.lower() in {"node_modules", ".git", "__pycache__"} for part in path.parts):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def extract_week_number(*candidates: str) -> Optional[int]:
    for c in candidates:
        if not c:
            continue
        m = re.search(r"\bweek\s*(\d{1,2})\b", c, re.IGNORECASE)
        if not m:
            m = re.search(r"week-(\d{1,2})", c, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _parse_iso_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d).date()
    except ValueError:
        return None


def write_markdown_grouped(records: list[dict], out_md: Path) -> None:
    by_label: dict[str, list[dict]] = {label: [] for label in LABELS_IN_ORDER}
    for r in records:
        for label in r.get("labels", []):
            if label in by_label:
                by_label[label].append(r)

    lines: list[str] = []
    lines.append("# Book Insights (auto-extracted)\n")
    lines.append(
        "This file is a starting point: review, edit, and rewrite in your own voice.\n"
    )

    for label in LABELS_IN_ORDER:
        items = by_label[label]
        if not items:
            continue

        def sort_key(r: dict) -> tuple:
            season = r.get("season")
            season_sort = season if isinstance(season, int) else -1
            week = extract_week_number(r.get("title") or "", r.get("source_file") or "")
            week_sort = week if isinstance(week, int) else -1
            published_date = _parse_iso_date(r.get("published_date"))
            published_sort = published_date or date.min
            source = r.get("source_file") or ""
            return (season_sort, week_sort, published_sort, source)

        items = sorted(items, key=sort_key, reverse=True)
        lines.append(f"\n## {label}\n")
        for r in items:
            title = r.get("title") or "(untitled)"
            published = r.get("published_text") or ""
            season = r.get("season")
            season_str = f"season {season}" if season is not None else ""
            meta_bits = " | ".join(b for b in [published, season_str] if b)
            src = r.get("source_file")
            block = r.get("text")
            lines.append(f"- {title} ({meta_bits}) — {src}: {block}")

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Extract paragraph/list-item blocks from saved Cash Lineup Review articles "
            "and auto-tag them into book-relevant categories."
        )
    )
    ap.add_argument(
        "--input-dir",
        action="append",
        default=["."],
        help="Directory to scan (repeatable). Default: current directory.",
    )
    ap.add_argument(
        "--glob",
        default="**/*.html",
        help="Glob pattern under each input dir. Default: **/*.html",
    )
    ap.add_argument(
        "--min-score",
        type=int,
        default=2,
        help="Minimum per-label score to include a label on a block. Default: 2",
    )
    ap.add_argument(
        "--min-score-position",
        type=int,
        default=2,
        help=(
            "Minimum score to include a position_* label without an explicit position mention. Default: 2"
        ),
    )
    ap.add_argument(
        "--out-jsonl",
        default="book_insights.jsonl",
        help="Output JSONL file. Default: book_insights.jsonl",
    )
    ap.add_argument(
        "--out-md",
        default="book_insights.md",
        help="Output Markdown file grouped by label. Default: book_insights.md",
    )

    args = ap.parse_args()

    input_dirs = [Path(p).expanduser().resolve() for p in args.input_dir]
    out_jsonl = Path(args.out_jsonl).expanduser().resolve()
    out_md = Path(args.out_md).expanduser().resolve()

    records: list[dict] = []

    for html_path in iter_html_files(input_dirs, args.glob):
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        meta, blocks = extract_article_meta_and_blocks(html, source_file=str(html_path))
        if meta is None:
            continue

        for idx, block in enumerate(blocks):
            scores = score_labels(block)
            labels = choose_labels_with_thresholds(
                block,
                scores,
                min_score=args.min_score,
                min_score_position=args.min_score_position,
            )
            labels = resolve_label_conflicts(block, labels, scores)
            if not labels:
                continue

            records.append(
                {
                    "source_file": meta.source_file,
                    "title": meta.title,
                    "author": meta.author,
                    "published_text": meta.published_text,
                    "published_date": meta.published_date.isoformat() if meta.published_date else None,
                    "season": meta.season,
                    "block_index": idx,
                    "text": block,
                    "labels": labels,
                    "scores": scores,
                }
            )

    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_markdown_grouped(records, out_md)

    print(f"Wrote {len(records)} labeled blocks")
    print(f"- {out_jsonl}")
    print(f"- {out_md}")


if __name__ == "__main__":
    main()
