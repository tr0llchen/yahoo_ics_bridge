"""
Configuration management for Yahoo Calendar Bridge.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Yahoo Credentials
    YAHOO_USERNAME: str = os.getenv("YAHOO_USERNAME", "")
    YAHOO_PASSWORD: str = os.getenv("YAHOO_PASSWORD", "")
    YAHOO_APP_PASSWORD: str = os.getenv("YAHOO_APP_PASSWORD", "")

    # OAuth Tokens (long-lived)
    OAUTH_TOKEN: str = os.getenv("OAUTH_TOKEN", "")
    OAUTH_REFRESH_TOKEN: str = os.getenv("OAUTH_REFRESH_TOKEN", "")

    # CalDAV Endpoint
    CALDAV_URL: str = os.getenv("CALDAV_URL", "https://caldav.calendar.yahoo.com/")

    # Server Settings
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))

    # ICS Settings
    DEFAULT_CALENDAR_ID: str = os.getenv("DEFAULT_CALENDAR_ID", "default")

    # Authentication method
    AUTH_METHOD: str = os.getenv("AUTH_METHOD", "app_password")  # app_password, oauth, username_password


settings = Settings()
