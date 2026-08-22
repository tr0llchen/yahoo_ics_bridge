"""
Diagnostic script for Yahoo CalDAV authentication issues.

Run this directly on the server where the bridge is deployed, using the
same environment/.env it runs with:

    python diagnose_auth.py

It does NOT print your raw password/app-password. It only prints lengths
and boundary characters so you can spot copy-paste issues (stray spaces,
quotes, newlines) without leaking the secret.
"""

import sys

from config import settings


def _inspect(name: str, value: str) -> None:
    if not value:
        print(f"  {name}: (empty)")
        return
    has_leading_ws = value != value.lstrip()
    has_trailing_ws = value != value.rstrip()
    has_inner_ws = " " in value.strip()
    has_quotes = value.startswith(('"', "'")) or value.endswith(('"', "'"))
    print(
        f"  {name}: length={len(value)} "
        f"leading_whitespace={has_leading_ws} trailing_whitespace={has_trailing_ws} "
        f"inner_whitespace={has_inner_ws} wrapped_in_quotes={has_quotes} "
        f"first_char={value[0]!r} last_char={value[-1]!r}"
    )
    if has_leading_ws or has_trailing_ws:
        print(f"    -> WARNING: {name} has leading/trailing whitespace. Likely copy-paste artifact.")
    if has_inner_ws and name != "YAHOO_USERNAME":
        print(f"    -> WARNING: {name} contains spaces. Yahoo displays app passwords grouped "
              f"with spaces for readability — make sure they were NOT pasted in.")
    if has_quotes:
        print(f"    -> WARNING: {name} appears to be wrapped in quote characters. "
              f"dotenv should strip a matching pair, but check for a stray unmatched quote.")


def check_config() -> None:
    print("=== Configuration sanity check ===")
    print(f"  AUTH_METHOD = {settings.AUTH_METHOD!r}")
    valid_methods = {"app_password", "oauth", "username_password"}
    if settings.AUTH_METHOD not in valid_methods:
        print(f"    -> WARNING: AUTH_METHOD is not one of {valid_methods}. "
              f"The code does an exact-string match; anything else silently falls back "
              f"to username_password with whatever YAHOO_PASSWORD is set (possibly empty).")
    print(f"  CALDAV_URL  = {settings.CALDAV_URL!r}")
    print()
    print("  Credential fields for the active AUTH_METHOD:")
    _inspect("YAHOO_USERNAME", settings.YAHOO_USERNAME)
    if settings.AUTH_METHOD == "app_password":
        _inspect("YAHOO_APP_PASSWORD", settings.YAHOO_APP_PASSWORD)
        if not settings.YAHOO_APP_PASSWORD:
            print("    -> WARNING: AUTH_METHOD=app_password but YAHOO_APP_PASSWORD is empty. "
                  "This will silently fall back to username_password auth (see caldav_client.py:60-73).")
    elif settings.AUTH_METHOD == "oauth":
        _inspect("OAUTH_TOKEN", settings.OAUTH_TOKEN)
    else:
        _inspect("YAHOO_PASSWORD", settings.YAHOO_PASSWORD)
    print()


def which_credential_will_actually_be_used() -> tuple[str, str]:
    """Mirror caldav_client.py's _authenticate branch logic exactly."""
    if settings.AUTH_METHOD == "oauth" and settings.OAUTH_TOKEN:
        return settings.YAHOO_USERNAME, settings.OAUTH_TOKEN
    elif settings.AUTH_METHOD == "app_password" and settings.YAHOO_APP_PASSWORD:
        return settings.YAHOO_USERNAME, settings.YAHOO_APP_PASSWORD
    else:
        return settings.YAHOO_USERNAME, settings.YAHOO_PASSWORD


def raw_propfind_test() -> None:
    import requests

    username, password = which_credential_will_actually_be_used()

    print("=== Raw PROPFIND test against Yahoo CalDAV ===")
    print(f"  Using username={username!r}, password length={len(password)}")
    if not username or not password:
        print("  -> Skipping: username or password resolved to empty. Fix config first.")
        return

    body = (
        '<?xml version="1.0" encoding="utf-8" ?>'
        '<D:propfind xmlns:D="DAV:">'
        '<D:prop><D:current-user-principal/></D:prop>'
        '</D:propfind>'
    )
    headers = {"Content-Type": "application/xml; charset=utf-8", "Depth": "0"}

    try:
        resp = requests.request(
            "PROPFIND",
            settings.CALDAV_URL,
            data=body,
            headers=headers,
            auth=(username, password),
            timeout=15,
            allow_redirects=False,
        )
    except requests.exceptions.RequestException as e:
        print(f"  -> Request failed before getting a response: {e!r}")
        return

    print(f"  Status: {resp.status_code} {resp.reason}")
    print(f"  WWW-Authenticate: {resp.headers.get('WWW-Authenticate', '(none)')}")
    if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
        print(f"  -> Server wants to redirect to: {resp.headers.get('Location')}")
        print("     If this redirect crosses to a different host, requests/caldav may "
              "silently drop the Authorization header on the follow-up request, which "
              "looks identical to a bad-credentials 401.")
    print(f"  Body (first 500 chars):\n{resp.text[:500]!r}")
    print()

    if resp.status_code == 401:
        print("  -> 401 Unauthorized confirmed at the raw HTTP level (not a caldav-library bug).")
        print("     This means Yahoo itself is rejecting username/password as sent.")
        print("     Double check: username is the FULL email address, and the app password ")
        print("     was copied WITHOUT the spaces Yahoo displays it with for readability.")
    elif resp.status_code in (200, 207):
        print("  -> Success! Credentials are valid at the HTTP level.")
        print("     If the FastAPI app still fails, the bug is in caldav_client.py's flow, ")
        print("     not the credentials themselves.")


def caldav_library_test() -> None:
    print("=== caldav library test (principal + calendars) ===")
    from caldav import DAVClient
    from requests.auth import HTTPBasicAuth

    username, password = which_credential_will_actually_be_used()
    if not username or not password:
        print("  -> Skipping: username or password resolved to empty.")
        return

    client = DAVClient(
        url=settings.CALDAV_URL,
        username=username,
        password=password,
        auth=HTTPBasicAuth(username, password),
    )
    try:
        principal = client.principal()
        print(f"  -> principal() succeeded: {principal}")
        calendars = principal.calendars()
        print(f"  -> Found {len(calendars)} calendar(s): {[c.name for c in calendars]}")
    except Exception as e:
        print(f"  -> caldav library raised: {type(e).__name__}: {e}")


if __name__ == "__main__":
    check_config()
    raw_propfind_test()
    print()
    caldav_library_test()
    sys.exit(0)
