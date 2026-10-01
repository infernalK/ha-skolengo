"""Flatten Skolengo's `/schools-info` payload (school news / "actualités")."""
from __future__ import annotations

from bs4 import BeautifulSoup

from .const import NEWS_OWNER_KEY


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


def _file(file: dict | None) -> dict | None:
    """One `schoolInfoFile` (attachment or illustration). The `url` points to
    the school's ENT and generally needs an ENT login to open."""
    if not isinstance(file, dict):
        return None
    return {
        "name": file.get("name"),
        "mime_type": file.get("mimeType"),
        "size": file.get("size"),
        "url": file.get("url"),
    }


def flatten_news(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "date": item.get("publicationDateTime"),
        "title": item.get("title"),
        "summary": item.get("shortContent") or None,
        "content": html_to_text(item.get("content")) or None,
        "url": item.get("url") or item.get("linkedInfoUrl") or item.get("linkedWebSiteUrl"),
        "author": _author_name(item.get("author")),
        "image": _file(item.get("illustration")),
        "attachments": [f for f in (_file(a) for a in item.get("attachments") or []) if f],
    }


def flatten_school_news(items: list[dict] | None) -> list[dict]:
    """Newest first; entries with no title, text or image are dropped."""
    news = [flatten_news(i) for i in items or []]
    news = [n for n in news if n["title"] or n["content"] or n["image"]]
    news.sort(key=lambda n: n["date"] or "", reverse=True)
    return news


def claim_news_sensor(hass, school_id: str, entry_id: str) -> bool:
    """Whether `entry_id` should create its school's news sensor.

    News belongs to the school, so siblings in the same school share one
    sensor (on a "school" device) instead of each getting a copy. The
    first config entry to ask owns it.
    """
    owners: dict[str, str] = hass.data.setdefault(NEWS_OWNER_KEY, {})
    return owners.setdefault(school_id, entry_id) == entry_id


def release_news_sensor(hass, school_id: str, entry_id: str) -> bool:
    """Drop `entry_id`'s ownership (on unload). Returns True if it owned it,
    meaning a sibling entry must be reloaded to take the sensor over."""
    owners: dict[str, str] = hass.data.get(NEWS_OWNER_KEY, {})
    if owners.get(school_id) == entry_id:
        del owners[school_id]
        return True
    return False
