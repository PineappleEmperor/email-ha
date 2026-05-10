"""Constants for the Email IMAP integration."""
from __future__ import annotations

DOMAIN = "email_imap"

PLATFORMS = ["sensor"]

CONF_EMAIL = "email"
CONF_FOLDER = "folder"
CONF_MAX_EMAILS = "max_emails"
CONF_SCAN_INTERVAL = "scan_interval"

GMAIL_IMAP_HOST = "imap.gmail.com"
GMAIL_IMAP_PORT = 993
GMAIL_SCOPES = "https://mail.google.com/"

DEFAULT_FOLDER = "INBOX"
DEFAULT_MAX_EMAILS = 10
DEFAULT_SCAN_INTERVAL = 300  # seconds

# Sensor attribute keys
ATTR_SUBJECT = "subject"
ATTR_SENDER = "sender"
ATTR_DATE = "date"
ATTR_PREVIEW = "preview"
ATTR_MESSAGE_ID = "message_id"
ATTR_UID = "uid"
ATTR_EMAILS = "emails"
ATTR_FOLDER = "folder"

# Service names
SERVICE_QUERY_EMAILS = "query_emails"
SERVICE_ATTR_FOLDER = "folder"
SERVICE_ATTR_SEARCH_CRITERIA = "search_criteria"
SERVICE_ATTR_MAX_RESULTS = "max_results"

EVENT_NEW_EMAIL = "email_imap_new_email"
