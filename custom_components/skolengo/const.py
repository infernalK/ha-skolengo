"""Constants for the Skolengo integration."""
from datetime import timedelta

DOMAIN = "skolengo"

# --- Skolengo / Skoapp public OIDC client identifiers ---
# These are the identifiers used by the official "Skolengo" mobile app.
# They are not secret in any meaningful sense (they ship inside the public
# mobile app APK/IPA) and are required to complete the standard OpenID
# Connect Authorization Code flow against each school's identity provider.
OID_CLIENT_ID_B64 = "U2tvQXBwLlByb2QuMGQzNDkyMTctOWE0ZS00MWVjLTlhZjktZGY5ZTY5ZTA5NDk0"
OID_CLIENT_SECRET_B64 = "N2NiNGQ5YTgtMjU4MC00MDQxLTlhZTgtZDU4MDM4NjkxODNm"
REDIRECT_URI = "skoapp-prod://sign-in-callback"

API_BASE_URL = "https://api.skolengo.com/api/v1/bff-sko-app"

# --- Config entry keys ---
CONF_SCHOOL_ID = "school_id"
CONF_SCHOOL_NAME = "school_name"
CONF_SCHOOL_EMS_CODE = "school_ems_code"
CONF_SCHOOL_OIDC_WELLKNOWN = "school_oidc_wellknown"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_STUDENT_ID = "student_id"
CONF_STUDENT_NAME = "student_name"
CONF_USER_ID = "user_id"

# --- Options ---
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30  # minutes
MIN_SCAN_INTERVAL = 5

# How long before the first lesson of the next school day the
# "next_alarm" sensor should fire (e.g. time needed to get ready).
CONF_ALARM_OFFSET = "alarm_offset"
DEFAULT_ALARM_OFFSET = 60  # minutes
MIN_ALARM_OFFSET = 0

# How far ahead the timetable calendar (and, mirroring it, the homework
# due-date window) looks. By default (option unset) both are fetched all
# the way from the start to the end of the current school year (see
# `_start_of_school_year()`/`_end_of_school_year()` in coordinator.py) --
# so nothing since the school year began is missing, and booking against
# upcoming free slots isn't limited by a short rolling window either.
# Setting the option pins the *future* end instead to a fixed number of
# days from today, which trades that full-year visibility for fewer
# /agendas requests per poll (see `_get_agenda_paginated`'s 15-day
# chunking).
CONF_AGENDA_DAYS_FUTURE = "agenda_days_future"
MIN_AGENDA_DAYS_FUTURE = 1
MAX_AGENDA_DAYS_FUTURE = 366

# The school year is considered to run from September 1st through August
# 31st. Lessons/homework aren't actually published outside the real term
# dates, so requesting the full nominal range rather than the tighter real
# one just means a few extra empty-result request chunks at each end, not
# wrong data.
SCHOOL_YEAR_START_MONTH = 9
SCHOOL_YEAR_START_DAY = 1
SCHOOL_YEAR_END_MONTH = 8
SCHOOL_YEAR_END_DAY = 31

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)

# When the /homework-assignments endpoint 500s (Skolengo server bug) and we
# fall back to pulling homework embedded in the agenda, assignments are
# nested under the day they were *given*, not their due date. Look back this
# many days further from the homework window's own start when querying the
# agenda, so assignments given a while before it but due within the window
# are still found.
HOMEWORK_AGENDA_LOOKBACK_DAYS = 60

PLATFORMS = ["calendar", "sensor"]

MANUFACTURER = "Skolengo (unofficial)"

# --- Events ---
# Fired on the HA event bus so automations can react to changes, mirroring
# hass-pronote's `pronote_event`. `event_data["type"]` distinguishes the
# kind of change.
EVENT_SKOLENGO = "skolengo_event"
EVENT_TYPE_NEW_GRADE = "new_grade"
EVENT_TYPE_NEW_HOMEWORK = "new_homework"
EVENT_TYPE_LESSON_CANCELED = "lesson_canceled"
EVENT_TYPE_LESSON_MODIFIED = "lesson_modified"
EVENT_TYPE_LESSON_ADDED = "lesson_added"
