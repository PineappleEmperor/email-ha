"""Constants for the Email IMAP integration."""
from __future__ import annotations

DOMAIN = "email_ha"

PLATFORMS = ["sensor"]

CONF_EMAIL = "email"
CONF_FOLDER = "folder"
CONF_SCAN_INTERVAL = "scan_interval"

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
GMAIL_SCOPES = "https://mail.google.com/"

DEFAULT_FOLDER = "INBOX"
DEFAULT_SCAN_INTERVAL = 300  # seconds
POLL_FETCH_COUNT = 3  # background poll fetches latest 3; sensor surfaces all 3
UNAVAILABLE_AFTER_SECONDS = 900  # go unavailable if no successful update for this long

# Sensor attribute keys
ATTR_SUBJECT = "subject"
ATTR_SENDER_NAME = "sender_name"
ATTR_SENDER_EMAIL = "sender_email"
ATTR_DATE = "date"
ATTR_UID = "uid"
ATTR_EMAILS = "emails"
ATTR_FOLDER = "folder"

# Service names
SERVICE_QUERY_EMAILS = "query_emails"
SERVICE_ATTR_FOLDER = "folder"
SERVICE_ATTR_SEARCH_CRITERIA = "search_criteria"
SERVICE_ATTR_MAX_RESULTS = "max_results"
SERVICE_ATTR_INCLUDE_FULL_BODY = "include_full_body"
SERVICE_ATTR_INCLUDE_ATTACHMENTS = "include_attachments"

EVENT_NEW_EMAIL = "email_ha_new_email"
