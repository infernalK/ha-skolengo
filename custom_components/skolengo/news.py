"""Flatten Skolengo's `/schools-info` payload (school news / "actualités")."""
from __future__ import annotations

from bs4 import BeautifulSoup


def html_to_text(html: str | None) -> str:
    """Plain text of a news article's HTML body (paragraphs separated by
    blank lines)."""
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    return "\n".join(line for line in lines if line)


def _author_name(author: dict | None) -> str | None:
    if not isinstance(author, dict):
        return None
    person = author.get("person") or {}
    name = " ".join(str(p) for p in (person.get("title"), person.get("firstName"), person.get("lastName")) if p)
    if name:
        return name
    technical = author.get("technicalUser") or {}
    return technical.get("label") or technical.get("name") or None


def flatten_news(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "date": item.get("publicationDateTime"),
        "title": item.get("title"),
        "summary": item.get("shortContent") or None,
        "content": html_to_text(item.get("content")) or None,
        "url": item.get("url") or item.get("linkedInfoUrl") or item.get("linkedWebSiteUrl"),
        "author": _author_name(item.get("author")),
        "attachments": [a.get("name") or a.get("fileName") for a in item.get("attachments") or [] if isinstance(a, dict)],
    }


def flatten_school_news(items: list[dict] | None) -> list[dict]:
    """Newest first; entries without a title and content are dropped."""
    news = [flatten_news(i) for i in items or []]
    news = [n for n in news if n["title"] or n["content"]]
    news.sort(key=lambda n: n["date"] or "", reverse=True)
    return news
