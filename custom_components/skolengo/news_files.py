"""HTTP view proxying school-news files (illustrations and attachments).

The files live on the school's ENT and normally need an ENT login, so a
browser can't show them directly. This view downloads them with the same API
token the integration uses and serves them to Home Assistant's frontend, via
a signed (temporary) URL created by the card.
"""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .api import SkolengoApiError
from .const import DOMAIN
from .news import find_news_file, is_allowed_file_url

_LOGGER = logging.getLogger(__name__)

NEWS_FILE_URL = "/api/skolengo/news_file/{entry_id}/{file_id}"


class SkolengoNewsFileView(HomeAssistantView):
    """Serves one news file, only if it belongs to the current news data."""

    url = NEWS_FILE_URL
    name = "api:skolengo:news_file"
    requires_auth = True

    async def get(self, request: web.Request, entry_id: str, file_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
        if coordinator is None or coordinator.client is None or coordinator.data is None:
            return web.Response(status=404)

        # Only files listed in the news we fetched ourselves can be served:
        # the caller never chooses the URL.
        file = find_news_file(coordinator.data.news, file_id)
        if file is None:
            return web.Response(status=404)
        if not is_allowed_file_url(file.get("url"), coordinator.wellknown_url):
            _LOGGER.warning("Refusing to fetch a news file from an unexpected host")
            return web.Response(status=403)

        try:
            content, content_type = await hass.async_add_executor_job(
                coordinator.client.download_file, file["url"]
            )
        except SkolengoApiError as err:
            _LOGGER.debug("News file %s could not be downloaded: %s", file_id, err)
            return web.Response(status=502)

        filename = (file.get("name") or "file").replace('"', "").replace("\r", "").replace("\n", "")
        # The file comes from a third party but is served from Home Assistant's
        # own origin: only raster images and PDFs are shown inline; anything
        # else (HTML, SVG, ...) is forced to download as opaque bytes.
        inline = (content_type.startswith("image/") and content_type != "image/svg+xml") or content_type == "application/pdf"
        if not inline:
            content_type = "application/octet-stream"
        return web.Response(
            body=content,
            content_type=content_type,
            headers={
                "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="{filename}"',
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
                # `sandbox` would break the browsers' built-in PDF viewer.
                "Content-Security-Policy": "default-src 'none'" + ("" if content_type == "application/pdf" else "; sandbox"),
            },
        )
