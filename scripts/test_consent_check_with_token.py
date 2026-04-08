from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def _extract_token_from_callback_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(parsed.query)
    fragment_params = urllib.parse.parse_qs(parsed.fragment)

    for params in (query_params, fragment_params):
        for key in ("access_token", "id_token"):
            values = params.get(key, [])
            if values:
                return values[0]
    raise ValueError("No access_token or id_token found in callback URL.")


def _read_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token

    if args.token_file:
        with open(args.token_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()

    if args.callback_url:
        return _extract_token_from_callback_url(args.callback_url)

    token = os.getenv(args.token_env, "").strip()
    if token:
        return token

    raise ValueError(
        "No token provided. Use one of: --token, --token-file, --callback-url, or set the env var named by --token-env."
    )


def _call_consent_endpoint(base_url: str, access_token: str) -> dict:
    url = f"{base_url.rstrip('/')}/onboarding/consent/check"
    payload = json.dumps({"access_token": access_token}).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Consent endpoint returned HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach consent endpoint: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Call the local consent-check endpoint with a tenant token from onboarding flows. "
            "Token sources: raw token, file, env var, or callback URL."
        )
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8090", help="Consent-check server base URL")
    parser.add_argument("--token", help="Raw JWT token string")
    parser.add_argument("--token-file", help="Path to a file that contains a raw JWT token")
    parser.add_argument(
        "--callback-url",
        help=(
            "Full redirect/callback URL captured from onboarding sign-in; token is extracted from query or fragment."
        ),
    )
    parser.add_argument(
        "--token-env",
        default="CUSTOMER_ACCESS_TOKEN",
        help="Environment variable name containing the token when other options are not used",
    )
    args = parser.parse_args()

    try:
        token = _read_token(args)
        if token.lower().startswith("bearer "):
            token = token[7:].strip()

        result = _call_consent_endpoint(args.base_url, token)
        print(json.dumps(result, indent=2))
        if not result.get("is_ready_for_either", False):
            sys.exit(1)
    except Exception as exc:  # pragma: no cover
        print(str(exc), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
