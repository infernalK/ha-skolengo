from types import SimpleNamespace

from custom_components.skolengo.const import EVENT_SKOLENGO, EVENT_TYPE_NEW_NEWS, NEWS_SEEN_KEY
from custom_components.skolengo.coordinator import SkolengoDataUpdateCoordinator
from custom_components.skolengo.news import flatten_school_news, html_to_text

RAW = [
    {
        "id": "n1",
        "publicationDateTime": "2026-09-30T10:12:46Z",
        "title": "Vente de Chocolats",
        "shortContent": "Les 5èmes participent…",
        "content": "<html><body><p><b>Les 5èmes participent.</b></p><p>Merci pour votre soutien</p></body></html>",
        "url": None,
        "linkedInfoUrl": None,
        "linkedWebSiteUrl": "https://example.org/vente",
        "author": {"person": {"title": "Mme", "firstName": "Anne", "lastName": "Lemaitre"}},
        "attachments": [{"name": "affiche.pdf"}],
    },
    {"id": "n0", "publicationDateTime": "2026-09-10T15:14:06Z", "title": "Photo", "content": "<html></html>"},
    {"id": "empty", "publicationDateTime": "2026-09-11T00:00:00Z", "title": "", "content": "<html><body></body></html>"},
]


def test_flatten_orders_newest_first_and_cleans_content():
    news = flatten_school_news(RAW)

    assert [n["id"] for n in news] == ["n1", "n0"]  # empty article dropped
    first = news[0]
    assert first["content"] == "Les 5èmes participent.\nMerci pour votre soutien"
    assert first["author"] == "Mme Anne Lemaitre"
    assert first["url"] == "https://example.org/vente"
    assert first["attachments"] == ["affiche.pdf"]


def test_html_to_text_handles_empty():
    assert html_to_text(None) == ""
    assert html_to_text("<html><head></head><body> \n </body></html>") == ""


def _coordinator(hass_data, school_id="school-1"):
    coordinator = object.__new__(SkolengoDataUpdateCoordinator)
    fired = []
    coordinator.hass = SimpleNamespace(
        data=hass_data, bus=SimpleNamespace(async_fire=lambda name, data: fired.append((name, data)))
    )
    coordinator.entry = SimpleNamespace(data={"school_name": "Collège du Parc"})
    coordinator.school_id = school_id
    return coordinator, fired


def test_no_event_on_first_sight_then_new_article_fires_once():
    data: dict = {}
    coordinator, fired = _coordinator(data)

    coordinator._async_fire_news_events([{"id": "n0", "title": "Photo"}])  # noqa: SLF001
    assert fired == []

    coordinator._async_fire_news_events([{"id": "n1", "title": "Vente"}, {"id": "n0", "title": "Photo"}])  # noqa: SLF001

    assert [(name, d["type"], d["id"]) for name, d in fired] == [(EVENT_SKOLENGO, EVENT_TYPE_NEW_NEWS, "n1")]
    assert fired[0][1]["school_name"] == "Collège du Parc"


def test_siblings_of_the_same_school_do_not_double_fire():
    data: dict = {}
    first, fired = _coordinator(data)
    second, fired_second = _coordinator(data)
    second.hass.bus = first.hass.bus  # same bus, as in Home Assistant

    for coordinator in (first, second):
        coordinator._async_fire_news_events([{"id": "n0", "title": "Photo"}])  # noqa: SLF001
    for coordinator in (first, second):
        coordinator._async_fire_news_events([{"id": "n1", "title": "Vente"}, {"id": "n0", "title": "Photo"}])  # noqa: SLF001

    assert len(fired) == 1
    assert NEWS_SEEN_KEY in data


def test_empty_fetch_is_ignored():
    data: dict = {}
    coordinator, fired = _coordinator(data)
    coordinator._async_fire_news_events([{"id": "n0", "title": "Photo"}])  # noqa: SLF001
    coordinator._async_fire_news_events([])  # noqa: SLF001
    coordinator._async_fire_news_events([{"id": "n0", "title": "Photo"}])  # noqa: SLF001

    assert fired == []


def test_only_the_first_entry_of_a_school_owns_the_news_sensor():
    from custom_components.skolengo.news import claim_news_sensor, release_news_sensor

    hass = SimpleNamespace(data={})

    assert claim_news_sensor(hass, "school-1", "entry-a") is True
    assert claim_news_sensor(hass, "school-1", "entry-a") is True  # idempotent for the owner
    assert claim_news_sensor(hass, "school-1", "entry-b") is False  # sibling
    assert claim_news_sensor(hass, "school-2", "entry-c") is True  # other school

    assert release_news_sensor(hass, "school-1", "entry-b") is False  # not the owner
    assert release_news_sensor(hass, "school-1", "entry-a") is True
    assert claim_news_sensor(hass, "school-1", "entry-b") is True  # sibling takes over
