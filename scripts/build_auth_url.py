from __future__ import annotations

import argparse
import os
import urllib.parse
import webbrowser

from dotenv import load_dotenv


DEFAULT_SCOPES = [
    "openid",
    "profile",
    "offline_access",
    "User.Read.All",
    "Files.Read.All",
    "Mail.Read",
    "Calendars.Read",
    "ChannelMessage.Read.All",
]


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _normalize_scopes(raw_scopes: str | None) -> list[str]:
    if raw_scopes and raw_scopes.strip():
        return [scope.strip() for scope in raw_scopes.split() if scope.strip()]
    return DEFAULT_SCOPES


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build Microsoft identity authorize URL for tenant onboarding consent. "
            "Reads defaults from .env and can open browser."
        )
    )
    parser.add_argument("--open", action="store_true", help="Open the generated URL in your default browser")
    parser.add_argument("--state", default="clarion-consent-check", help="OAuth state value")
    parser.add_argument("--scopes", help="Space-separated scopes override")
    args = parser.parse_args()

    load_dotenv(override=False)

    tenant = _required("PARTNER_AUTH_TENANT")
    client_id = _required("PARTNER_AUTH_CLIENT_ID")
    redirect_uri = _required("PARTNER_AUTH_REDIRECT_URI")
    response_type = os.getenv("PARTNER_AUTH_RESPONSE_TYPE", "token").strip() or "token"
    scopes = _normalize_scopes(args.scopes or os.getenv("PARTNER_AUTH_SCOPES"))

    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    query = {
        "client_id": client_id,
        "response_type": response_type,
        "redirect_uri": redirect_uri,
        "response_mode": "fragment",
        "scope": " ".join(scopes),
        "state": args.state,
    }

    auth_url = f"{base}?{urllib.parse.urlencode(query)}"
    print(auth_url)

    if args.open:
        webbrowser.open(auth_url)


if __name__ == "__main__":
    main()
