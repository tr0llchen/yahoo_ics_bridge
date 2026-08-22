# Yahoo Calendar Bridge

A bridge between Yahoo Calendar and an ICS endpoint. Yahoo's native ICS export is currently down — this bridge provides a reliable alternative via Yahoo's CalDAV API.

## Features

- **ICS Endpoint**: `/calendar.ics` — serves all future events in iCalendar format
- **Read-Write**: Create and delete events via REST API
- **On-Demand**: Fetches directly from Yahoo CalDAV (no local caching)
- **Single Client**: Optimized for one subscribing application
- **Future Events Only**: Filters out historic events
- **Long-Lived Auth**: OAuth refresh tokens are indefinite

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Your App    │────▶│ Yahoo Calendar   │────▶│ Yahoo CalDAV │
│  (ICS)       │     │ Bridge (FastAPI) │     │  Endpoint    │
└──────────────┘     └──────────────────┘     └──────────────┘
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/calendar.ics` | Get all future events as ICS |
| GET | `/calendar.ics/{calendar_id}` | Get events from specific calendar |
| GET | `/events` | Get events as JSON |
| POST | `/events` | Create a new event |
| DELETE | `/events/{event_id}` | Delete an event |
| GET | `/health` | Health check |

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Yahoo credentials
```

### 2. Run with Docker

```bash
docker-compose up -d
```

### 3. Access the ICS Endpoint

```
http://localhost:8000/calendar.ics
```

### 4. Subscribe Your App

Point your application to:
```
http://<your-server-ip>:8000/calendar.ics
```

## Authentication

Yahoo CalDAV supports three authentication methods:

| Method | Description |
|--------|-------------|
| **App Password** (default) | Dedicated password for CalDAV |
| **OAuth** | OAuth 2.0 with indefinite refresh token |
| **Username/Password** | Regular Yahoo credentials |

### OAuth Token Lifespan

- **Access Token**: ~1 hour (auto-refreshed)
- **Refresh Token**: **Indefinite** (never expires unless revoked)

You authenticate once, and the bridge handles all token refreshes automatically.

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python main.py

# Or with uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Project Structure

```
yahoo_calbridge/
├── main.py              # FastAPI application
├── config.py            # Configuration management
├── caldav_client.py     # CalDAV client for Yahoo
├── ics_generator.py     # ICS format generator
├── requirements.txt     # Python dependencies
├── Dockerfile           # Docker build file
├── docker-compose.yml   # Docker Compose config
├── .env.example         # Environment variables template
└── README.md            # This file
```
