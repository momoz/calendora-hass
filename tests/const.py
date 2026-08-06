"""Shared test constants.

`example.invalid` is reserved by RFC 2606 and can never resolve — no test here
can accidentally reach a real host, and no real household data appears in this
repository.
"""

from __future__ import annotations

FEED_TOKEN = "tok-3f9a2c-not-a-real-token"
FEED_URL = f"https://example.invalid/api/feeds/{FEED_TOKEN}"
OTHER_FEED_TOKEN = "tok-rotated-also-not-real"
OTHER_FEED_URL = f"https://example.invalid/api/feeds/{OTHER_FEED_TOKEN}"

ICS_HEADERS = {"Content-Type": "text/calendar; charset=utf-8"}

ICS = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "PRODID:-//Calendora//Test//EN\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:test-event-1\r\n"
    "DTSTART;VALUE=DATE:20260810\r\n"
    "DTEND;VALUE=DATE:20260811\r\n"
    "SUMMARY:Placeholder\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)
