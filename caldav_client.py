"""
CalDAV Client for Yahoo Calendar.
Handles authentication and communication with Yahoo CalDAV endpoint.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from dataclasses import dataclass
from caldav.objects import Calendar, Event
from caldav import DAVClient

from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    event_id: str
    summary: str
    description: str
    start: str  # ISO 8601 format
    end: str    # ISO 8601 format
    calendar_id: str
    location: Optional[str] = None
    status: Optional[str] = None


class CalDAVClient:
    """Client for interacting with Yahoo CalDAV."""

    def __init__(
        self,
        username: str = "",
        password: str = "",
        app_password: str = "",
        oauth_token: str = "",
        oauth_refresh_token: str = "",
    ):
        self.username = username
        self.password = password
        self.app_password = app_password
        self.oauth_token = oauth_token
        self.oauth_refresh_token = oauth_refresh_token
        self.client = None
        self.calendars = {}

    def _authenticate(self) -> "CalDAVClient":
        """Authenticate with Yahoo CalDAV."""
        if settings.AUTH_METHOD == "oauth" and self.oauth_token:
            # OAuth authentication
            self.client = DAVClient(
                url=settings.CALDAV_URL,
                username=self.username,
                password=self.oauth_token,
            )
        elif settings.AUTH_METHOD == "app_password" and self.app_password:
            # App password authentication
            self.client = DAVClient(
                url=settings.CALDAV_URL,
                username=self.username,
                password=self.app_password,
            )
        else:
            # Username/password authentication
            self.client = DAVClient(
                url=settings.CALDAV_URL,
                username=self.username,
                password=self.password,
            )

        logger.info(f"Authenticated with CalDAV using {settings.AUTH_METHOD}")
        return self

    def _get_calendars(self) -> dict:
        """Fetch all calendars."""
        if not self.client:
            self._authenticate()

        calendars = self.client.principal().calendars()
        for calendar in calendars:
            self.calendars[calendar.name] = calendar
            logger.info(f"Found calendar: {calendar.name}")

        return self.calendars

    def _get_calendar(self, calendar_id: str = None) -> Calendar:
        """Get a specific calendar or the default one."""
        if not self.calendars:
            self._get_calendars()

        if calendar_id and calendar_id in self.calendars:
            return self.calendars[calendar_id]

        # Return first calendar as default
        if self.calendars:
            return list(self.calendars.values())[0]

        # Fallback: get default calendar
        if not self.client:
            self._authenticate()
        return self.client.default_calendar()

    async def get_future_events(self, calendar_id: str = None) -> List[CalendarEvent]:
        """
        Fetch all future events from Yahoo Calendar.
        On-demand: fetches directly from CalDAV.
        """
        if not self.client:
            self._authenticate()

        calendar = self._get_calendar(calendar_id)

        # Get all events (Yahoo CalDAV returns all by default)
        events = calendar.events()

        # Filter for future events
        future_events = []
        now = datetime.now(timezone.utc)

        for event in events:
            try:
                # Parse event data
                vobject_event = event.vobject_event
                if not vobject_event:
                    continue

                # Get start and end times
                start = vobject_event.vevent.dtstart.value
                end = vobject_event.vevent.dtend.value

                # Convert to UTC if needed
                if hasattr(start, 'tzinfo') and start.tzinfo is not None:
                    start = start.astimezone(timezone.utc)
                else:
                    start = datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc)

                if hasattr(end, 'tzinfo') and end.tzinfo is not None:
                    end = end.astimezone(timezone.utc)
                else:
                    end = datetime.combine(end, datetime.min.time()).replace(tzinfo=timezone.utc)

                # Filter future events
                if start > now:
                    # Extract event properties
                    summary = str(vobject_event.vevent.summary.value) if hasattr(vobject_event.vevent, 'summary') else ""
                    description = str(vobject_event.vevent.description.value) if hasattr(vobject_event.vevent, 'description') else ""
                    location = str(vobject_event.vevent.location.value) if hasattr(vobject_event.vevent, 'location') else None
                    status = str(vobject_event.vevent.status.value) if hasattr(vobject_event.vevent, 'status') else None

                    future_events.append(CalendarEvent(
                        event_id=event.id,
                        summary=summary,
                        description=description,
                        start=start.isoformat(),
                        end=end.isoformat(),
                        calendar_id=calendar.name,
                        location=location,
                        status=status,
                    ))
            except Exception as e:
                logger.warning(f"Error parsing event {event.id}: {e}")
                continue

        logger.info(f"Found {len(future_events)} future events")
        return future_events

    async def create_event(
        self,
        summary: str,
        description: str = "",
        start: str = "",
        end: str = "",
        calendar_id: str = None,
    ) -> dict:
        """
        Create a new event in Yahoo Calendar.
        """
        if not self.client:
            self._authenticate()

        calendar = self._get_calendar(calendar_id)

        # Parse start and end if provided as strings
        if start:
            start_dt = datetime.fromisoformat(start)
        else:
            start_dt = datetime.now(timezone.utc)

        if end:
            end_dt = datetime.fromisoformat(end)
        else:
            end_dt = start_dt.replace(hour=start_dt.hour + 1)  # Default 1 hour duration

        # Create event
        event = calendar.add_event(
            f"BEGIN:VCALENDAR\r\n"
            f"VERSION:2.0\r\n"
            f"PRODID:-//Yahoo Calendar Bridge//EN\r\n"
            f"BEGIN:VEVENT\r\n"
            f"DTSTART:{start_dt.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"DTEND:{end_dt.strftime('%Y%m%dT%H%M%SZ')}\r\n"
            f"SUMMARY:{summary}\r\n"
            f"DESCRIPTION:{description}\r\n"
            f"END:VEVENT\r\n"
            f"END:VCALENDAR",
        )

        return {
            "event_id": event.id,
            "summary": summary,
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
        }

    async def delete_event(self, event_id: str) -> bool:
        """
        Delete an event from Yahoo Calendar.
        """
        if not self.client:
            self._authenticate()

        # Get the event
        event = self.client.event(id=event_id)

        # Delete
        event.delete()
        logger.info(f"Deleted event: {event_id}")
        return True

    async def refresh_oauth_token(self) -> bool:
        """
        Refresh OAuth token if using OAuth authentication.
        """
        if settings.AUTH_METHOD != "oauth" or not self.oauth_refresh_token:
            return True

        try:
            # Yahoo OAuth token refresh
            import requests

            response = requests.post(
                "https://api.login.yahoo.com/oauth2/get_token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.oauth_refresh_token,
                    "client_id": "dleyar3EnXPpT6I75j7h8Q",  # Yahoo's default client ID
                    "client_secret": "",
                },
            )

            if response.status_code == 200:
                data = response.json()
                self.oauth_token = data.get("access_token", "")
                logger.info("OAuth token refreshed successfully")
                return True
            else:
                logger.error(f"OAuth token refresh failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error refreshing OAuth token: {e}")
            return False
