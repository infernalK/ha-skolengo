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

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)

# Window (in days) used to fetch the timetable / homework / agenda around
# "today", mirroring hass-pronote's approach.
AGENDA_DAYS_PAST = 2
AGENDA_DAYS_FUTURE = 15
HOMEWORK_DAYS_FUTURE = 60

PLATFORMS = ["calendar", "sensor"]

MANUFACTURER = "Skolengo (unofficial)"

# --- Events ---
# Fired on the HA event bus so automations can react to changes, mirroring
# hass-pronote's `pronote_event`. `event_data["type"]` distinguishes the
# kind of change.
EVENT_SKOLENGO = "skolengo_event"
EVENT_TYPE_NEW_GRADE = "new_grade"
EVENT_TYPE_NEW_HOMEWORK = "new_homework"
