from __future__ import annotations

import argparse
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class CallbackState:
    def __init__(self) -> None:
        self.token: str | None = None
        self.error: str | None = None
        self.event = threading.Event()


def _extract_token(payload: dict[str, Any]) -> str:
    for key in ("access_token", "id_token"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("Callback did not include access_token or id_token.")


def _call_consent_endpoint(base_url: str, token: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/onboarding/consent/check"
    body = json.dumps({"access_token": token}).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Consent endpoint returned HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach consent endpoint: {exc}") from exc


def _success_page() -> bytes:
    html = """
<!doctype html>
<html>
  <head><meta charset=\"utf-8\"><title>Consent Callback</title></head>
  <body style=\"font-family:Segoe UI,Arial,sans-serif;padding:2rem\">
    <h2>Processing token...</h2>
    <p>You can close this window after status changes.</p>
    <script>
      const hash = window.location.hash ? window.location.hash.substring(1) : "";
      const query = window.location.search ? window.location.search.substring(1) : "";
      const tokenSource = hash || query;
      const params = new URLSearchParams(tokenSource);
      const payload = {
        access_token: params.get("access_token"),
        id_token: params.get("id_token"),
        error: params.get("error"),
        error_description: params.get("error_description")
      };

      fetch("/callback-token", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      }).then(r => r.text()).then(() => {
        document.body.innerHTML = "<h2>Token captured</h2><p>Return to terminal for results.</p>";
      }).catch(() => {
        document.body.innerHTML = "<h2>Capture failed</h2><p>Check terminal for details.</p>";
      });
    </script>
  </body>
</html>
"""
    return html.encode("utf-8")


class CallbackHandler(BaseHTTPRequestHandler):
    state: CallbackState

    def do_GET(self) -> None:
        if self.path.startswith("/callback"):
            page = _success_page()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/callback-token":
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            if payload.get("error"):
                self.state.error = f"{payload.get('error')}: {payload.get('error_description', '')}"
            else:
                token = _extract_token(payload)
                self.state.token = token[7:].strip() if token.lower().startswith("bearer ") else token
        except Exception as exc:  # pragma: no cover
            self.state.error = str(exc)

        self.state.event.set()
        self.send_response(HTTPStatus.OK)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture callback token locally and run consent check automatically.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for local callback listener")
    parser.add_argument("--port", type=int, default=8787, help="Port for local callback listener")
    parser.add_argument("--auth-url", help="Optional auth URL to open automatically in browser")
    parser.add_argument(
        "--consent-check-base",
        default="http://127.0.0.1:8090",
        help="Base URL for local consent-check server",
    )
    parser.add_argument("--timeout", type=int, default=300, help="Seconds to wait for callback token")
    args = parser.parse_args()

    state = CallbackState()
    CallbackHandler.state = state
    server = ThreadingHTTPServer((args.host, args.port), CallbackHandler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    callback_url = f"http://{args.host}:{args.port}/callback"
    print(f"Listening for callback at: {callback_url}")
    print("Set this as your redirect URI for local testing.")

    if args.auth_url:
        print("Opening provided auth URL in browser...")
        webbrowser.open(args.auth_url)

    got_token = state.event.wait(timeout=args.timeout)
    server.shutdown()
    server.server_close()

    if not got_token:
        raise SystemExit("Timed out waiting for callback token.")
    if state.error:
        raise SystemExit(f"Callback reported an error: {state.error}")
    if not state.token:
        raise SystemExit("No token captured from callback.")

    result = _call_consent_endpoint(args.consent_check_base, state.token)
    print(json.dumps(result, indent=2))
    if not result.get("is_ready_for_either", False):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
