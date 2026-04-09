from __future__ import annotations

import argparse
import asyncio
import html
import json
import logging
import os
import ssl
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qs, urlsplit

import httpx

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

LOGGER = logging.getLogger(__name__)


HTML_PAGE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Clarion Agent Chat</title>
  <style>
    :root {
      --bg: #f8f6f1;
      --panel: #fffdf8;
      --ink: #1d1b16;
      --accent: #14532d;
      --accent-2: #84cc16;
      --line: #d6d0c4;
      --user: #ecfccb;
      --assistant: #e8f4ff;
      --error: #b91c1c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 20% 10%, #fff8e1, transparent 30%),
        radial-gradient(circle at 80% 20%, #dcfce7, transparent 25%),
        linear-gradient(140deg, #f6f3ea 0%, #f8fafc 45%, #eefbf0 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }
    .app {
      width: min(920px, 100%);
      height: min(88vh, 820px);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      overflow: hidden;
      display: grid;
      grid-template-rows: auto 1fr auto;
      box-shadow: 0 16px 40px rgba(20, 83, 45, 0.12);
    }
    header {
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(120deg, #14532d, #1f2937);
      color: #f9fafb;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
    }
    h1 {
      margin: 0;
      font-size: 1.05rem;
      letter-spacing: 0.02em;
      font-weight: 700;
    }
    .status {
      font-size: 0.85rem;
      opacity: 0.95;
    }
    #messages {
      padding: 1rem;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      scroll-behavior: smooth;
    }
    .msg {
      max-width: 85%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0.75rem 0.9rem;
      white-space: pre-wrap;
      line-height: 1.4;
      animation: pop-in 180ms ease-out;
    }
    .user {
      margin-left: auto;
      background: var(--user);
    }
    .assistant {
      margin-right: auto;
      background: var(--assistant);
    }
    .meta {
      font-size: 0.78rem;
      opacity: 0.75;
      margin-bottom: 0.2rem;
    }
    .msg-body {
      white-space: pre-wrap;
    }
    .error {
      color: var(--error);
      border-color: #fecaca;
      background: #fef2f2;
    }
    form {
      border-top: 1px solid var(--line);
      padding: 0.85rem;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 0.6rem;
      background: #fff;
    }
    textarea {
      resize: vertical;
      min-height: 52px;
      max-height: 180px;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 0.65rem 0.75rem;
      font: inherit;
      line-height: 1.35;
      outline: none;
    }
    textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(20, 83, 45, 0.15);
    }
    button {
      border: 0;
      border-radius: 10px;
      background: linear-gradient(135deg, var(--accent), #166534);
      color: #fff;
      padding: 0 1.1rem;
      min-width: 110px;
      font-weight: 600;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    @keyframes pop-in {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @media (max-width: 760px) {
      .app { height: 94vh; border-radius: 12px; }
      .msg { max-width: 94%; }
      form { grid-template-columns: 1fr; }
      button { min-height: 44px; }
    }
  </style>
</head>
<body>
  <div class=\"app\">
    <header>
      <h1>Clarion Hosted Agent Web Chat</h1>
      <div class=\"status\" id=\"status\">Ready</div>
    </header>

    <main id=\"messages\">__SERVER_HISTORY__</main>

    <form id=\"chat-form\" method=\"post\" action=\"/chat\">
      <textarea id=\"prompt\" name=\"input\" placeholder=\"Ask about Teams, OneDrive, Outlook, or corpus status...\" required></textarea>
      <button id=\"send\" type=\"submit\">Send</button>
    </form>
  </div>

  <noscript>
    <div style=\"position:fixed;bottom:10px;left:10px;right:10px;background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px;font-family:Segoe UI,Trebuchet MS,sans-serif;\">
      JavaScript is disabled or blocked. Using server-side fallback mode.
    </div>
  </noscript>

  <script>
    const form = document.getElementById("chat-form");
    const promptInput = document.getElementById("prompt");
    const messages = document.getElementById("messages");
    const sendBtn = document.getElementById("send");
    const status = document.getElementById("status");

    function addMessage(role, text, isError = false) {
      const wrap = document.createElement("div");
      wrap.className = `msg ${role} ${isError ? "error" : ""}`;

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = role === "user" ? "You" : "Clarion Agent";

      const body = document.createElement("div");
      body.className = "msg-body";
      body.textContent = text;

      wrap.appendChild(meta);
      wrap.appendChild(body);
      messages.appendChild(wrap);
      messages.scrollTop = messages.scrollHeight;
      return wrap;
    }

    function updateMessage(messageEl, text, isError = false) {
      if (!messageEl) {
        return;
      }
      if (isError) {
        messageEl.classList.add("error");
      }
      const body = messageEl.querySelector(".msg-body");
      if (body) {
        body.textContent = text;
      }
      messages.scrollTop = messages.scrollHeight;
    }

    window.addEventListener("error", (event) => {
      addMessage("assistant", `Client error: ${event.message}`, true);
      status.textContent = "Client error";
    });

    window.addEventListener("unhandledrejection", (event) => {
      const reason = event.reason ? String(event.reason) : "Unknown promise rejection";
      addMessage("assistant", `Client error: ${reason}`, true);
      status.textContent = "Client error";
    });

    function extractAssistantText(payload) {
      if (!payload || typeof payload !== "object") {
        return "No output returned by hosted agent.";
      }

      if (payload.error) {
        return `Error: ${payload.error}`;
      }

      // Some runtime errors return { code, message } without an output array.
      if (payload.message && payload.code) {
        return `${payload.code}: ${payload.message}`;
      }

      if (payload.message && !Array.isArray(payload.output)) {
        return String(payload.message);
      }

      const chunks = [];
      if (!Array.isArray(payload.output)) {
        return `No text output returned by hosted agent. Raw status: ${payload.status || "unknown"}`;
      }

      for (const item of payload.output) {
        if (!item || typeof item !== "object") {
          continue;
        }

        if (item.type === "function_call_output" && item.output) {
          chunks.push(String(item.output));
        }

        if (!Array.isArray(item.content)) {
          continue;
        }

        for (const contentItem of item.content) {
          if (!contentItem || typeof contentItem !== "object") {
            continue;
          }

          if (contentItem.type === "output_text" && contentItem.text) {
            chunks.push(String(contentItem.text));
          } else if (contentItem.type === "text") {
            if (typeof contentItem.text === "string") {
              chunks.push(contentItem.text);
            } else if (contentItem.text && typeof contentItem.text === "object" && contentItem.text.value) {
              chunks.push(String(contentItem.text.value));
            }
          }
        }
      }

      if (chunks.length) {
        return chunks.join("\n");
      }

      return `No text output returned by hosted agent. Raw status: ${payload.status || "unknown"}`;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const prompt = promptInput.value.trim();
      if (!prompt) {
        return;
      }

      sendBtn.disabled = true;
      sendBtn.textContent = "Sending...";
      status.textContent = "Preparing request...";
      await new Promise((resolve) => requestAnimationFrame(resolve));

      addMessage("user", prompt);
      promptInput.value = "";
      status.textContent = "Waiting for response...";
      const pending = addMessage("assistant", "Thinking...");

      try {
        const response = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ input: prompt }),
        });

        const rawText = await response.text();
        let payload = null;
        try {
          payload = rawText ? JSON.parse(rawText) : {};
        } catch {
          payload = { error: "Received non-JSON response from server.", detail: rawText.slice(0, 400) };
        }

        if (!response.ok) {
          const message = payload && payload.error ? payload.error : `Request failed with status ${response.status}`;
          updateMessage(pending, message, true);
          status.textContent = "Request failed";
        } else {
          updateMessage(pending, extractAssistantText(payload));
          status.textContent = "Ready";
        }
      } catch (error) {
        updateMessage(pending, `Could not reach hosted agent: ${error}`, true);
        status.textContent = "Agent unavailable";
      } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = "Send";
        promptInput.focus();
      }
    });

    promptInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        form.requestSubmit();
      }
    });

    const hasServerHistory = messages.children.length > 0;
    if (!hasServerHistory) {
      addMessage("assistant", "Chat UI is connected. Send a prompt to the hosted agent.");
    }
  </script>
</body>
</html>
"""


STATUS_PAGE_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Clarion Tenant Health</title>
  <style>
    :root {
      --bg: #f8fafc;
      --card: #ffffff;
      --line: #dbe4ef;
      --ink: #0f172a;
      --ok: #166534;
      --warn: #92400e;
      --bad: #991b1b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 1rem;
      font-family: \"Segoe UI\", \"Trebuchet MS\", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 10%, #e0f2fe, transparent 30%),
        radial-gradient(circle at 90% 20%, #dcfce7, transparent 28%),
        var(--bg);
    }
    .card {
      max-width: 920px;
      margin: 0 auto;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--card);
      box-shadow: 0 12px 28px rgba(2, 6, 23, 0.08);
      overflow: hidden;
    }
    header {
      display: flex;
      gap: 1rem;
      justify-content: space-between;
      align-items: center;
      padding: 1rem 1.2rem;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(120deg, #0f172a, #1e3a8a);
      color: #f8fafc;
    }
    h1 { margin: 0; font-size: 1.05rem; }
    #overall { font-weight: 700; }
    main { padding: 1rem 1.2rem; }
    .meta { font-size: 0.9rem; opacity: 0.8; margin-bottom: 0.9rem; }
    table { width: 100%; border-collapse: collapse; }
    th, td {
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 0.6rem;
      vertical-align: top;
      font-size: 0.95rem;
    }
    .ok { color: var(--ok); font-weight: 700; }
    .warn { color: var(--warn); font-weight: 700; }
    .bad { color: var(--bad); font-weight: 700; }
  </style>
</head>
<body>
  <div class=\"card\">
    <header>
      <h1>Clarion Tenant Health</h1>
      <div id=\"overall\">Loading...</div>
    </header>
    <main>
      <div id=\"meta\" class=\"meta\"></div>
      <table>
        <thead>
          <tr><th>Check</th><th>Status</th><th>Detail</th></tr>
        </thead>
        <tbody id=\"rows\"></tbody>
      </table>
    </main>
  </div>
  <script>
    function statusClass(value) {
      if (value === \"ok\") return \"ok\";
      if (value === \"warn\") return \"warn\";
      return \"bad\";
    }

    async function refresh() {
      const response = await fetch('/api/tenant/health', { cache: 'no-store' });
      const payload = await response.json();

      const overall = document.getElementById('overall');
      const meta = document.getElementById('meta');
      const rows = document.getElementById('rows');

      overall.className = statusClass(payload.overall_status === 'healthy' ? 'ok' : payload.overall_status === 'degraded' ? 'warn' : 'bad');
      overall.textContent = payload.overall_status;
      meta.textContent = `last_checked_utc: ${payload.last_checked_utc} | tenant: ${payload.tenant_id || 'unknown'}`;

      rows.innerHTML = '';
      for (const [name, check] of Object.entries(payload.checks || {})) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${name}</td><td class=\"${statusClass(check.status)}\">${check.status}</td><td>${check.detail || ''}</td>`;
        rows.appendChild(tr);
      }
    }

    refresh().catch((error) => {
      document.getElementById('overall').textContent = `error: ${error}`;
    });
    setInterval(() => refresh().catch(() => {}), 10000);
  </script>
</body>
</html>
"""


CHAT_HISTORY: list[tuple[str, str, bool]] = [
    ("assistant", "Chat UI is connected. Send a prompt to the hosted agent.", False),
]


def _log_telemetry(event_name: str, **fields: object) -> None:
  payload = {
    "event": event_name,
    "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
  }
  payload.update(fields)
  LOGGER.info("telemetry %s", json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str))


def _status(ok: bool, detail: str) -> dict[str, str]:
  return {"status": "ok" if ok else "fail", "detail": detail}


def _warn(detail: str) -> dict[str, str]:
  return {"status": "warn", "detail": detail}


def _collect_tenant_health(agent_base_url: str, tenant_id: str) -> dict[str, object]:
  checks: dict[str, dict[str, str]] = {}

  corpus_path = Path(__file__).resolve().parents[1] / "data" / "processed" / "m365_corpus.jsonl"
  if corpus_path.exists():
    age_minutes = (datetime.now(UTC).timestamp() - corpus_path.stat().st_mtime) / 60.0
    checks["corpus"] = _status(True, f"available ({corpus_path}, age_minutes={age_minutes:.1f})")
  else:
    checks["corpus"] = _status(False, f"missing ({corpus_path})")

  has_project_endpoint = bool(
    os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    or os.getenv("AZURE_AI_PROJECT_ENDPOINT", "").strip()
  )
  has_model_deployment = bool(
    os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME", "").strip()
    or os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "").strip()
  )
  missing_env: list[str] = []
  if not has_project_endpoint:
    missing_env.append("FOUNDRY_PROJECT_ENDPOINT|AZURE_AI_PROJECT_ENDPOINT")
  if not has_model_deployment:
    missing_env.append("FOUNDRY_MODEL_DEPLOYMENT_NAME|AZURE_AI_MODEL_DEPLOYMENT_NAME")
  if missing_env:
    checks["foundry_config"] = _status(False, f"missing env vars: {', '.join(missing_env)}")
  else:
    checks["foundry_config"] = _status(True, "required env vars present")

  try:
    probe_payload = {"input": "What is my m365 status?", "stream": False}
    probe_response = asyncio.run(_call_hosted_agent(agent_base_url, probe_payload, timeout=20.0))
    checks["hosted_agent"] = _status(True, _extract_assistant_text(probe_response)[:180])
  except Exception as exc:  # noqa: BLE001
    checks["hosted_agent"] = _status(False, f"unreachable: {str(exc)[:180]}")

  has_warn = any(item["status"] == "warn" for item in checks.values())
  has_fail = any(item["status"] == "fail" for item in checks.values())
  overall_status = "unhealthy" if has_fail else "degraded" if has_warn else "healthy"

  return {
    "tenant_id": tenant_id,
    "overall_status": overall_status,
    "last_checked_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "checks": checks,
  }


def _extract_assistant_text(payload: dict) -> str:
  if not isinstance(payload, dict):
    return "No output returned by hosted agent."

  if payload.get("error"):
    return f"Error: {payload['error']}"

  if payload.get("code") and payload.get("message"):
    return f"{payload['code']}: {payload['message']}"

  if payload.get("message") and not isinstance(payload.get("output"), list):
    return str(payload["message"])

  output = payload.get("output", [])
  chunks: list[str] = []

  if not isinstance(output, list):
    return f"No text output returned by hosted agent. Raw status: {payload.get('status', 'unknown')}"

  for item in output:
    if not isinstance(item, dict):
      continue

    if item.get("type") == "function_call_output" and item.get("output"):
      chunks.append(str(item["output"]))

    content = item.get("content")
    if not isinstance(content, list):
      continue

    for content_item in content:
      if not isinstance(content_item, dict):
        continue

      if content_item.get("type") == "output_text" and content_item.get("text"):
        chunks.append(str(content_item["text"]))
        continue

      if content_item.get("type") == "text":
        text_value = content_item.get("text")
        if isinstance(text_value, str) and text_value:
          chunks.append(text_value)
        elif isinstance(text_value, dict) and text_value.get("value"):
          chunks.append(str(text_value["value"]))

  if chunks:
    return "\n".join(chunks)
  return f"No text output returned by hosted agent. Raw status: {payload.get('status', 'unknown')}"


def _render_history() -> str:
    parts: list[str] = []
    for role, text, is_error in CHAT_HISTORY:
        role_class = "user" if role == "user" else "assistant"
        error_class = " error" if is_error else ""
        label = "You" if role == "user" else "Clarion Agent"
        parts.append(
            "".join(
                [
                    f'<div class="msg {role_class}{error_class}">',
                    f'<div class="meta">{html.escape(label)}</div>',
                    f'<div class="msg-body">{html.escape(text)}</div>',
                    "</div>",
                ]
            )
        )
    return "".join(parts)


def _render_page() -> str:
    return HTML_PAGE.replace("__SERVER_HISTORY__", _render_history())


class WebChatHandler(BaseHTTPRequestHandler):
    agent_base_url = "http://127.0.0.1:8088"

    def _send_json(self, payload: dict, status_code: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        tenant_id = self.headers.get("x-tenant-id", "unknown")

        if path in ("/", "/index.html"):
            self._send_html(_render_page())
            return

        if path == "/status":
            self._send_html(STATUS_PAGE_HTML)
            return

        if path == "/api/tenant/health":
            health_payload = _collect_tenant_health(self.agent_base_url, tenant_id)
            _log_telemetry(
                "tenant_health_checked",
                tenant_id=tenant_id,
                overall_status=health_payload.get("overall_status"),
            )
            self._send_json(health_payload)
            return

        if path == "/api/chat":
            self._send_json(
                {
                    "message": "Use POST /api/chat with JSON body: {'input': 'your prompt'}",
                    "agent_url": f"{self.agent_base_url}/responses",
                }
            )
            return

        if path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path not in ("/api/chat", "/chat"):
            self.send_error(404, "Not found")
            return

        tenant_id = self.headers.get("x-tenant-id", "unknown")

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        prompt = ""
        if path == "/chat":
            form_values = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
            prompt = (form_values.get("input", [""])[0] or "").strip()
        else:
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON body."}, status_code=400)
                return
            prompt = (payload.get("input") or "").strip()

        if not prompt:
            if path == "/chat":
                CHAT_HISTORY.append(("assistant", "Field 'input' is required.", True))
                self._send_html(_render_page())
            else:
                self._send_json({"error": "Field 'input' is required."}, status_code=400)
            return

        if path == "/chat":
            CHAT_HISTORY.append(("user", prompt, False))

        request_payload = {
            "input": prompt,
            "stream": False,
        }
        request_started = perf_counter()

        try:
            response_payload = asyncio.run(_call_hosted_agent(self.agent_base_url, request_payload))
            latency_ms = int((perf_counter() - request_started) * 1000)
            _log_telemetry(
                "chat_request",
                tenant_id=tenant_id,
                outcome="ok",
                latency_ms=latency_ms,
                prompt_chars=len(prompt),
            )
            if path == "/chat":
                CHAT_HISTORY.append(("assistant", _extract_assistant_text(response_payload), False))
                self._send_html(_render_page())
            else:
                self._send_json(response_payload)
        except httpx.HTTPStatusError as exc:
            latency_ms = int((perf_counter() - request_started) * 1000)
            detail = exc.response.text[:800]
            error_payload = {
                "error": f"Hosted agent returned HTTP {exc.response.status_code}.",
                "detail": detail,
            }
            _log_telemetry(
                "chat_request",
                tenant_id=tenant_id,
                outcome="http_error",
                latency_ms=latency_ms,
                prompt_chars=len(prompt),
                status_code=exc.response.status_code,
            )
            if path == "/chat":
                CHAT_HISTORY.append(("assistant", f"{error_payload['error']} {detail}", True))
                self._send_html(_render_page())
            else:
                self._send_json(error_payload, status_code=502)
        except httpx.HTTPError as exc:
            latency_ms = int((perf_counter() - request_started) * 1000)
            error_payload = {
                "error": f"Could not connect to hosted agent at {self.agent_base_url}.",
                "detail": str(exc),
            }
            _log_telemetry(
                "chat_request",
                tenant_id=tenant_id,
                outcome="connect_error",
                latency_ms=latency_ms,
                prompt_chars=len(prompt),
            )
            if path == "/chat":
                CHAT_HISTORY.append(("assistant", f"{error_payload['error']} {error_payload['detail']}", True))
                self._send_html(_render_page())
            else:
                self._send_json(error_payload, status_code=502)


def _generate_self_signed_cert(cert_file: str, key_file: str) -> None:
    """Generate a self-signed certificate using cryptography library."""
    if not HAS_CRYPTOGRAPHY:
        raise ImportError(
            "cryptography library required for HTTPS cert generation. "
            "Install with: pip install cryptography"
        )
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    
    # Create certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "GB"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Local"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Clarion"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )
    
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.DNSName("127.0.0.1")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256(), default_backend())
    )
    
    # Write certificate to file
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    # Write private key to file
    with open(key_file, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )


def _run_server(host: str, port: int, agent_url: str, cert_file: str | None = None, key_file: str | None = None) -> None:
    WebChatHandler.agent_base_url = agent_url.rstrip("/")
    
    # Default paths for self-signed cert in script directory
    script_dir = Path(__file__).parent
    if cert_file is None:
        cert_file = str(script_dir / "webchat.crt")
    if key_file is None:
        key_file = str(script_dir / "webchat.key")
    
    # Generate self-signed certificate if missing
    cert_path = Path(cert_file)
    key_path = Path(key_file)
    if not cert_path.exists() or not key_path.exists():
        LOGGER.info("Generating self-signed certificate for HTTPS...")
        try:
            _generate_self_signed_cert(cert_file, key_file)
            LOGGER.info("Self-signed certificate generated at %s and %s", cert_file, key_file)
        except (ImportError, Exception) as e:
            LOGGER.error("Failed to generate self-signed certificate: %s", e)
            raise
    
    # Create HTTPS server with SSL context
    httpd = ThreadingHTTPServer((host, port), WebChatHandler)
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(cert_file, key_file)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    LOGGER.info("Clarion web chat running at https://%s:%s", host, port)
    LOGGER.info("Proxying requests to hosted agent endpoint at %s/responses", WebChatHandler.agent_base_url)
    LOGGER.warning("Self-signed certificate; browser will show security warning (expected for localhost).")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Shutting down web chat server")
    finally:
        httpd.server_close()


async def _call_hosted_agent(agent_base_url: str, payload: dict, timeout: float = 90.0) -> dict:
  async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{agent_base_url}/responses", json=payload)
        response.raise_for_status()
        return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local web chat UI for Clarion hosted agent")
    parser.add_argument("--host", default="127.0.0.1", help="Web server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8090, help="Web server port (default: 8090)")
    parser.add_argument(
        "--agent-url",
        default="http://127.0.0.1:8088",
        help="Hosted agent base URL (default: http://127.0.0.1:8088)",
    )
    parser.add_argument(
        "--cert",
        default=None,
        help="Path to SSL certificate file (default: webchat.crt in script directory)",
    )
    parser.add_argument(
        "--key",
        default=None,
        help="Path to SSL key file (default: webchat.key in script directory)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _run_server(args.host, args.port, args.agent_url, args.cert, args.key)


if __name__ == "__main__":
    main()
