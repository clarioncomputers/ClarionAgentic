from __future__ import annotations

import argparse
import json
import os
import re
import zipfile
from pathlib import Path


PLACEHOLDER_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _load_mapping(args: argparse.Namespace) -> dict[str, str]:
    mapping = {
        "TEAMS_APP_ID": args.teams_app_id or os.getenv("TEAMS_APP_ID", ""),
        "BOT_APP_ID": args.bot_app_id or os.getenv("BOT_APP_ID", ""),
        "AGENT_HOST_DOMAIN": args.agent_host_domain or os.getenv("AGENT_HOST_DOMAIN", ""),
        "DEVELOPER_NAME": args.developer_name or os.getenv("DEVELOPER_NAME", ""),
        "DEVELOPER_WEBSITE": args.developer_website or os.getenv("DEVELOPER_WEBSITE", ""),
        "DEVELOPER_PRIVACY": args.developer_privacy or os.getenv("DEVELOPER_PRIVACY", ""),
        "DEVELOPER_TERMS": args.developer_terms or os.getenv("DEVELOPER_TERMS", ""),
    }
    return {key: value for key, value in mapping.items() if value}


def _replace_placeholders(template_text: str, mapping: dict[str, str]) -> str:
    def replace_match(match: re.Match[str]) -> str:
        key = match.group(1)
        return mapping.get(key, match.group(0))

    rendered = PLACEHOLDER_RE.sub(replace_match, template_text)
    unresolved = sorted(set(PLACEHOLDER_RE.findall(rendered)))
    if unresolved:
        unresolved_text = ", ".join(unresolved)
        raise ValueError(f"Unresolved placeholders in manifest: {unresolved_text}")
    return rendered


def _apply_optional_overrides(manifest: dict, args: argparse.Namespace) -> dict:
    if args.app_name_short:
        manifest.setdefault("name", {})["short"] = args.app_name_short
    if args.app_name_full:
        manifest.setdefault("name", {})["full"] = args.app_name_full
    if args.app_description_short:
        manifest.setdefault("description", {})["short"] = args.app_description_short
    if args.app_description_full:
        manifest.setdefault("description", {})["full"] = args.app_description_full

    developer = manifest.setdefault("developer", {})
    if args.developer_name:
        developer["name"] = args.developer_name
    if args.developer_website:
        developer["websiteUrl"] = args.developer_website
    if args.developer_privacy:
        developer["privacyUrl"] = args.developer_privacy
    if args.developer_terms:
        developer["termsOfUseUrl"] = args.developer_terms

    return manifest


def _write_package(zip_path: Path, manifest_path: Path, color_icon: Path, outline_icon: Path) -> None:
    if not color_icon.exists() or not outline_icon.exists():
        raise FileNotFoundError("Missing icon files. Expected color.png and outline.png in teams-app folder.")

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(manifest_path, arcname="manifest.json")
        archive.write(color_icon, arcname="color.png")
        archive.write(outline_icon, arcname="outline.png")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render and package Teams manifest from template placeholders")
    parser.add_argument("--template", default="teams-app/manifest.template.json", help="Path to template manifest")
    parser.add_argument("--output", default="teams-app/dist/manifest.json", help="Path to rendered manifest")
    parser.add_argument("--zip-output", default="teams-app/dist/clarion-teams-app.zip", help="Path to Teams app zip")
    parser.add_argument("--no-zip", action="store_true", help="Only render manifest.json and skip zip package")

    parser.add_argument("--teams-app-id", default="", help="Teams app ID")
    parser.add_argument("--bot-app-id", default="", help="Bot app ID")
    parser.add_argument("--agent-host-domain", default="", help="Hosted domain")

    parser.add_argument("--developer-name", default="", help="Developer display name")
    parser.add_argument("--developer-website", default="", help="Developer website URL")
    parser.add_argument("--developer-privacy", default="", help="Developer privacy URL")
    parser.add_argument("--developer-terms", default="", help="Developer terms URL")

    parser.add_argument("--app-name-short", default="", help="App short name override")
    parser.add_argument("--app-name-full", default="", help="App full name override")
    parser.add_argument("--app-description-short", default="", help="Short description override")
    parser.add_argument("--app-description-full", default="", help="Full description override")

    args = parser.parse_args()

    template_path = Path(args.template)
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    mapping = _load_mapping(args)
    rendered_text = _replace_placeholders(template_path.read_text(encoding="utf-8"), mapping)
    manifest_data = json.loads(rendered_text)
    manifest_data = _apply_optional_overrides(manifest_data, args)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    print(f"Rendered manifest: {output_path}")

    if not args.no_zip:
        teams_root = template_path.parent
        zip_path = Path(args.zip_output)
        _write_package(
            zip_path=zip_path,
            manifest_path=output_path,
            color_icon=teams_root / "color.png",
            outline_icon=teams_root / "outline.png",
        )
        print(f"Packaged Teams app zip: {zip_path}")


if __name__ == "__main__":
    main()
