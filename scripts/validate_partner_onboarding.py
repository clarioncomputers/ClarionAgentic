from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

import httpx
from dotenv import load_dotenv

from consent_check_server import _decode_jwt_payload, _evaluate_consent


def _run_graph_preflight(repo_root: Path) -> dict[str, object]:
    started = perf_counter()
    command = [sys.executable, str(repo_root / "scripts" / "check_graph_access.py")]
    proc = subprocess.run(command, capture_output=True, text=True, cwd=str(repo_root), check=False)
    elapsed_ms = int((perf_counter() - started) * 1000)

    return {
        "ok": proc.returncode == 0,
        "return_code": proc.returncode,
        "latency_ms": elapsed_ms,
        "stdout": proc.stdout[-1500:],
        "stderr": proc.stderr[-1500:],
    }


def _check_corpus(repo_root: Path) -> dict[str, object]:
    corpus_path = repo_root / "data" / "processed" / "m365_corpus.jsonl"
    if corpus_path.exists():
        return {"ok": True, "detail": f"Corpus found at {corpus_path}"}
    return {"ok": False, "detail": f"Corpus missing at {corpus_path}"}


def _check_consent_token(access_token: str | None) -> dict[str, object]:
    if not access_token:
        return {"ok": False, "status": "warn", "detail": "No access token provided; consent readiness not verified."}

    try:
        claims = _decode_jwt_payload(access_token)
        result = _evaluate_consent(claims)
        return {
            "ok": bool(result.get("is_ready_for_either")),
            "status": "ok" if result.get("is_ready_for_either") else "fail",
            "detail": "Consent claims evaluated.",
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "fail", "detail": f"Token validation failed: {exc}"}


def _probe_agent(agent_url: str) -> dict[str, object]:
    payload = {"input": "What is my m365 status?", "stream": False}
    started = perf_counter()
    try:
        response = httpx.post(f"{agent_url.rstrip('/')}/responses", json=payload, timeout=20.0)
        elapsed_ms = int((perf_counter() - started) * 1000)
        if response.status_code >= 400:
            return {
                "ok": False,
                "status": "fail",
                "latency_ms": elapsed_ms,
                "detail": f"HTTP {response.status_code}",
                "response_snippet": response.text[:600],
            }
        return {
            "ok": True,
            "status": "ok",
            "latency_ms": elapsed_ms,
            "detail": "Hosted agent responded.",
        }
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status": "fail",
            "latency_ms": elapsed_ms,
            "detail": f"Agent probe failed: {exc}",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate partner onboarding readiness for Clarion Agentic")
    parser.add_argument("--agent-url", default="http://127.0.0.1:8088", help="Hosted agent base URL")
    parser.add_argument("--token", default="", help="Customer tenant access token for consent readiness checks")
    parser.add_argument("--skip-graph", action="store_true", help="Skip Graph preflight check")
    parser.add_argument("--skip-agent", action="store_true", help="Skip hosted agent probe")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    load_dotenv(override=False)
    repo_root = Path(__file__).resolve().parents[1]

    checks: dict[str, dict[str, object]] = {}

    checks["corpus"] = _check_corpus(repo_root)
    checks["consent"] = _check_consent_token(args.token.strip() or None)

    if not args.skip_graph:
        graph = _run_graph_preflight(repo_root)
        checks["graph_preflight"] = {
            "ok": graph["ok"],
            "status": "ok" if graph["ok"] else "fail",
            "detail": "Graph preflight completed." if graph["ok"] else "Graph preflight failed.",
            "latency_ms": graph["latency_ms"],
            "stdout": graph["stdout"],
            "stderr": graph["stderr"],
        }

    if not args.skip_agent:
        checks["hosted_agent"] = _probe_agent(args.agent_url)

    critical_failures = [name for name, result in checks.items() if result.get("status") == "fail"]
    warnings = [name for name, result in checks.items() if result.get("status") == "warn"]

    overall = "ready"
    if critical_failures:
        overall = "not_ready"
    elif warnings:
        overall = "ready_with_warnings"

    output = {
        "overall": overall,
        "critical_failures": critical_failures,
        "warnings": warnings,
        "checks": checks,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print("Partner Onboarding Validator")
        print("============================")
        print(f"Overall: {overall}")
        for name, result in checks.items():
            mark = "OK" if result.get("status") == "ok" else "WARN" if result.get("status") == "warn" else "FAIL"
            print(f"{mark:4} {name:16} {result.get('detail', '')}")

        if critical_failures:
            print("\nCritical failures:")
            for item in critical_failures:
                print(f"- {item}")

        if warnings:
            print("\nWarnings:")
            for item in warnings:
                print(f"- {item}")

    raise SystemExit(1 if critical_failures else 0)


if __name__ == "__main__":
    main()
