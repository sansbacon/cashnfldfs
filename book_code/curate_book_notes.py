from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional


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


CORE_PRINCIPLES_BY_LABEL: dict[str, list[str]] = {
    "general_strategy": [
        "Good process tends to drive good results over time, but short-term luck/variance can be misleading — don’t let a hot streak convince you you’re better than you are.",
    ],
}


_DROP_PREFIXES = (
    "week ",
)


def _parse_iso_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d).date()
    except ValueError:
        return None


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


def _clean_text(text: str) -> str:
    t = (text or "").strip()

    # Remove common in-article section headers.
    t = re.sub(r"\bMY\s+MUST\s+PLAYS\b\s*\*?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\bMY\s+WANT\s+PLAYS\b\s*\*?\s*", "", t, flags=re.IGNORECASE)

    # Strip leading bullet markers that come from list items.
    t = re.sub(r"^\*\s+", "", t)

    # Normalize whitespace.
    t = re.sub(r"\s+", " ", t).strip()

    # Remove or anonymize salary references.
    # - ($5300) -> () removed
    t = re.sub(r"\(\s*\$\s*\d[\d,]*\s*\)", "", t)
    # - $5300 or $9,400 -> <salary>
    t = re.sub(r"\$\s*\d[\d,]*", "<salary>", t)

    # Some posts have stray spaced punctuation after removals.
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()

    return t


def _looks_like_results_recap(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True

    # Very explicit recap sections.
    if re.match(r"^week\s*\d{1,2}\s+results\b", t):
        return True

    # Also drop "Week X Results ..." even if there is punctuation.
    if re.match(r"^week\s*\d{1,2}\s+results\b", re.sub(r"[^a-z0-9\s]", "", t)):
        return True

    # Performance-brag/finish-place lines are rarely reusable as book principles.
    if "finished" in t and "out of" in t and "entries" in t:
        return True

    # Very short or purely administrative lines.
    if len(t) < 30:
        return True

    return False


def _looks_like_prune_candidate(text: str, prune: str) -> bool:
    prune = (prune or "none").lower().strip()
    if prune == "none":
        return False

    t = (text or "").strip().lower()
    if not t:
        return True

    # Light pruning: remove diary-ish "see lineup" admin lines.
    light_patterns = [
        r"\bsee (?:team|lineup) above\b",
        r"\bin this lineup\b",
        r"\bhedging across sites\b",
        r"\bacross sites\b",
        r"\bwent off the board\b",
    ]
    if any(re.search(p, t, flags=re.IGNORECASE) for p in light_patterns):
        return True

    if prune == "light":
        return False

    # Medium pruning: drop more "I did X" narrative that’s hard to reuse verbatim.
    medium_patterns = [
        r"\bit(?:’|')s worth noting\b",
        r"\bin the end\b",
        r"\bi (?:decided|simply|ended up|went|was happy|was not|did not)\b",
        r"\bon (?:draftkings|fanduel)\b",
        r"\b(?:draftkings|fanduel)\b",
        r"\b(?:dk|fd)\b",
    ]
    if any(re.search(p, t, flags=re.IGNORECASE) for p in medium_patterns):
        return True

    if prune == "medium":
        return False

    # Heavy pruning: drop most first-person, conversational transitions.
    heavy_patterns = [
        r"\b(i|we)\b",
        r"\balong those lines\b",
        r"\bspeaking of\b",
        r"\bof course\b",
    ]
    if any(re.search(p, t, flags=re.IGNORECASE) for p in heavy_patterns):
        return True

    return False


@dataclass(frozen=True)
class Record:
    source_file: str
    title: str
    published_text: str
    published_date: Optional[date]
    season: Optional[int]
    labels: list[str]
    text: str


def _sort_key(r: Record) -> tuple:
    season_sort = r.season if isinstance(r.season, int) else -1
    week = extract_week_number(r.title, r.source_file)
    week_sort = week if isinstance(week, int) else -1
    published_sort = r.published_date or date.min
    return (season_sort, week_sort, published_sort, r.source_file)


def write_outline(out_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Book Outline (starter)\n")
    lines.append("This is a starter outline derived from the extraction labels. Edit freely.\n")
    lines.append("\n## Part I — Cash Game Fundamentals\n")
    lines.append(
        "- What cash is (and isn’t)\n"
        "- Floor vs. ceiling in cash\n"
        "- Process > results (don’t confuse short-term luck with skill)\n"
    )
    lines.append("\n## Part II — Roster Construction\n")
    lines.append("- Salary allocation and slate context\n- Punts and when they’re right\n- Correlation/stacking rules (if any)\n")
    lines.append("\n## Part III — Position Chapters\n")
    lines.append("- QB\n- RB\n- WR\n- TE\n- D/ST\n")
    lines.append("\n## Part IV — Decision Making\n")
    lines.append("- Tie-breakers (1v1, 2v2, 3v3)\n- Common pitfalls\n")

    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_manuscript_draft(by_label: dict[str, list[Record]], out_path: Path) -> None:
    def _section(title: str) -> None:
        lines.append(f"\n## {title}\n")

    def _subsection(title: str) -> None:
        lines.append(f"\n### {title}\n")

    def _bullets(label: str) -> None:
        for principle in CORE_PRINCIPLES_BY_LABEL.get(label, []):
            lines.append(f"- {principle}")
        items = by_label.get(label) or []
        if not items:
            lines.append("- (no notes yet)\n")
            return
        items = sorted(items, key=_sort_key, reverse=True)
        for r in items:
            lines.append(f"- {r.text}")

    lines: list[str] = []
    lines.append("# Manuscript Draft (auto-assembled)\n")
    lines.append(
        "This is a working draft assembled from cleaned notes. Next pass: rewrite into your voice, "
        "dedupe, and add examples where helpful.\n"
    )

    _section("Part I — Cash Game Fundamentals")
    _subsection("General Strategy")
    _bullets("general_strategy")

    _section("Part II — Roster Construction")
    _subsection("Roster Structure")
    _bullets("roster_structure")

    _section("Part III — Position Chapters")
    _subsection("QB")
    _bullets("position_qb")
    _subsection("RB")
    _bullets("position_rb")
    _subsection("WR")
    _bullets("position_wr")
    _subsection("TE")
    _bullets("position_te")
    _subsection("D/ST")
    _bullets("position_dst")

    _section("Part IV — Decision Making")
    _subsection("Tie-breakers")
    _bullets("tiebreakers")
    _subsection("Pitfalls")
    _bullets("pitfalls")

    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Curate and lightly normalize extracted insights into book-oriented notes. "
            "Input: book_insights.jsonl from extract_book_insights.py"
        )
    )
    ap.add_argument("--in-jsonl", default="book_insights.jsonl")
    ap.add_argument("--out-md", default=str(Path("book") / "book_notes_clean.md"))
    ap.add_argument("--out-outline", default=str(Path("book") / "book_outline.md"))
    ap.add_argument("--out-manuscript", default=str(Path("book") / "manuscript_draft.md"))
    ap.add_argument(
        "--prune",
        default="none",
        choices=["none", "light", "medium", "heavy"],
        help=(
            "Pruning aggressiveness for dropping diary-ish blocks. "
            "Use 'light' for minimal cleanup, 'medium' for more, 'heavy' to be aggressive."
        ),
    )
    args = ap.parse_args()

    in_path = Path(args.in_jsonl).expanduser().resolve()
    out_md = Path(args.out_md).expanduser().resolve()
    out_outline = Path(args.out_outline).expanduser().resolve()
    out_manuscript = Path(args.out_manuscript).expanduser().resolve()

    by_label: dict[str, list[Record]] = {l: [] for l in LABELS_IN_ORDER}

    total = 0
    dropped = 0

    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            raw = json.loads(line)

            text_raw = raw.get("text") or ""
            if _looks_like_results_recap(text_raw):
                dropped += 1
                continue

            text = _clean_text(text_raw)
            if _looks_like_results_recap(text):
                dropped += 1
                continue

            if _looks_like_prune_candidate(text, args.prune):
                dropped += 1
                continue

            labels = [l for l in (raw.get("labels") or []) if l in by_label]
            if not labels:
                dropped += 1
                continue

            rec = Record(
                source_file=raw.get("source_file") or "",
                title=raw.get("title") or "(untitled)",
                published_text=raw.get("published_text") or "",
                published_date=_parse_iso_date(raw.get("published_date")),
                season=raw.get("season") if isinstance(raw.get("season"), int) else None,
                labels=labels,
                text=text,
            )

            for l in labels:
                by_label[l].append(rec)

    lines: list[str] = []
    lines.append("# Book Notes (cleaned, auto-curated)\n")
    lines.append(
        "These notes are derived from the article archive and are meant to be rewritten into your voice.\n"
        "Filters applied: removed explicit \"Week X Results\" recap blocks; removed salary amounts; removed \"MY MUST/WANT PLAYS\" headers.\n"
    )
    lines.append(f"Pruning mode: {args.prune}\n")
    lines.append(f"Input records: {total}  |  Kept: {total - dropped}  |  Dropped: {dropped}\n")

    for label in LABELS_IN_ORDER:
        items = by_label[label]
        if not items:
            continue
        items = sorted(items, key=_sort_key, reverse=True)
        lines.append(f"\n## {label}\n")
        for r in items:
            season_str = f"season {r.season}" if r.season is not None else ""
            date_str = r.published_text
            meta_bits = " | ".join(b for b in [date_str, season_str] if b)
            meta = f" ({meta_bits})" if meta_bits else ""
            lines.append(f"- {r.text}{meta} — {r.source_file}")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    out_outline.parent.mkdir(parents=True, exist_ok=True)
    write_outline(out_outline)

    out_manuscript.parent.mkdir(parents=True, exist_ok=True)
    write_manuscript_draft(by_label, out_manuscript)

    print(f"Wrote {out_md}")
    print(f"Wrote {out_outline}")
    print(f"Wrote {out_manuscript}")


if __name__ == "__main__":
    main()
