"""
CalDAV Client for Yahoo Calendar.
Handles authentication and communication with Yahoo CalDAV endpoint.
"""

import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List
from dataclasses import dataclass
from caldav.objects import Calendar, Event
from caldav import DAVClient
from requests.auth import HTTPBasicAuth

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


def _to_utc_datetime(value) -> datetime:
    """Normalize a vobject DTSTART/DTEND/RECURRENCE-ID value (date or datetime) to aware UTC."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc)
        return value.replace(tzinfo=timezone.utc)
    # date-only value (all-day event)
    return datetime.combine(value, datetime.min.time()).replace(tzinfo=timezone.utc)


def _vevent_fields(vevent) -> dict:
    return {
        "summary": str(vevent.summary.value) if hasattr(vevent, "summary") else "",
        "description": str(vevent.description.value) if hasattr(vevent, "description") else "",
        "location": str(vevent.location.value) if hasattr(vevent, "location") else None,
        "status": str(vevent.status.value) if hasattr(vevent, "status") else None,
    }


def _expand_calendar_object(
    vobject_instance,
    event_id: str,
    calendar_name: str,
    window_start: datetime,
    window_end: datetime,
) -> List[CalendarEvent]:
    """
    Expand one fetched calendar resource into individual CalendarEvent
    occurrences within [window_start, window_end]. A resource may hold a
    single plain VEVENT, or a recurring master (RRULE) plus zero or more
    overridden-occurrence VEVENTs (RECURRENCE-ID) sharing the same UID.
    """
    vevents = list(getattr(vobject_instance, "vevent_list", []))
    if not vevents and hasattr(vobject_instance, "vevent"):
        vevents = [vobject_instance.vevent]

    masters = [v for v in vevents if hasattr(v, "rrule") and not hasattr(v, "recurrence_id")]
    overrides = [v for v in vevents if hasattr(v, "recurrence_id")]
    singles = [v for v in vevents if not hasattr(v, "rrule") and not hasattr(v, "recurrence_id")]

    results: List[CalendarEvent] = []
    override_recurrence_ids = set()

    for vevent in overrides:
        recurrence_dt = _to_utc_datetime(vevent.recurrence_id.value)
        override_recurrence_ids.add(recurrence_dt)

        start = _to_utc_datetime(vevent.dtstart.value)
        end = _to_utc_datetime(vevent.dtend.value)
        if end < window_start or start > window_end:
            continue
        results.append(CalendarEvent(
            event_id=f"{event_id}-{recurrence_dt.isoformat()}",
            calendar_id=calendar_name,
            start=start.isoformat(),
            end=end.isoformat(),
            **_vevent_fields(vevent),
        ))

    for vevent in masters:
        master_start = _to_utc_datetime(vevent.dtstart.value)
        master_end = _to_utc_datetime(vevent.dtend.value)
        duration = master_end - master_start
        fields = _vevent_fields(vevent)
        is_all_day = not isinstance(vevent.dtstart.value, datetime)

        try:
            ruleset = vevent.getrruleset(addRDate=True)
            if is_all_day:
                raw_occurrences = ruleset.between(
                    window_start.replace(tzinfo=None), window_end.replace(tzinfo=None), inc=True
                )
            else:
                raw_occurrences = ruleset.between(window_start, window_end, inc=True)
        except Exception as e:
            logger.warning(f"Could not expand recurrence for event {event_id}: {e}")
            continue

        for occurrence in raw_occurrences:
            occ_start = _to_utc_datetime(occurrence)
            if occ_start in override_recurrence_ids:
                continue  # replaced by an override VEVENT, already emitted above
            occ_end = occ_start + duration
            results.append(CalendarEvent(
                event_id=f"{event_id}-{occ_start.isoformat()}",
                calendar_id=calendar_name,
                start=occ_start.isoformat(),
                end=occ_end.isoformat(),
                **fields,
            ))

    for vevent in singles:
        start = _to_utc_datetime(vevent.dtstart.value)
        end = _to_utc_datetime(vevent.dtend.value)
        if end < window_start or start > window_end:
            continue
        results.append(CalendarEvent(
            event_id=event_id,
            calendar_id=calendar_name,
            start=start.isoformat(),
            end=end.isoformat(),
            **_vevent_fields(vevent),
        ))

    return results


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
        # Yahoo's CalDAV endpoint returns 401 on an unauthenticated request
        # WITHOUT a WWW-Authenticate header. The caldav library only sets up
        # Basic Auth in response to that header, so it never actually sends
        # credentials and fails with AuthorizationError even when the
        # credentials are correct. Passing `auth=` explicitly forces Basic
        # Auth to be sent on the first request, bypassing that negotiation.
        if settings.AUTH_METHOD == "oauth" and self.oauth_token:
            # OAuth authentication
            used_method = "oauth"
            password = self.oauth_token
        elif settings.AUTH_METHOD == "app_password" and self.app_password:
            # App password authentication
            used_method = "app_password"
            password = self.app_password
        else:
            # Username/password authentication
            used_method = "username_password"
            password = self.password

        self.client = DAVClient(
            url=settings.CALDAV_URL,
            username=self.username,
            password=password,
            auth=HTTPBasicAuth(self.username, password),
        )

        logger.info(f"Authenticated with CalDAV using {used_method}")
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

    def _get_calendar_events(
        self, calendar: Calendar, window_start: datetime, window_end: datetime
    ) -> List[CalendarEvent]:
        """Fetch and expand events from a single calendar within the given window."""
        # Ask the server to expand recurring events server-side where
        # supported (RFC4791 CALDAV:expand). Bounded start/end are required
        # for expand - an open-ended recurrence can't be expanded.
        events = calendar.search(
            event=True,
            start=window_start,
            end=window_end,
            expand=True,
        )

        calendar_events: List[CalendarEvent] = []

        for event in events:
            try:
                vobject_instance = event.vobject_instance
                if not vobject_instance:
                    continue

                calendar_events.extend(
                    _expand_calendar_object(
                        vobject_instance, event.id, calendar.name, window_start, window_end
                    )
                )
            except Exception as e:
                logger.warning(f"Error parsing event {event.id} in calendar {calendar.name}: {e}")
                continue

        return calendar_events

    async def get_events(
        self,
        calendar_id: str = None,
        since_days: int = 30,
        until_days: int = 730,
    ) -> List[CalendarEvent]:
        """
        Fetch events from Yahoo Calendar within a window: `since_days` in
        the past through `until_days` in the future. Includes events
        already in progress, and expands recurring events (RRULE) into
        their individual occurrences within the window.

        If `calendar_id` is given, only that calendar is queried. Otherwise
        ALL calendars in the account are fetched and merged; each event's
        `calendar_id` field records which calendar it came from so callers
        (e.g. the ICS generator) can keep them distinguishable.

        On-demand: fetches directly from CalDAV.
        """
        if not self.client:
            self._authenticate()

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=since_days)
        window_end = now + timedelta(days=until_days)

        if calendar_id:
            calendars = [self._get_calendar(calendar_id)]
        else:
            calendars = list(self._get_calendars().values())

        all_events: List[CalendarEvent] = []

        for calendar in calendars:
            try:
                calendar_events = self._get_calendar_events(calendar, window_start, window_end)
            except Exception as e:
                logger.warning(f"Error fetching events from calendar {calendar.name}: {e}")
                continue

            logger.info(f"Calendar '{calendar.name}': {len(calendar_events)} event(s)")
            all_events.extend(calendar_events)

        logger.info(
            f"Found {len(all_events)} events across {len(calendars)} calendar(s) "
            f"(past {since_days}d, next {until_days}d, recurring occurrences expanded)"
        )
        return all_events

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
