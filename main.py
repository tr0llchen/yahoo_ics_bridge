"""
Yahoo Calendar Bridge - FastAPI Application
Serves ICS endpoint for a single client with read-write support.
"""

import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional

from config import settings
from caldav_client import CalDAVClient
from ics_generator import generate_ics, generate_event_ics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Yahoo Calendar Bridge",
    description="Bridge between Yahoo Calendar and ICS endpoint",
    version="1.0.0",
)

# Initialize CalDAV client
caldav_client = CalDAVClient(
    username=settings.YAHOO_USERNAME,
    password=settings.YAHOO_PASSWORD,
    app_password=settings.YAHOO_APP_PASSWORD,
    oauth_token=settings.OAUTH_TOKEN,
    oauth_refresh_token=settings.OAUTH_REFRESH_TOKEN,
)


@app.get("/calendar.ics")
async def get_calendar_ics():
    """
    Get all future events as ICS format.
    On-demand: fetches directly from Yahoo CalDAV.
    """
    try:
        events = await caldav_client.get_future_events()
        ics_content = generate_ics(events)
        return Response(
            content=ics_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": "attachment; filename=calendar.ics",
            },
        )
    except Exception as e:
        logger.error(f"Error generating ICS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar.ics/{calendar_id}")
async def get_calendar_ics_by_id(calendar_id: str):
    """
    Get events from a specific calendar.
    """
    try:
        events = await caldav_client.get_future_events(calendar_id=calendar_id)
        ics_content = generate_ics(events)
        return Response(
            content=ics_content,
            media_type="text/calendar",
            headers={
                "Content-Disposition": f"attachment; filename={calendar_id}.ics",
            },
        )
    except Exception as e:
        logger.error(f"Error generating ICS for calendar {calendar_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/events")
async def get_events_json():
    """
    Get all future events as JSON (for debugging/inspection).
    """
    try:
        events = await caldav_client.get_future_events()
        return {"events": [event.dict() for event in events]}
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/events")
async def create_event(event: BaseModel):
    """
    Create a new event in Yahoo Calendar.
    """
    try:
        new_event = await caldav_client.create_event(
            summary=event.summary,
            description=event.description,
            start=event.start,
            end=event.end,
            calendar_id=event.calendar_id,
        )
        return {"event": new_event, "status": "created"}
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/events/{event_id}")
async def delete_event(event_id: str):
    """
    Delete an event from Yahoo Calendar.
    """
    try:
        await caldav_client.delete_event(event_id)
        return {"status": "deleted", "event_id": event_id}
    except Exception as e:
        logger.error(f"Error deleting event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "healthy", "service": "Yahoo Calendar Bridge"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
