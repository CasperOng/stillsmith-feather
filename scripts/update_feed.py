#!/usr/bin/env python3
"""Publish the newest unsigned Stillsmith build into this Feather source.

The app repository builds an unsigned IPA and keeps it at a stable URL:

    https://github.com/CasperOng/Stillsmith/releases/download/latest/Stillsmith-unsigned.ipa

This script downloads that IPA (no token needed, the release is public), reads
the version out of its Info.plist, and rewrites the files Feather reads here:

    ipas/Stillsmith-<version>-<build>-<sha>.ipa
    apps.json
    LATEST-BUILD.md

It is idempotent: nothing is written when the feed already describes the build.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import plistlib
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

SOURCE_REPO = os.environ.get("SOURCE_REPO", "CasperOng/Stillsmith")
SOURCE_TAG = os.environ.get("SOURCE_TAG", "latest")
SOURCE_ASSET = os.environ.get("SOURCE_ASSET", "Stillsmith-unsigned.ipa")
FEED_OWNER = os.environ.get("FEED_OWNER", "CasperOng")
FEED_REPO = os.environ.get("FEED_REPO", "stillsmith-feather")
FEED_BRANCH = os.environ.get("FEED_BRANCH", "main")

IPA_DIR = ROOT / "ipas"
FEED_PATH = ROOT / "apps.json"
LATEST_PATH = ROOT / "LATEST-BUILD.md"

RAW_BASE = f"https://raw.githubusercontent.com/{FEED_OWNER}/{FEED_REPO}/{FEED_BRANCH}"

# Everything about the app that does not change from build to build.
APP = {
    "name": "Stillsmith",
    "bundleIdentifier": "caspernyong.Stillsmith",
    "developerName": "Casper Ong",
    "subtitle": "Pull stills out of any video",
    "category": "utilities",
    "tintColor": "#0A84FF",
    "localizedDescription": (
        "Mark frames while a video plays, then save every one of them to your photo "
        "library at the video's own resolution. Videos can be chosen in the app or "
        "handed over from the share sheet, Files, AirDrop and stillsmith:// links."
    ),
    "privacy": {
        "NSPhotoLibraryAddUsageDescription": "Stillsmith saves the frames you extract to your photo library.",
        "NSPhotoLibraryUsageDescription": "Stillsmith reads the videos you choose and removes frames from your library when you delete them.",
    },
}


def log(message: str) -> None:
    print(message, flush=True)


def release_download_url(tag: str, asset: str) -> str:
    """Asset URL for `tag`, falling back to the newest release that has it."""
    direct = f"https://github.com/{SOURCE_REPO}/releases/download/{tag}/{asset}"
    log(f"Looking for {asset} at {direct}")
    try:
        with urlopen(Request(direct, method="HEAD"), timeout=30) as response:
            if response.status == 200:
                return direct
    except HTTPError as error:
        if error.code not in (403, 404):
            raise
        log(f"  not published at that tag ({error.code}); falling back to the release list")

    api = f"https://api.github.com/repos/{SOURCE_REPO}/releases?per_page=20"
    with urlopen(Request(api, headers={"Accept": "application/vnd.github+json"}), timeout=30) as response:
        releases = json.load(response)

    for release in releases:
        if release.get("draft"):
            continue
        for candidate in release.get("assets", []):
            if candidate.get("name") == asset:
                log(f"  using release {release['tag_name']}")
                return candidate["browser_download_url"]

    raise SystemExit(f"No release of {SOURCE_REPO} publishes an asset named {asset}")


def download(url: str) -> bytes:
    log(f"Downloading {url}")
    with urlopen(Request(url, headers={"Accept": "application/octet-stream"}), timeout=600) as response:
        data = response.read()
    log(f"  {len(data):,} bytes")
    return data


def read_app_info(ipa: bytes) -> dict:
    """Version, build and minimum OS from the app inside the IPA."""
    with zipfile.ZipFile(io.BytesIO(ipa)) as archive:
        plist_name = next(
            (name for name in archive.namelist() if name.startswith("Payload/") and name.endswith(".app/Info.plist")),
            None,
        )
        if plist_name is None:
            raise SystemExit("The IPA does not contain Payload/*.app/Info.plist")
        log(f"Reading {plist_name}")
        info = plistlib.loads(archive.read(plist_name))

    version = info.get("CFBundleShortVersionString")
    build = str(info.get("CFBundleVersion", ""))
    if not version or not build:
        raise SystemExit("The app's Info.plist has no version or build number")
    return {
        "version": version,
        "build": build,
        "minimumOSVersion": info.get("MinimumOSVersion", "17.0"),
        "bundleIdentifier": info.get("CFBundleIdentifier", APP["bundleIdentifier"]),
    }


def current_version_entry() -> dict | None:
    if not FEED_PATH.exists():
        return None
    try:
        feed = json.loads(FEED_PATH.read_text())
        return feed["apps"][0]["versions"][0]
    except (json.JSONDecodeError, KeyError, IndexError):
        return None


def ipa_file_name(info: dict, digest: str) -> str:
    """A file name that is unique per build.

    raw.githubusercontent.com caches by path and ignored the cache-busting query
    string the feed used to rely on, so a new build can be served from a stale
    cache entry. Giving every build its own path removes the ambiguity.
    """
    return f"Stillsmith-{info['version']}-{info['build']}-{digest[:8]}.ipa"


def build_feed(info: dict, size: int, digest: str, built_at: datetime, ipa_name: str) -> dict:
    icon_url = f"{RAW_BASE}/icons/Stillsmith.png"
    version_entry = {
        "version": info["version"],
        "buildVersion": info["build"],
        "date": built_at.date().isoformat(),
        "localizedDescription": (
            f"Version {info['version']} (build {info['build']}) — unsigned, ready to sign with Feather."
        ),
        "downloadURL": f"{RAW_BASE}/ipas/{ipa_name}",
        "size": size,
        "sha256": digest,
        "minOSVersion": info["minimumOSVersion"],
    }

    return {
        "name": APP["name"],
        "subtitle": APP["subtitle"],
        "description": "Unsigned Stillsmith builds for signing with Feather.",
        "iconURL": icon_url,
        "tintColor": APP["tintColor"],
        "apps": [
            {
                "name": APP["name"],
                "bundleIdentifier": info["bundleIdentifier"],
                "developerName": APP["developerName"],
                "subtitle": APP["subtitle"],
                "localizedDescription": APP["localizedDescription"],
                "iconURL": icon_url,
                "tintColor": APP["tintColor"],
                "category": APP["category"],
                "appPermissions": {
                    "entitlements": [],
                    "privacy": APP["privacy"],
                },
                "versions": [version_entry],
            }
        ],
    }


def build_latest_markdown(info: dict, size: int, digest: str, built_at: datetime, source_url: str, ipa_name: str) -> str:
    return f"""# Latest build

| | |
| --- | --- |
| **Version** | {info['version']} |
| **Build** | {info['build']} |
| **Minimum iOS** | {info['minimumOSVersion']} |
| **Size** | {size:,} bytes |
| **SHA-256** | `{digest}` |
| **Published** | {built_at.strftime('%Y-%m-%d %H:%M UTC')} |
| **Source** | [Stillsmith](https://github.com/{SOURCE_REPO}) |

Download: [ipas/{ipa_name}](ipas/{ipa_name}) — taken from {source_url}

This file is rewritten by `.github/workflows/refresh.yml`; do not edit it by hand.
"""


def set_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-file", type=Path, help="use a local IPA instead of downloading one")
    parser.add_argument("--dry-run", action="store_true", help="report what would change without writing")
    args = parser.parse_args()

    if args.from_file:
        ipa = args.from_file.read_bytes()
        source_url = str(args.from_file)
    else:
        source_url = release_download_url(SOURCE_TAG, SOURCE_ASSET)
        ipa = download(source_url)

    info = read_app_info(ipa)
    digest = hashlib.sha256(ipa).hexdigest()
    built_at = datetime.now(timezone.utc)

    current = current_version_entry()
    if current and current.get("version") == info["version"] and str(current.get("buildVersion")) == info["build"]:
        if current.get("sha256") == digest:
            log(f"Feed already describes {info['version']} ({info['build']}); nothing to do")
            set_output("changed", "false")
            set_output("version", info["version"])
            set_output("build", info["build"])
            return 0
        log(f"Rebuilding feed for {info['version']} ({info['build']}): the IPA changed")

    log(f"Publishing {info['version']} (build {info['build']})")
    if args.dry_run:
        log("Dry run: nothing written")
        set_output("changed", "true")
        set_output("version", info["version"])
        set_output("build", info["build"])
        return 0

    ipa_name = ipa_file_name(info, digest)
    IPA_DIR.mkdir(parents=True, exist_ok=True)
    (IPA_DIR / ipa_name).write_bytes(ipa)
    # One build at a time: drop the previous IPA so the repository stays small.
    for existing in IPA_DIR.glob("Stillsmith-*.ipa"):
        if existing.name != ipa_name:
            existing.unlink()
            log(f"Removed {existing.relative_to(ROOT)}")

    FEED_PATH.write_text(json.dumps(build_feed(info, len(ipa), digest, built_at, ipa_name), indent=2) + "\n")
    LATEST_PATH.write_text(build_latest_markdown(info, len(ipa), digest, built_at, source_url, ipa_name))

    set_output("changed", "true")
    set_output("version", info["version"])
    set_output("build", info["build"])
    log(f"Wrote ipas/{ipa_name}, {FEED_PATH.name} and {LATEST_PATH.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (HTTPError, URLError) as error:
        sys.exit(f"Could not reach GitHub: {error}")
