# nlm_extesion

Playwright automation for exporting NotebookLM infographic assets with a Chromium extension.

## What is implemented

- Persistent Chromium context with configurable extension path and browser profile path.
- Extension launch flags:
  - `--disable-extensions-except=<path>`
  - `--load-extension=<path>`
- UI automation to find extension-injected export controls and trigger export.
- Download persistence into `out/<job_id>/infographic/`.
- Format policy with PNG preference and JPG/WebP fallback.
- Manifest output recording exported file paths, formats, and timestamps.

## Usage

```python
from pathlib import Path
from export_automation import ExportConfig, run_export_job_sync

config = ExportConfig(
    job_id="job-123",
    target_url="https://notebooklm.google.com",
    extension_path=Path("/path/to/notebooklm-export-extension"),
    browser_profile_path=Path("/path/to/chromium-profile"),
)

manifest = run_export_job_sync(config)
print(manifest)
```

The manifest is written at:

`out/<job_id>/infographic/manifest.json`
