from __future__ import annotations

import base64
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


REQUIRED_DELEGATED_SCOPES = {
    "User.Read.All",
    "Files.Read.All",
    "Mail.Read",
    "Calendars.Read",
    "ChannelMessage.Read.All",
}

REQUIRED_APP_ROLES = {
    "User.Read.All",
    "Files.Read.All",
    "Mail.Read",
    "Calendars.Read",
    "ChannelMessage.Read.All",
}


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Token is not a JWT.")

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    payload_bytes = base64.urlsafe_b64decode(payload_segment + padding)
    payload = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JWT payload is not an object.")
    return payload


def _evaluate_consent(claims: dict[str, Any]) -> dict[str, Any]:
    delegated_scopes = set(str(claims.get("scp", "")).split())
    app_roles_raw = claims.get("roles", [])
    app_roles = set(app_roles_raw if isinstance(app_roles_raw, list) else [])

    missing_delegated = sorted(REQUIRED_DELEGATED_SCOPES - delegated_scopes)
    missing_app_roles = sorted(REQUIRED_APP_ROLES - app_roles)

    has_delegated = len(missing_delegated) == 0
    has_app = len(missing_app_roles) == 0

    return {
        "tenant_id": claims.get("tid"),
        "app_id": claims.get("appid"),
        "principal": claims.get("upn") or claims.get("unique_name") or claims.get("oid"),
        "token_type_hint": "delegated" if "scp" in claims else "application" if "roles" in claims else "unknown",
        "granted_delegated_scopes": sorted(delegated_scopes),
        "granted_app_roles": sorted(app_roles),
        "missing_delegated_scopes": missing_delegated,
        "missing_app_roles": missing_app_roles,
        "is_ready_for_delegated_flow": has_delegated,
        "is_ready_for_app_flow": has_app,
        "is_ready_for_either": has_delegated or has_app,
    }


class ConsentCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return

        self._write_json(
            HTTPStatus.NOT_FOUND,
            {
                "error": "Not found",
                "hint": "Use POST /onboarding/consent/check with JSON body {\"access_token\":\"<jwt>\"}.",
            },
        )

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/onboarding/consent/check":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8"))
            access_token = payload.get("access_token", "")
            if not access_token:
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Missing access_token in request body."})
                return

            claims = _decode_jwt_payload(access_token)
            result = _evaluate_consent(claims)
            self._write_json(HTTPStatus.OK, result)
        except json.JSONDecodeError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Request body must be valid JSON."})
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    host = os.getenv("CONSENT_CHECK_HOST", "127.0.0.1")
    port = int(os.getenv("CONSENT_CHECK_PORT", "8090"))
    server = ThreadingHTTPServer((host, port), ConsentCheckHandler)
    print(f"Consent check server running at http://{host}:{port}")
    print("Health endpoint: GET /health")
    print("Consent endpoint: POST /onboarding/consent/check")
    server.serve_forever()


if __name__ == "__main__":
    main()
