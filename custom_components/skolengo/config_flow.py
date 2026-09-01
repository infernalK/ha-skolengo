"""Config flow for the Skolengo integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import (
    SkolengoAuthError,
    SkolengoApiError,
    SkolengoClient,
    SkolengoSchool,
)
from .const import (
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_SCHOOL_EMS_CODE,
    CONF_SCHOOL_ID,
    CONF_SCHOOL_NAME,
    CONF_SCHOOL_OIDC_WELLKNOWN,
    CONF_STUDENT_ID,
    CONF_STUDENT_NAME,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SkolengoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Skolengo."""

    VERSION = 1

    def __init__(self) -> None:
        self._schools: list[SkolengoSchool] = []
        self._selected_school: SkolengoSchool | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._client: SkolengoClient | None = None
        self._user_info: dict[str, Any] | None = None
        self._students: list[dict[str, Any]] = []
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: ask for a school search text."""
        errors: dict[str, str] = {}
        if user_input is not None:
            search_text = user_input["school_search"]
            try:
                self._schools = await self.hass.async_add_executor_job(
                    SkolengoClient.search_schools, search_text
                )
            except SkolengoApiError:
                errors["base"] = "cannot_connect"
            else:
                if not self._schools:
                    errors["base"] = "no_school_found"
                else:
                    return await self.async_step_school()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("school_search"): str}),
            errors=errors,
        )

    async def async_step_school(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: pick a school from the search results."""
        errors: dict[str, str] = {}

        if len(self._schools) == 1:
            self._selected_school = self._schools[0]
            return await self.async_step_credentials()

        options = {
            school.id: f"{school.name} ({school.city})" if school.city else school.name
            for school in self._schools
        }

        if user_input is not None:
            school_id = user_input["school_id"]
            self._selected_school = next(
                (s for s in self._schools if s.id == school_id), None
            )
            if self._selected_school is None:
                errors["base"] = "no_school_found"
            else:
                return await self.async_step_credentials()

        return self.async_show_form(
            step_id="school",
            data_schema=vol.Schema({vol.Required("school_id"): vol.In(options)}),
            errors=errors,
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: ask for username/password and perform the login."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input["username"]
            self._password = user_input["password"]
            assert self._selected_school is not None

            try:
                self._client = await self.hass.async_add_executor_job(
                    SkolengoClient.login,
                    self._selected_school,
                    self._username,
                    self._password,
                )
                user_id = await self.hass.async_add_executor_job(
                    self._client.get_user_id
                )
                self._user_info = await self.hass.async_add_executor_job(
                    self._client.get_user_info, user_id
                )
            except SkolengoAuthError as err:
                _LOGGER.warning("Skolengo login failed: %s", err)
                errors["base"] = "invalid_auth"
            except SkolengoApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Skolengo login")
                errors["base"] = "unknown"
            else:
                self._user_info["_user_id"] = user_id
                self._students = self._extract_students(self._user_info)
                if not self._students:
                    errors["base"] = "no_student_found"
                else:
                    if len(self._students) == 1:
                        return await self._finish(self._students[0])
                    return await self.async_step_student()

        return self.async_show_form(
            step_id="credentials",
            data_schema=vol.Schema(
                {vol.Required("username"): str, vol.Required("password"): str}
            ),
            errors=errors,
        )

    async def async_step_student(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4 (parent accounts only): pick which child to track."""
        errors: dict[str, str] = {}
        options = {
            student["id"]: self._student_label(student) for student in self._students
        }

        if user_input is not None:
            student_id = user_input["student_id"]
            student = next(
                (s for s in self._students if s["id"] == student_id), None
            )
            if student is None:
                errors["base"] = "no_student_found"
            else:
                return await self._finish(student)

        return self.async_show_form(
            step_id="student",
            data_schema=vol.Schema({vol.Required("student_id"): vol.In(options)}),
            errors=errors,
        )

    async def _finish(self, student: dict[str, Any]) -> FlowResult:
        assert self._selected_school is not None
        assert self._client is not None

        await self.async_set_unique_id(f"{self._selected_school.id}-{student['id']}")
        self._abort_if_unique_id_configured()

        data = {
            CONF_SCHOOL_ID: self._selected_school.id,
            CONF_SCHOOL_NAME: self._selected_school.name,
            CONF_SCHOOL_EMS_CODE: self._selected_school.ems_code,
            CONF_SCHOOL_OIDC_WELLKNOWN: self._selected_school.oidc_wellknown_url,
            CONF_USER_ID: self._user_info.get("_user_id"),
            CONF_STUDENT_ID: student["id"],
            CONF_STUDENT_NAME: self._student_label(student),
            CONF_REFRESH_TOKEN: self._client.tokens.refresh_token,
        }

        title = f"Skolengo - {self._student_label(student)}"

        if self._reauth_entry is not None:
            self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        return self.async_create_entry(title=title, data=data)

    @staticmethod
    def _extract_students(user_info: dict[str, Any]) -> list[dict[str, Any]]:
        """A Skolengo account can be a student itself, or a legal
        representative (parent) with one or more linked students.
        """
        students = user_info.get("students")
        if students:
            return students
        # The logged-in user is the student themselves.
        if user_info.get("type") in ("student", "students") or user_info.get("id"):
            return [user_info]
        return []

    @staticmethod
    def _student_label(student: dict[str, Any]) -> str:
        first = student.get("firstName", "")
        last = student.get("lastName", "")
        label = f"{first} {last}".strip()
        return label or student.get("id", "Élève")

    # ------------------------------------------------------------------
    # Reauth
    # ------------------------------------------------------------------
    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._selected_school = SkolengoSchool(
            id=entry_data[CONF_SCHOOL_ID],
            name=entry_data.get(CONF_SCHOOL_NAME, ""),
            ems_code=entry_data[CONF_SCHOOL_EMS_CODE],
            oidc_wellknown_url=entry_data[CONF_SCHOOL_OIDC_WELLKNOWN],
        )
        self._students = [
            {
                "id": entry_data[CONF_STUDENT_ID],
                "firstName": entry_data.get(CONF_STUDENT_NAME, ""),
                "lastName": "",
            }
        ]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input["username"]
            self._password = user_input["password"]
            assert self._selected_school is not None
            try:
                self._client = await self.hass.async_add_executor_job(
                    SkolengoClient.login,
                    self._selected_school,
                    self._username,
                    self._password,
                )
            except SkolengoAuthError as err:
                _LOGGER.warning("Skolengo login failed: %s", err)
                errors["base"] = "invalid_auth"
            except SkolengoApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Skolengo reauth")
                errors["base"] = "unknown"
            else:
                return await self._finish(self._students[0])

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {vol.Required("username"): str, vol.Required("password"): str}
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------
    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "SkolengoOptionsFlow":
        return SkolengoOptionsFlow(config_entry)


class SkolengoOptionsFlow(config_entries.OptionsFlow):
    """Options flow: allow changing the polling interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
                    )
                }
            ),
        )
