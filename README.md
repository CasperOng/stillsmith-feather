# Stillsmith — Feather source

A [Feather](https://github.com/khcrysalis/Feather) source for the unsigned builds of
[Stillsmith](https://github.com/CasperOng/Stillsmith), the iOS app
that pulls still frames out of videos at the video's own resolution.

## Add it to Feather

1. Open Feather → **Sources** → **+**
2. Paste this URL:

   ```
   https://raw.githubusercontent.com/CasperOng/stillsmith-feather/main/apps.json
   ```

3. Install or update **Stillsmith** from the source. Feather signs the IPA with your own certificate.

The feed always points at the newest build the app repository has published.

## What is in here

| Path | Purpose |
| --- | --- |
| `apps.json` | The Feather source itself |
| `ipas/Stillsmith-<version>-<build>-<sha>.ipa` | The newest unsigned build |
| `icons/FrameExtractor.png` | Source and app icon |
| `LATEST-BUILD.md` | Version, build, size and SHA-256 of the IPA |
| `scripts/update_feed.py` | Downloads the newest IPA and rewrites the files above |
| `.github/workflows/refresh.yml` | Runs that script on a schedule |

Every build gets its own file name. The path is unique per build on purpose:
`raw.githubusercontent.com` caches by path and was still serving the previous
IPA for a cache-busting query string, which could hand Feather an IPA that did
not match the version in `apps.json`. Older IPAs are deleted as each new one
arrives, so the repository holds exactly one build.

## How it updates itself

The app repository keeps a rolling pre-release tagged `latest`:

```
https://github.com/CasperOng/Stillsmith/releases/download/latest/Stillsmith-unsigned.ipa
```

`.github/workflows/refresh.yml` downloads that IPA, reads its version out of
`Info.plist`, copies it into `ipas/`, and commits the regenerated `apps.json` and
`LATEST-BUILD.md`. It runs every six hours, can be started by hand (**Actions →
Refresh Feed → Run workflow**), and does nothing when the feed is already current.

### Refreshing immediately (optional)

To have a new build appear in Feather as soon as CI finishes it, add a secret to the
**app** repository named `FEED_DISPATCH_TOKEN`: a fine-grained personal access token
with *Contents: read and write* on `stillsmith-feather`. The build workflow
then dispatches `frame-extractor-build` to this repository. Without the secret the
next scheduled run picks the build up instead.

## Notes

- The IPA is **unsigned**. Feather, AltStore, SideStore and similar tools sign it with
  the certificate on your device.
- This repository holds no source code; it only republishes build artefacts.
- `apps.json` and `LATEST-BUILD.md` are generated. Edit `scripts/update_feed.py`
  instead.
