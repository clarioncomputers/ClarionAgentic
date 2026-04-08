from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request


def get_graph_token() -> str:
    command = [
        "az",
        "account",
        "get-access-token",
        "--resource-type",
        "ms-graph",
        "--query",
        "accessToken",
        "-o",
        "tsv",
    ]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to get Graph token: {proc.stderr.strip() or proc.stdout.strip()}")

    token = proc.stdout.strip()
    if not token:
        raise RuntimeError("Graph token command returned an empty token.")
    return token


def call_consent_endpoint(base_url: str, access_token: str) -> dict:
    payload = json.dumps({"access_token": access_token}).encode("utf-8")
    url = f"{base_url.rstrip('/')}/onboarding/consent/check"

    request = urllib.request.Request(
        url=url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Consent endpoint returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach consent endpoint: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire a Graph token and call the local consent-check endpoint.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8090", help="Consent-check server base URL")
    args = parser.parse_args()

    token = get_graph_token()
    result = call_consent_endpoint(args.base_url, token)

    print(json.dumps(result, indent=2))
    if not result.get("is_ready_for_either", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
