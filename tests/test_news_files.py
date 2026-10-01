import asyncio
from types import SimpleNamespace

from custom_components.skolengo.api import SkolengoApiError
from custom_components.skolengo.const import DOMAIN
from custom_components.skolengo.news import find_news_file, is_allowed_file_url
from custom_components.skolengo.news_files import SkolengoNewsFileView

WELLKNOWN = "https://cas.moncollege.valdemarne.fr/.well-known/openid-configuration"
FILE_URL = "https://du-parc-sucy-en-brie.moncollege.valdemarne.fr/lectureFichiergw.do?ID_FICHIER=17415"

NEWS = [
    {
        "id": "n1",
        "image": {"id": "17414", "name": "poster.png", "url": FILE_URL.replace("17415", "17414")},
        "attachments": [{"id": "17415", "name": "liste.pdf", "url": FILE_URL}],
    }
]


def test_token_is_only_sent_to_the_schools_own_domain():
    assert is_allowed_file_url(FILE_URL, WELLKNOWN)
    assert not is_allowed_file_url(FILE_URL.replace("https", "http"), WELLKNOWN)
    assert not is_allowed_file_url("https://evil.example.com/x", WELLKNOWN)
    assert not is_allowed_file_url("https://valdemarne.fr.evil.com/x", WELLKNOWN)
    assert not is_allowed_file_url(None, WELLKNOWN)
    assert not is_allowed_file_url("javascript:alert(1)", WELLKNOWN)


def test_find_news_file_looks_in_image_and_attachments():
    assert find_news_file(NEWS, "17414")["name"] == "poster.png"
    assert find_news_file(NEWS, 17415)["name"] == "liste.pdf"
    assert find_news_file(NEWS, "999") is None


def _call(entry_id, file_id, content=b"%PDF", content_type="application/pdf", error=None, news=NEWS):
    calls = []

    def download(url):
        calls.append(url)
        if error:
            raise error
        return content, content_type

    coordinator = SimpleNamespace(
        client=SimpleNamespace(download_file=download),
        data=SimpleNamespace(news=news),
        wellknown_url=WELLKNOWN,
    )

    async def run_in_executor(func, *args):
        return func(*args)

    hass = SimpleNamespace(data={DOMAIN: {"entry-1": coordinator}}, async_add_executor_job=run_in_executor)
    request = SimpleNamespace(app={"hass": hass})
    response = asyncio.run(SkolengoNewsFileView().get(request, entry_id, file_id))
    return response, calls


def test_serves_a_listed_file_inline_for_pdf_and_images():
    response, calls = _call("entry-1", "17415")
    assert response.status == 200 and calls == [FILE_URL]
    assert response.headers["Content-Disposition"].startswith("inline")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" not in response.headers["Content-Security-Policy"]  # would break the PDF viewer

    response, _ = _call("entry-1", "17414", content_type="image/png")
    assert response.content_type == "image/png"


def test_html_and_svg_are_never_served_inline():
    for dangerous in ("text/html", "image/svg+xml", "application/javascript"):
        response, _ = _call("entry-1", "17415", content_type=dangerous)
        assert response.content_type == "application/octet-stream"
        assert response.headers["Content-Disposition"].startswith("attachment")
        assert "sandbox" in response.headers["Content-Security-Policy"]


def test_unknown_entry_or_unlisted_file_is_404_and_nothing_is_fetched():
    assert _call("other-entry", "17415")[0].status == 404
    response, calls = _call("entry-1", "not-in-the-news")
    assert response.status == 404 and calls == []


def test_file_on_another_host_is_refused_without_downloading():
    evil = [{"id": "1", "image": {"id": "1", "name": "x", "url": "https://evil.example.com/x"}, "attachments": []}]
    response, calls = _call("entry-1", "1", news=evil)
    assert response.status == 403 and calls == []


def test_download_failure_is_a_502():
    response, _ = _call("entry-1", "17415", error=SkolengoApiError("boom"))
    assert response.status == 502
