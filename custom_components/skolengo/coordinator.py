"""DataUpdateCoordinator for the Skolengo integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SkolengoApiError, SkolengoAuthError, SkolengoClient, SkolengoTokens
from .const import (
    AGENDA_DAYS_FUTURE,
    AGENDA_DAYS_PAST,
    CONF_ALARM_OFFSET,
    CONF_REFRESH_TOKEN,
    CONF_SCHOOL_EMS_CODE,
    CONF_SCHOOL_ID,
    CONF_SCHOOL_OIDC_WELLKNOWN,
    CONF_STUDENT_ID,
    CONF_STUDENT_NAME,
    CONF_USER_ID,
    DEFAULT_ALARM_OFFSET,
    DOMAIN,
    EVENT_SKOLENGO,
    EVENT_TYPE_NEW_GRADE,
    EVENT_TYPE_NEW_HOMEWORK,
    HOMEWORK_DAYS_FUTURE,
)
from .evaluations import flatten_evaluations
from .homework import flatten_homework

_LOGGER = logging.getLogger(__name__)


@dataclass
class SkolengoData:
    """Container for all data pulled for one student."""

    lessons: list[dict] = field(default_factory=list)
    homework: list[dict] = field(default_factory=list)
    absences: list[dict] = field(default_factory=list)
    evaluations: list[dict] = field(default_factory=list)
    periods: list[dict] = field(default_factory=list)
    student_name: str = ""
    next_alarm: datetime | None = None
    student_info: dict = field(default_factory=dict)


class SkolengoDataUpdateCoordinator(DataUpdateCoordinator[SkolengoData]):
    """Coordinator that fetches timetable/homework/absences/grades."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.entry_id}",
            update_interval=update_interval,
        )
        self.entry = entry
        self.student_id: str = entry.data[CONF_STUDENT_ID]
        self.school_id: str = entry.data[CONF_SCHOOL_ID]
        self.ems_code: str = entry.data[CONF_SCHOOL_EMS_CODE]
        self.wellknown_url: str = entry.data[CONF_SCHOOL_OIDC_WELLKNOWN]
        self.user_id: str = entry.data[CONF_USER_ID]
        self.client: SkolengoClient | None = None
        # Evaluation IDs seen on the previous update, used to detect new
        # grades and fire `new_grade` events; `None` until the first
        # successful update so nothing is fired for pre-existing grades
        # on startup.
        self._known_evaluation_ids: set[str] | None = None
        # Same idea for homework assignments and `new_homework` events.
        self._known_homework_ids: set[str] | None = None

    async def _async_ensure_client(self) -> SkolengoClient:
        if self.client is not None:
            return self.client

        refresh_token = self.entry.data.get(CONF_REFRESH_TOKEN)
        if not refresh_token:
            raise ConfigEntryAuthFailed("No refresh token stored; reauthentication required.")

        def _build_and_refresh() -> SkolengoClient:
            client = SkolengoClient(self.school_id, self.ems_code)
            # Fetch the token endpoint from the discovery doc so we can use
            # the refresh token to obtain a fresh access token.
            discovery = client._fetch_discovery_document(  # noqa: SLF001
                self.wellknown_url, client._session  # noqa: SLF001
            )
            token_endpoint = discovery.get("token_endpoint")
            client.tokens = SkolengoTokens(
                access_token="",
                refresh_token=refresh_token,
                id_token=None,
                expires_at=0,
                token_endpoint=token_endpoint,
            )
            client.refresh_access_token()
            return client

        try:
            self.client = await self.hass.async_add_executor_job(_build_and_refresh)
        except SkolengoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SkolengoApiError as err:
            raise UpdateFailed(str(err)) from err

        self._async_persist_refresh_token()
        return self.client

    def _async_persist_refresh_token(self) -> None:
        """Persist a rotated refresh token into the config entry, if changed."""
        if self.client is None or self.client.tokens is None:
            return
        new_token = self.client.tokens.refresh_token
        if new_token and new_token != self.entry.data.get(CONF_REFRESH_TOKEN):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, CONF_REFRESH_TOKEN: new_token}
            )

    async def _async_update_data(self) -> SkolengoData:
        client = await self._async_ensure_client()

        today = dt_util.now().date()
        agenda_start = today - timedelta(days=AGENDA_DAYS_PAST)
        agenda_end = today + timedelta(days=AGENDA_DAYS_FUTURE)
        homework_end = today + timedelta(days=HOMEWORK_DAYS_FUTURE)

        def _fetch() -> SkolengoData:
            lessons: list[dict] = []
            try:
                agendas = client.get_agenda(self.student_id, agenda_start, agenda_end)
                for day in agendas:
                    lessons.extend(day.get("lessons") or [])
            except SkolengoApiError as err:
                _LOGGER.warning("Unable to fetch agenda: %s", err)

            homework: list[dict] = []
            try:
                homework = client.get_homework(self.student_id, today, homework_end)
            except SkolengoApiError as err:
                _LOGGER.warning("Unable to fetch homework: %s", err)

            absences: list[dict] = []
            try:
                absences = client.get_absences(self.student_id)
            except SkolengoApiError as err:
                # Known to 500 on some schools due to a server-side bug in
                # Skolengo's own API (not something we can fix); never fatal.
                _LOGGER.debug("Unable to fetch absences (non-fatal): %s", err)

            periods: list[dict] = []
            try:
                settings = client.get_evaluations_settings(self.student_id)
                periods = (settings[0].get("periods") or []) if settings else []
            except SkolengoApiError as err:
                # Known to be flaky/unsupported on some schools; never fatal.
                _LOGGER.debug("Unable to fetch evaluation periods (non-fatal): %s", err)

            evaluations: list[dict] = []
            if periods:
                # Fetch evaluations one period (trimester/semester) at a
                # time and tag each evaluationService with its period id,
                # so the sensors/cards can offer a per-period breakdown
                # without extra round-trips when the user switches period.
                for period in periods:
                    period_id = period.get("id")
                    try:
                        period_evaluations = client.get_evaluations(self.student_id, period_id)
                    except SkolengoApiError as err:
                        _LOGGER.debug(
                            "Unable to fetch evaluations for period %s (non-fatal): %s",
                            period_id,
                            err,
                        )
                        continue
                    for service in period_evaluations:
                        service["_period_id"] = period_id
                    evaluations.extend(period_evaluations)
            else:
                # No period info available (endpoint unsupported/flaky for
                # this school) -- fall back to the unfiltered fetch.
                try:
                    evaluations = client.get_evaluations(self.student_id)
                except SkolengoApiError as err:
                    _LOGGER.debug("Unable to fetch evaluations (non-fatal): %s", err)

            alarm_offset = self.entry.options.get(CONF_ALARM_OFFSET, DEFAULT_ALARM_OFFSET)
            next_alarm = _compute_next_alarm(lessons, alarm_offset)

            student_info: dict = {}
            try:
                user_info = client.get_user_info(self.user_id)
                student_info = _find_student_info(user_info, self.student_id)
            except SkolengoApiError as err:
                _LOGGER.debug("Unable to fetch student info (non-fatal): %s", err)

            return SkolengoData(
                lessons=lessons,
                homework=homework,
                absences=absences,
                evaluations=evaluations,
                periods=periods,
                next_alarm=next_alarm,
                student_info=student_info,
            )

        try:
            data = await self.hass.async_add_executor_job(_fetch)
        except SkolengoAuthError as err:
            self.client = None
            raise ConfigEntryAuthFailed(str(err)) from err
        except SkolengoApiError as err:
            raise UpdateFailed(str(err)) from err

        self._async_persist_refresh_token()
        self._async_fire_new_grade_events(data.evaluations)
        self._async_fire_new_homework_events(data.homework)
        return data

    def _async_fire_new_grade_events(self, evaluation_services: list[dict]) -> None:
        """Fire one `skolengo_event` (type `new_grade`) per grade that
        wasn't present on the previous update, mirroring hass-pronote's
        `pronote_event` so automations can react as grades are published.

        Nothing is fired on the very first update after (re)start, since
        every already-existing grade would otherwise look "new".
        """
        items = flatten_evaluations(evaluation_services)
        current_ids = {item["id"] for item in items if item.get("id")}

        if self._known_evaluation_ids is not None:
            new_ids = current_ids - self._known_evaluation_ids
            if new_ids:
                student_name = self.entry.data.get(CONF_STUDENT_NAME, "")
                for item in items:
                    if item.get("id") in new_ids:
                        self.hass.bus.async_fire(
                            EVENT_SKOLENGO,
                            {
                                "type": EVENT_TYPE_NEW_GRADE,
                                "student_name": student_name,
                                **item,
                            },
                        )

        self._known_evaluation_ids = current_ids

    def _async_fire_new_homework_events(self, homework: list[dict]) -> None:
        """Fire one `skolengo_event` (type `new_homework`) per assignment
        that wasn't present on the previous update, mirroring
        `_async_fire_new_grade_events`.

        Nothing is fired on the very first update after (re)start, since
        every already-existing assignment would otherwise look "new".
        """
        current_ids = {hw["id"] for hw in homework if hw.get("id")}

        if self._known_homework_ids is not None:
            new_ids = current_ids - self._known_homework_ids
            if new_ids:
                student_name = self.entry.data.get(CONF_STUDENT_NAME, "")
                for hw in homework:
                    if hw.get("id") in new_ids:
                        self.hass.bus.async_fire(
                            EVENT_SKOLENGO,
                            {
                                "type": EVENT_TYPE_NEW_HOMEWORK,
                                "student_name": student_name,
                                **flatten_homework(hw),
                            },
                        )

        self._known_homework_ids = current_ids


def _find_student_info(user_info: dict, student_id: str) -> dict:
    """Locate this student's record within a `getUserInfo()` response.

    For a legal-representative (parent) account, the student is one entry
    of the `students` relationship; for a student account logging in
    directly, `user_info` itself already *is* the student.
    """
    for student in user_info.get("students") or []:
        if student.get("id") == student_id:
            return student
    if user_info.get("id") == student_id or not user_info.get("students"):
        return user_info
    return {}


def _compute_next_alarm(lessons: list[dict], offset_minutes: int) -> datetime | None:
    """First lesson of the next school day (today included), minus offset.

    Groups non-canceled lessons by local calendar day and walks days in
    chronological order (skipping weekends/holidays, which simply have no
    lessons). For each day, the alarm would be that day's earliest lesson
    start time minus `offset_minutes`; the first such alarm time that is
    still in the future is returned -- so once today's alarm has passed
    (or there are no lessons left today), it automatically rolls over to
    the next day that actually has lessons.
    """
    now = dt_util.now()
    by_day: dict[date, list[datetime]] = {}

    for lesson in lessons:
        if lesson.get("canceled"):
            continue
        start = dt_util.parse_datetime(lesson.get("startDateTime") or "")
        if not start:
            continue
        start = dt_util.as_local(start)
        by_day.setdefault(start.date(), []).append(start)

    for day in sorted(by_day):
        if day < now.date():
            continue
        first_start = min(by_day[day])
        alarm_time = first_start - timedelta(minutes=offset_minutes)
        if alarm_time > now:
            return alarm_time

    return None
