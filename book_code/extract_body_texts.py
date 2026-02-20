from pathlib import Path

from summarize_cash_lineup_reviews import BASE_DIR, extract_article_fields


def extract_body_texts() -> None:
    html_files = sorted(BASE_DIR.glob("*.html"))

    for html_path in html_files:
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        fields = extract_article_fields(html)
        body_text = fields.get("content", "")

        txt_path = html_path.with_suffix(".txt")
        txt_path.write_text(body_text, encoding="utf-8")


def main() -> None:
    extract_body_texts()


if __name__ == "__main__":
    main()
