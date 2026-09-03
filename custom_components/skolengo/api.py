"""Lightweight, unofficial Skolengo API client.

This module implements just enough of the Skolengo ("bff-sko-app") JSON:API
to authenticate a user against their school's identity provider (OpenID
Connect, fronted by a CAS/SSO login form that varies from school to school)
and to pull the timetable (agenda), homework, absences and evaluations for a
student.

This is a community reverse-engineered client. It is NOT affiliated with,
endorsed by, or supported by Skolengo / Index Education. It may break at any
time if Skolengo changes their API or login pages.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .const import (
    API_BASE_URL,
    HOMEWORK_AGENDA_LOOKBACK_DAYS,
    OID_CLIENT_ID_B64,
    OID_CLIENT_SECRET_B64,
    REDIRECT_URI,
)

_LOGGER = logging.getLogger(__name__)

OID_CLIENT_ID = base64.b64decode(OID_CLIENT_ID_B64).decode()
OID_CLIENT_SECRET = base64.b64decode(OID_CLIENT_SECRET_B64).decode()

MAX_REDIRECT_HOPS = 30
USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Mobile Safari/537.36 SkoApp/HomeAssistant"
)

# Best-effort field name guesses for generic CAS/SSO login forms.
USERNAME_FIELD_CANDIDATES = (
    "username",
    "email",
    "identifiant",
    "login",
    "j_username",
    "casusername",
    "user",
)
PASSWORD_FIELD_CANDIDATES = (
    "password",
    "pwd",
    "j_password",
    "caspassword",
    "pass",
)


class SkolengoError(Exception):
    """Base error for the Skolengo client."""


class SkolengoAuthError(SkolengoError):
    """Raised when authentication fails (bad credentials, unsupported login page, etc.)."""


class SkolengoApiError(SkolengoError):
    """Raised when a call to the Skolengo API fails."""


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode (without verifying) the payload of a JWT."""
    try:
        payload_b64 = token.split(".")[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(payload)
    except Exception as err:  # noqa: BLE001
        raise SkolengoAuthError(f"Unable to decode id_token: {err}") from err


def jsonapi_deserialize(document: dict[str, Any]) -> Any:
    """Flatten a JSON:API document (data + included) into plain nested dicts.

    This is a small, self-contained reimplementation of what the
    `json_api_doc` package does, so we avoid depending on a niche third
    party library for ~40 lines of logic.
    """
    included = document.get("included", [])
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for res in included:
        index[(res.get("type"), res.get("id"))] = res

    def resolve(resource: dict[str, Any], _seen: set[tuple[str, str]] | None = None) -> dict[str, Any]:
        _seen = _seen or set()
        key = (resource.get("type"), resource.get("id"))
        out: dict[str, Any] = {"id": resource.get("id"), "type": resource.get("type")}
        out.update(resource.get("attributes", {}) or {})
        relationships = resource.get("relationships", {}) or {}
        for rel_name, rel_body in relationships.items():
            rel_data = (rel_body or {}).get("data")
            if rel_data is None:
                out[rel_name] = None
            elif isinstance(rel_data, list):
                items = []
                for item in rel_data:
                    item_key = (item.get("type"), item.get("id"))
                    if item_key in _seen:
                        continue
                    full = index.get(item_key, item)
                    items.append(resolve(full, _seen | {key}))
                out[rel_name] = items
            else:
                item_key = (rel_data.get("type"), rel_data.get("id"))
                if item_key in _seen:
                    out[rel_name] = None
                else:
                    full = index.get(item_key, rel_data)
                    out[rel_name] = resolve(full, _seen | {key})
        return out

    data = document.get("data")
    if data is None:
        return None
    if isinstance(data, list):
        return [resolve(item) for item in data]
    return resolve(data)


@dataclass
class SkolengoTokens:
    access_token: str
    refresh_token: str | None
    id_token: str | None
    expires_at: float
    token_endpoint: str

    @property
    def is_expired(self) -> bool:
        return time.time() >= (self.expires_at - 30)


@dataclass
class SkolengoSchool:
    id: str
    name: str
    ems_code: str
    oidc_wellknown_url: str
    city: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class SkolengoClient:
    """Client handling authentication and data retrieval for one student."""

    def __init__(
        self,
        school_id: str,
        ems_code: str,
        tokens: SkolengoTokens | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.school_id = school_id
        self.ems_code = ems_code
        self.tokens = tokens
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT})

    # ------------------------------------------------------------------
    # School lookup
    # ------------------------------------------------------------------
    # French stopwords that, when present alongside other search terms,
    # cause Skolengo's own `/schools?filter[text]` search to return zero
    # results (observed empirically: "sucy en brie" -> 0 hits, "sucy brie"
    # -> 2 hits, "sucy" alone -> 3 hits). Many French place names contain
    # them (e.g. "Sucy-en-Brie"), so we retry without them if the raw query
    # comes back empty.
    _FR_STOPWORDS = {
        "en", "de", "des", "du", "le", "la", "les", "l", "d",
        "et", "sur", "sous", "aux", "au", "a", "à",
    }

    @classmethod
    def _strip_stopwords(cls, text: str) -> str | None:
        tokens = [t for t in text.replace("-", " ").split() if t.lower() not in cls._FR_STOPWORDS]
        stripped = " ".join(tokens)
        return stripped if stripped and stripped.lower() != text.lower() else None

    @classmethod
    def search_schools(cls, text: str, session: requests.Session | None = None) -> list[SkolengoSchool]:
        session = session or requests.Session()
        session.headers.setdefault("User-Agent", USER_AGENT)

        schools = cls._search_schools_raw(text, session)
        if not schools:
            fallback = cls._strip_stopwords(text)
            if fallback:
                schools = cls._search_schools_raw(fallback, session)
        return schools

    @staticmethod
    def _search_schools_raw(text: str, session: requests.Session) -> list[SkolengoSchool]:
        try:
            resp = session.get(
                f"{API_BASE_URL}/schools",
                params={"page[limit]": 25, "page[offset]": 0, "filter[text]": text},
                timeout=20,
            )
            resp.raise_for_status()
        except requests.RequestException as err:
            raise SkolengoApiError(f"Unable to search schools: {err}") from err

        try:
            items = jsonapi_deserialize(resp.json()) or []
        except ValueError as err:
            raise SkolengoApiError(f"Invalid response while searching schools: {err}") from err

        schools: list[SkolengoSchool] = []
        for item in items:
            wellknown = item.get("emsOIDCWellKnownUrl")
            if not wellknown:
                continue
            schools.append(
                SkolengoSchool(
                    id=item["id"],
                    name=item.get("name") or item.get("city") or item["id"],
                    ems_code=item.get("emsCode", ""),
                    oidc_wellknown_url=wellknown,
                    city=item.get("city"),
                    raw=item,
                )
            )
        return schools

    # ------------------------------------------------------------------
    # OIDC login (generic CAS/SSO HTML form scraping)
    # ------------------------------------------------------------------
    @classmethod
    def login(
        cls,
        school: SkolengoSchool,
        username: str,
        password: str,
    ) -> "SkolengoClient":
        """Perform the full OIDC authorization-code login flow for a school.

        Because the redirect_uri is a mobile-app-only custom URI scheme
        (`skoapp-prod://sign-in-callback`), we can't literally follow the
        final redirect. Instead we manually walk the HTTP redirect chain
        and pull the `code` query parameter off the first `Location` header
        that starts with that scheme.
        """
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        discovery = cls._fetch_discovery_document(school.oidc_wellknown_url, session)
        authorization_endpoint = discovery.get("authorization_endpoint")
        token_endpoint = discovery.get("token_endpoint")
        if not authorization_endpoint or not token_endpoint:
            raise SkolengoAuthError(
                "The school's identity provider discovery document is missing "
                "authorization_endpoint/token_endpoint."
            )

        scopes_supported = discovery.get("scopes_supported") or []
        wanted_scopes = ["openid", "profile", "email", "offline_access"]
        scopes = [s for s in wanted_scopes if s in scopes_supported] or ["openid"]

        auth_params = {
            "response_type": "code",
            "client_id": OID_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": " ".join(scopes),
            "state": "ha-skolengo",
        }

        try:
            resp = session.get(
                authorization_endpoint, params=auth_params, timeout=20, allow_redirects=False
            )
        except requests.RequestException as err:
            raise SkolengoAuthError(f"Unable to reach the authorization endpoint: {err}") from err

        auth_url = resp.url
        code = cls._walk_redirect_chain(
            session, resp, auth_url, username=username, password=password
        )

        if not code:
            raise SkolengoAuthError(
                "Could not obtain an authorization code from the school's login "
                "flow. The login page format may not be supported."
            )

        return cls._exchange_code(school, session, token_endpoint, code)

    @staticmethod
    def _fetch_discovery_document(wellknown_url: str, session: requests.Session) -> dict[str, Any]:
        try:
            resp = session.get(wellknown_url, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as err:
            raise SkolengoAuthError(f"Unable to fetch OIDC discovery document: {err}") from err

    @staticmethod
    def _extract_code_from_url(url: str) -> str | None:
        if not url:
            return None
        if url.startswith(REDIRECT_URI) or "code=" in url:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            codes = qs.get("code")
            if codes:
                return codes[0]
        return None

    @staticmethod
    def _find_meta_refresh_url(page_url: str, html: str) -> str | None:
        """Return the target URL of a `<meta http-equiv="refresh">` tag, if any.

        Several French ENT/SSO relay pages (intermediate hops in federated
        login chains such as Éduconnect or SAML-based academic portals) use
        a meta-refresh instead of an HTTP 30x redirect between steps.
        """
        soup = BeautifulSoup(html, "html.parser")
        for meta in soup.find_all("meta"):
            if (meta.get("http-equiv") or "").lower() != "refresh":
                continue
            content = meta.get("content") or ""
            # Content looks like "0;url=https://..." or "0; URL='https://...'"
            _, _, rest = content.partition(";")
            rest = rest.strip()
            if rest.lower().startswith("url="):
                target = rest[4:].strip().strip("'\"")
                if target:
                    return urljoin(page_url, target)
        return None

    @classmethod
    def _fill_and_submit_form(
        cls,
        session: requests.Session,
        page_response: requests.Response,
        username: str,
        password: str,
        allow_relay: bool,
    ) -> tuple[requests.Response, bool]:
        """Parse a generic CAS/SSO page and POST credentials (or relay it).

        Some federated login chains (Éduconnect, SAML-based academic
        portals, ...) insert intermediate "relay" pages between the actual
        login page and the final redirect: an auto-submitting form made
        only of hidden fields (e.g. a SAML POST binding), with no
        identifier/password to fill in. When `allow_relay` is True and no
        credential fields are found, such a form is submitted as-is instead
        of raising, and the second return value is False (no credentials
        were actually submitted yet, so the caller should keep waiting for
        the real login page).
        """
        page_url = page_response.url
        soup = BeautifulSoup(page_response.text, "html.parser")
        form = soup.find("form")
        if form is None:
            raise SkolengoAuthError(
                "Impossible de trouver le formulaire de connexion sur la page de "
                "l'établissement (login form not found)."
            )

        action = form.get("action") or page_url
        post_url = urljoin(page_url, action)
        method = (form.get("method") or "get").strip().lower()

        form_data: dict[str, str] = {}
        username_field = None
        password_field = None
        radio_groups: dict[str, list[tuple[Any, str]]] = {}

        for input_tag in form.find_all("input"):
            name = input_tag.get("name")
            if not name:
                continue
            input_type = (input_tag.get("type") or "text").lower()
            value = input_tag.get("value", "")

            if input_type == "hidden":
                form_data[name] = value
                continue

            if input_type == "radio":
                radio_groups.setdefault(name, []).append((input_tag, value))
                if input_tag.get("checked"):
                    form_data[name] = value
                continue

            lower_name = name.lower()
            if input_type == "password" or any(c in lower_name for c in PASSWORD_FIELD_CANDIDATES):
                password_field = name
                continue
            if input_type in ("text", "email") or any(
                c in lower_name for c in USERNAME_FIELD_CANDIDATES
            ):
                username_field = name
                continue
            # Any other visible input (e.g. a submit button with a name) gets
            # its default value carried through.
            if input_type in ("submit", "checkbox"):
                if input_type == "checkbox" and not input_tag.get("checked"):
                    continue
                form_data[name] = value or "on"

        # Some login pages (e.g. Éduconnect) use <button name="..."> rather
        # than <input type="submit" name="...">  for their submit control.
        # Browsers include a clicked submit <button>'s name/value in the
        # form payload; since we can't "click" one, include the first named
        # submit button found — omitting it entirely causes some servers to
        # silently ignore the submission instead of validating credentials.
        submit_button_included = False
        for button_tag in form.find_all("button"):
            name = button_tag.get("name")
            if not name or submit_button_included:
                continue
            button_type = (button_tag.get("type") or "submit").lower()
            if button_type != "submit":
                continue
            form_data[name] = button_tag.get("value") or ""
            submit_button_included = True

        # Some establishments (typically public schools using the national
        # Éduconnect / academic SSO federation) present a "Where Are You
        # From" identity-provider picker before the real login page: a set
        # of radio buttons ("Élève ou parent", "Personnel", ...) with no
        # username/password field of their own. Best-effort default to the
        # "student/parent" option, since that's what the vast majority of
        # Home Assistant users authenticating here will be.
        if not username_field and not password_field:
            for group_name, options in radio_groups.items():
                if group_name in form_data:
                    continue  # already had a `checked` option
                choice = cls._pick_wayf_radio_option(options)
                if choice is not None:
                    form_data[group_name] = choice

        if not username_field or not password_field:
            if allow_relay:
                # Likely a WAYF picker (handled above) or an auto-submitting
                # relay/continue form (e.g. SAML POST binding) rather than
                # the actual login page.
                resp = cls._submit_form(session, post_url, method, form_data)
                return resp, False
            raise SkolengoAuthError(
                "Impossible d'identifier les champs identifiant/mot de passe du "
                "formulaire de connexion (unrecognized login form)."
            )

        form_data[username_field] = username
        form_data[password_field] = password

        resp = cls._submit_form(session, post_url, method, form_data)
        return resp, True

    @staticmethod
    def _submit_form(
        session: requests.Session, url: str, method: str, form_data: dict[str, str]
    ) -> requests.Response:
        try:
            if method == "get":
                return session.get(url, params=form_data, timeout=20, allow_redirects=False)
            return session.post(url, data=form_data, timeout=20, allow_redirects=False)
        except requests.RequestException as err:
            raise SkolengoAuthError(f"Form submission failed: {err}") from err

    # Keywords (matched against the radio's <label>, id or value) used to
    # pick the most likely "I'm a student/parent" option on a WAYF-style
    # identity-provider picker.
    _WAYF_PREFERRED_KEYWORDS = ("eleve", "élève", "parent", "educonnect", "éduconnect", "famille")

    @staticmethod
    def _pick_wayf_radio_option(options: list[tuple[Any, str]]) -> str | None:
        if not options:
            return None

        def option_text(input_tag: Any) -> str:
            parts = [input_tag.get("id") or "", input_tag.get("value") or ""]
            input_id = input_tag.get("id")
            if input_id:
                label = input_tag.find_parent().find("label", attrs={"for": input_id}) if input_tag.find_parent() else None
                if label is None:
                    # Search the whole document as a fallback (label may not
                    # be a sibling of the radio input).
                    root = input_tag
                    while root.parent is not None:
                        root = root.parent
                    label = root.find("label", attrs={"for": input_id})
                if label is not None:
                    parts.append(label.get_text())
            return " ".join(parts).lower()

        for input_tag, value in options:
            text = option_text(input_tag)
            if any(keyword in text for keyword in SkolengoClient._WAYF_PREFERRED_KEYWORDS):
                return value

        # No confident match: fall back to the first listed option rather
        # than failing outright.
        return options[0][1]

    @classmethod
    def _walk_redirect_chain(
        cls,
        session: requests.Session,
        response: requests.Response,
        current_url: str,
        username: str,
        password: str,
    ) -> str | None:
        """Manually follow redirects (since requests can't follow a custom
        non-HTTP URI scheme) until we hit the redirect_uri carrying `code`,
        submitting the login form (once) if/when we land on it.
        """
        resp = response
        url = current_url
        credentials_submitted = False

        for _ in range(MAX_REDIRECT_HOPS):
            code = cls._extract_code_from_url(resp.url)
            if code:
                return code

            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if not location:
                    return None
                if location.startswith(REDIRECT_URI):
                    return cls._extract_code_from_url(location)
                next_url = urljoin(url, location)
                try:
                    resp = session.get(next_url, timeout=20, allow_redirects=False)
                except requests.RequestException as err:
                    raise SkolengoAuthError(f"Redirect follow-up failed: {err}") from err
                url = next_url
                continue

            if resp.status_code == 200:
                meta_url = cls._find_meta_refresh_url(resp.url, resp.text)
                if meta_url:
                    # Relay page using <meta refresh> instead of an HTTP
                    # redirect (common in some federated ENT login chains).
                    if meta_url.startswith(REDIRECT_URI):
                        return cls._extract_code_from_url(meta_url)
                    try:
                        resp = session.get(meta_url, timeout=20, allow_redirects=False)
                    except requests.RequestException as err:
                        raise SkolengoAuthError(f"Meta-refresh follow-up failed: {err}") from err
                    url = meta_url
                    continue

                prev_resp = resp
                resp, was_credentials = cls._fill_and_submit_form(
                    session, resp, username, password, allow_relay=True
                )
                if was_credentials and credentials_submitted:
                    # A credential-looking login form was shown twice in a
                    # row: treat it as invalid credentials rather than loop
                    # forever on an unsupported flow.
                    lowered = prev_resp.text.lower()
                    if any(
                        kw in lowered
                        for kw in ("mot de passe", "password", "identifiant", "incorrect", "erreur")
                    ):
                        raise SkolengoAuthError(
                            "Identifiants incorrects, ou formulaire de connexion "
                            "réaffiché (invalid credentials or unsupported login flow)."
                        )
                url = resp.url or url
                credentials_submitted = credentials_submitted or was_credentials
                continue

            return None

        return None

    @classmethod
    def _exchange_code(
        cls, school: SkolengoSchool, session: requests.Session, token_endpoint: str, code: str
    ) -> "SkolengoClient":
        try:
            resp = session.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": OID_CLIENT_ID,
                    "client_secret": OID_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as err:
            raise SkolengoAuthError(f"Token exchange failed: {err}") from err

        tokens = SkolengoTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            id_token=payload.get("id_token"),
            expires_at=time.time() + float(payload.get("expires_in", 3600)),
            token_endpoint=token_endpoint,
        )
        client = cls(school.id, school.ems_code, tokens=tokens, session=session)
        return client

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------
    def refresh_access_token(self) -> None:
        if not self.tokens or not self.tokens.refresh_token:
            raise SkolengoAuthError("No refresh token available; user must log in again.")
        try:
            resp = self._session.post(
                self.tokens.token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.tokens.refresh_token,
                    "client_id": OID_CLIENT_ID,
                    "client_secret": OID_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as err:
            raise SkolengoAuthError(f"Unable to refresh access token: {err}") from err

        self.tokens = SkolengoTokens(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token", self.tokens.refresh_token),
            id_token=payload.get("id_token", self.tokens.id_token),
            expires_at=time.time() + float(payload.get("expires_in", 3600)),
            token_endpoint=self.tokens.token_endpoint,
        )

    def get_user_id(self) -> str:
        if not self.tokens or not self.tokens.id_token:
            raise SkolengoAuthError("Missing id_token; cannot determine user id.")
        claims = _decode_jwt_payload(self.tokens.id_token)
        sub = claims.get("sub")
        if not sub:
            raise SkolengoAuthError("id_token has no 'sub' claim.")
        return sub

    # ------------------------------------------------------------------
    # Generic authenticated request helper
    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        if not self.tokens:
            raise SkolengoAuthError("Client is not authenticated.")
        return {
            "Authorization": f"Bearer {self.tokens.access_token}",
            "X-Skolengo-Date-Format": "utc",
            "X-Skolengo-School-Id": self.school_id,
            "X-Skolengo-Ems-Code": self.ems_code,
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        if self.tokens and self.tokens.is_expired:
            self.refresh_access_token()

        url = f"{API_BASE_URL}{path}"
        try:
            resp = self._session.request(
                method, url, params=params, headers=self._headers(), timeout=30
            )
        except requests.RequestException as err:
            raise SkolengoApiError(f"Request to {path} failed: {err}") from err

        if resp.status_code == 401:
            # Try a single refresh + retry.
            self.refresh_access_token()
            try:
                resp = self._session.request(
                    method, url, params=params, headers=self._headers(), timeout=30
                )
            except requests.RequestException as err:
                raise SkolengoApiError(f"Request to {path} failed after refresh: {err}") from err
            if resp.status_code == 401:
                raise SkolengoAuthError("Authentication expired; re-authentication required.")

        if resp.status_code >= 400:
            raise SkolengoApiError(f"Skolengo API error {resp.status_code} on {path}: {resp.text[:300]}")

        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as err:
            raise SkolengoApiError(f"Invalid JSON response from {path}: {err}") from err

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    def get_user_info(self, user_id: str) -> dict[str, Any]:
        # `include` is required for JSON:API to resolve the `students`
        # relationship (a legal representative/parent account) into full
        # resource objects instead of bare {type, id} references, and the
        # `fields[student]` sparse-fieldset selects which attributes come
        # back on those resolved students -- without it, only the id/type
        # linkage is returned (no firstName/lastName, which is why the
        # config flow would otherwise only have raw ids to show).
        params = {
            "include": "school,students,students.school,schools,prioritySchool",
            "fields[student]": "firstName,lastName,photoUrl,className,dateOfBirth,regime,school",
        }
        doc = self._request("GET", f"/users-info/{user_id}", params=params)
        return jsonapi_deserialize(doc)

    def get_agenda(self, student_id: str, start: date, end: date) -> list[dict[str, Any]]:
        params = {
            "filter[student.id]": student_id,
            "filter[date][GE]": start.isoformat(),
            "filter[date][LE]": end.isoformat(),
            "include": (
                "lessons,lessons.subject,lessons.teachers,"
                "homeworkAssignments,homeworkAssignments.subject"
            ),
            # The API silently paginates at 20 "day" resources per page; a
            # date range spanning more than 20 days would otherwise return
            # only the first 20 days and drop the rest.
            "page[limit]": 100,
        }
        doc = self._request("GET", "/agendas", params=params)
        return jsonapi_deserialize(doc) or []

    def get_homework(self, student_id: str, start: date, end: date) -> list[dict[str, Any]]:
        params = {
            "filter[student.id]": student_id,
            "filter[dueDate][GE]": start.isoformat(),
            "filter[dueDate][LE]": end.isoformat(),
            "page[limit]": 100,
        }
        try:
            doc = self._request("GET", "/homework-assignments", params=params)
            return jsonapi_deserialize(doc) or []
        except SkolengoApiError as err:
            if "Skolengo API error 500" not in str(err):
                raise
            # Server-side bug: Skolengo's API throws a 500 when filtering by
            # dueDate range if any assignment in scope has no due date set,
            # and both bounds of the filter are mandatory (so we can't just
            # drop one). The error detail isn't always present (sometimes
            # it's a bare INTERNAL_SERVER_ERROR with no message), so match
            # on any 500 from this endpoint rather than the specific
            # getDueDateTime message. Fall back to the homework assignments
            # already embedded in the agenda response, which isn't affected.
            _LOGGER.debug(
                "Homework endpoint returned a 500 (likely the Skolengo "
                "no-due-date server bug); falling back to agenda-embedded homework"
            )
            return self._get_homework_via_agenda(student_id, start, end)

    def _get_homework_via_agenda(self, student_id: str, start: date, end: date) -> list[dict[str, Any]]:
        # homeworkAssignments are embedded under the agenda day they were
        # *assigned* on, not their due date, so an assignment given out
        # before `start` but due within [start, end] would otherwise be
        # missed. Query the agenda further back and filter by the
        # assignment's own dueDate to match what the primary endpoint would
        # have returned.
        agenda_start = start - timedelta(days=HOMEWORK_AGENDA_LOOKBACK_DAYS)
        params = {
            "filter[student.id]": student_id,
            "filter[date][GE]": agenda_start.isoformat(),
            "filter[date][LE]": end.isoformat(),
            "include": "homeworkAssignments,homeworkAssignments.subject",
            # See get_agenda: without this, a range over 20 days silently
            # returns only the first 20 days.
            "page[limit]": 100,
        }
        doc = self._request("GET", "/agendas", params=params)
        days = jsonapi_deserialize(doc) or []
        seen: set[str] = set()
        homework: list[dict[str, Any]] = []
        raw_count = 0
        for day in days:
            for hw in day.get("homeworkAssignments") or []:
                raw_count += 1
                hw_id = hw.get("id")
                if hw_id in seen:
                    continue
                due = (hw.get("dueDate") or hw.get("dueDateTime") or "")[:10]
                if due and not (start.isoformat() <= due <= end.isoformat()):
                    continue
                seen.add(hw_id)
                homework.append(hw)
        _LOGGER.debug(
            "Agenda fallback: %d day(s) from %s to %s, %d raw homework "
            "entries, %d kept after dueDate filter",
            len(days), agenda_start, end, raw_count, len(homework),
        )
        return homework

    def set_homework_done(self, homework_id: str, done: bool) -> None:
        url = f"{API_BASE_URL}/homework-assignments/{homework_id}"
        body = {
            "data": {
                "type": "homework",
                "id": homework_id,
                "attributes": {"done": done},
            }
        }
        if self.tokens and self.tokens.is_expired:
            self.refresh_access_token()
        try:
            resp = self._session.patch(
                url,
                json=body,
                headers={**self._headers(), "Content-Type": "application/json"},
                timeout=20,
            )
            resp.raise_for_status()
        except requests.RequestException as err:
            raise SkolengoApiError(f"Unable to update homework {homework_id}: {err}") from err

    def get_absences(self, student_id: str) -> list[dict[str, Any]]:
        params = {"filter[student.id]": student_id}
        doc = self._request("GET", "/absence-files", params=params)
        return jsonapi_deserialize(doc) or []

    def get_evaluations_settings(self, student_id: str) -> list[dict[str, Any]]:
        # `include=periods` is required to resolve the `periods` relationship
        # into full {id, label, startDate, endDate} objects -- without it,
        # only bare {type, id} linkage comes back (confirmed against the
        # reference scolengo-api client, since Skolengo's own docs don't
        # cover this).
        params = {"filter[student.id]": student_id, "include": "periods"}
        doc = self._request("GET", "/evaluations-settings", params=params)
        return jsonapi_deserialize(doc) or []

    def get_evaluations(self, student_id: str, period_id: str | None = None) -> list[dict[str, Any]]:
        """Best-effort: some schools return errors for this endpoint.

        Without an explicit `include`/`fields[...]`, Skolengo's JSON:API
        only returns bare {type, id} linkage for relationships and may
        omit attributes entirely -- notably `average`/`studentAverage`
        (the school's own officially-computed, coefficient-weighted
        subject average) on `evaluationService`, which is what we want to
        show rather than a naively-averaged mean of individual marks.
        """
        params: dict[str, Any] = {
            "filter[student.id]": student_id,
            "include": (
                "subject,teachers,evaluations,"
                "evaluations.evaluationResult,"
                "evaluations.evaluationResult.subSkillsEvaluationResults,"
                "evaluations.evaluationResult.subSkillsEvaluationResults.subSkill,"
                "evaluations.subSkills"
            ),
            "fields[evaluationService]": "coefficient,average,studentAverage,scale,subject,teachers",
            "fields[evaluation]": "title,topic,dateTime,coefficient,average,scale,evaluationResult",
        }
        if period_id:
            params["filter[period.id]"] = period_id
        try:
            doc = self._request("GET", "/evaluation-services", params=params)
        except SkolengoApiError as err:
            _LOGGER.debug("Evaluations endpoint failed (non-fatal): %s", err)
            return []
        return jsonapi_deserialize(doc) or []
