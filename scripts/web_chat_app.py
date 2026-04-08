from __future__ import annotations

import argparse
import asyncio
import html
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx

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
      if (!payload || !Array.isArray(payload.output)) {
        if (payload && payload.error) {
          return `Error: ${payload.error}`;
        }
        return "No output returned by hosted agent.";
      }

      const chunks = [];
      for (const item of payload.output) {
        if (!item || !Array.isArray(item.content)) {
          if (item && item.type === "function_call_output" && item.output) {
            chunks.push(String(item.output));
          }
          continue;
        }
        for (const contentItem of item.content) {
          if (contentItem && contentItem.type === "output_text" && contentItem.text) {
            chunks.push(contentItem.text);
          }
        }
      }

      if (chunks.length) {
        return chunks.join("\n");
      }

      try {
        return `No text output returned by hosted agent. Raw status: ${payload.status || "unknown"}`;
      } catch {
        return "No text output returned by hosted agent.";
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const prompt = promptInput.value.trim();
      if (!prompt) {
        return;
      }

      addMessage("user", prompt);
      promptInput.value = "";
      sendBtn.disabled = true;
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


CHAT_HISTORY: list[tuple[str, str, bool]] = [
    ("assistant", "Chat UI is connected. Send a prompt to the hosted agent.", False),
]


def _extract_assistant_text(payload: dict) -> str:
    output = payload.get("output", [])
    chunks: list[str] = []

    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            for content_item in content:
                if (
                    isinstance(content_item, dict)
                    and content_item.get("type") == "output_text"
                    and content_item.get("text")
                ):
                    chunks.append(str(content_item["text"]))
        elif item.get("type") == "function_call_output" and item.get("output"):
            chunks.append(str(item["output"]))

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

        if path in ("/", "/index.html"):
            self._send_html(_render_page())
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

        try:
            response_payload = asyncio.run(_call_hosted_agent(self.agent_base_url, request_payload))
            if path == "/chat":
                CHAT_HISTORY.append(("assistant", _extract_assistant_text(response_payload), False))
                self._send_html(_render_page())
            else:
                self._send_json(response_payload)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:800]
            error_payload = {
                "error": f"Hosted agent returned HTTP {exc.response.status_code}.",
                "detail": detail,
            }
            if path == "/chat":
                CHAT_HISTORY.append(("assistant", f"{error_payload['error']} {detail}", True))
                self._send_html(_render_page())
            else:
                self._send_json(error_payload, status_code=502)
        except httpx.HTTPError as exc:
            error_payload = {
                "error": f"Could not connect to hosted agent at {self.agent_base_url}.",
                "detail": str(exc),
            }
            if path == "/chat":
                CHAT_HISTORY.append(("assistant", f"{error_payload['error']} {error_payload['detail']}", True))
                self._send_html(_render_page())
            else:
                self._send_json(error_payload, status_code=502)


def _run_server(host: str, port: int, agent_url: str) -> None:
    WebChatHandler.agent_base_url = agent_url.rstrip("/")
    httpd = ThreadingHTTPServer((host, port), WebChatHandler)
    LOGGER.info("Clarion web chat running at http://%s:%s", host, port)
    LOGGER.info("Proxying requests to hosted agent endpoint at %s/responses", WebChatHandler.agent_base_url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Shutting down web chat server")
    finally:
        httpd.server_close()


async def _call_hosted_agent(agent_base_url: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=90.0) as client:
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
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _run_server(args.host, args.port, args.agent_url)


if __name__ == "__main__":
    main()
