"""
ICS Generator for Yahoo Calendar Bridge.
Converts calendar events to ICS (iCalendar) format.
"""

from datetime import datetime
from typing import List
from config import settings
from caldav_client import CalendarEvent


def generate_ics(events: List[CalendarEvent]) -> str:
    """
    Generate ICS content from a list of calendar events.
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Yahoo Calendar Bridge//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for event in events:
        lines.append(generate_event_ics(event))

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def generate_event_ics(event: CalendarEvent) -> str:
    """
    Generate a single VEVENT block in ICS format.
    """
    # Qualify the UID with the source calendar so events from different
    # calendars can never collide when merged into one VCALENDAR (RFC5545
    # requires UID to be unique within a single ICS file).
    uid = f"{event.calendar_id}-{event.event_id}" if event.calendar_id else event.event_id

    lines = [
        "BEGIN:VEVENT",
        f"UID:{_escape_text(uid)}",
        f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{_format_datetime(event.start)}",
        f"DTEND:{_format_datetime(event.end)}",
        f"SUMMARY:{_escape_text(event.summary)}",
    ]

    if event.calendar_id:
        lines.append(f"CATEGORIES:{_escape_text(event.calendar_id)}")

    if event.description:
        lines.append(f"DESCRIPTION:{_escape_text(event.description)}")

    if event.location:
        lines.append(f"LOCATION:{_escape_text(event.location)}")

    if event.status:
        lines.append(f"STATUS:{event.status}")

    lines.append("END:VEVENT")
    return "\r\n".join(lines)


def _format_datetime(dt_str: str) -> str:
    """
    Format datetime string to ICS format (YYYYMMDDTHHMMSSZ).
    """
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        # Fallback: return as-is if already in correct format
        return dt_str


def _escape_text(text: str) -> str:
    """
    Escape special characters for ICS format.
    """
    return text.replace(",", "\\,").replace(";", "\\;").replace("\\", "\\\\")
