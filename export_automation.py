from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from playwright.async_api import BrowserContext, Download, Page, Playwright, async_playwright
except Exception:  # pragma: no cover - allows unit tests without playwright installed
    BrowserContext = Any
    Download = Any
    Page = Any
    Playwright = Any
    async_playwright = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ExportConfig:
    job_id: str
    target_url: str
    extension_path: Path
    browser_profile_path: Path
    out_root: Path = Path("out")
    timeout_ms: int = 15000
    headless: bool = False

    @property
    def infographic_dir(self) -> Path:
        return self.out_root / self.job_id / "infographic"

    @property
    def launch_args(self) -> list[str]:
        ext = str(self.extension_path.resolve())
        return [
            f"--disable-extensions-except={ext}",
            f"--load-extension={ext}",
        ]


@dataclass(slots=True)
class ExportRecord:
    file_path: str
    file_format: str
    exported_at: str = field(default_factory=_utc_now_iso)


EXPORT_CONTROL_SELECTORS = [
    '[data-testid="nlm-export"]',
    '[data-testid="notebooklm-export"]',
    '[aria-label*="Export" i]',
    'button:has-text("Export")',
    'button:has-text("Infographic")',
]

FORMAT_SELECTOR_MAP: dict[str, list[str]] = {
    "png": ['[role="menuitem"]:has-text("PNG")', 'button:has-text("PNG")', "text=PNG"],
    "jpg": ['[role="menuitem"]:has-text("JPG")', '[role="menuitem"]:has-text("JPEG")', 'button:has-text("JPG")', "text=JPEG"],
    "webp": ['[role="menuitem"]:has-text("WebP")', 'button:has-text("WebP")', "text=WebP"],
}

PREFERRED_FORMATS = ["png", "jpg", "webp"]


async def launch_persistent_chromium(playwright: Playwright, config: ExportConfig) -> BrowserContext:
    config.browser_profile_path.mkdir(parents=True, exist_ok=True)
    return await playwright.chromium.launch_persistent_context(
        user_data_dir=str(config.browser_profile_path),
        headless=config.headless,
        args=config.launch_args,
        accept_downloads=True,
    )


async def _first_visible_locator(page: Page, selectors: Iterable[str]):
    for selector in selectors:
        locator = page.locator(selector).first
        if await locator.count() > 0 and await locator.is_visible():
            return locator
    return None


async def open_export_ui(page: Page, timeout_ms: int) -> None:
    export_control = await _first_visible_locator(page, EXPORT_CONTROL_SELECTORS)
    if export_control is None:
        raise RuntimeError("Could not find extension-injected export controls.")
    await export_control.click(timeout=timeout_ms)


async def choose_export_format(page: Page, timeout_ms: int, preferences: Iterable[str] = PREFERRED_FORMATS) -> str:
    for fmt in preferences:
        locator = await _first_visible_locator(page, FORMAT_SELECTOR_MAP.get(fmt, []))
        if locator is not None:
            await locator.click(timeout=timeout_ms)
            return fmt
    raise RuntimeError("No supported export format (PNG/JPG/WebP) found in export menu.")


async def export_infographic(page: Page, config: ExportConfig) -> tuple[Download, str]:
    await open_export_ui(page, config.timeout_ms)
    async with page.expect_download(timeout=config.timeout_ms) as download_info:
        selected_format = await choose_export_format(page, config.timeout_ms)
    download = await download_info.value
    return download, selected_format


async def save_download(download: Download, config: ExportConfig, fmt: str) -> ExportRecord:
    config.infographic_dir.mkdir(parents=True, exist_ok=True)
    suggested_name = download.suggested_filename
    if "." not in suggested_name:
        suggested_name = f"{suggested_name}.{fmt}"
    destination = config.infographic_dir / suggested_name
    await download.save_as(str(destination))
    return ExportRecord(file_path=str(destination), file_format=fmt)


def write_manifest(config: ExportConfig, records: list[ExportRecord]) -> Path:
    manifest_path = config.infographic_dir / "manifest.json"
    payload = {
        "job_id": config.job_id,
        "target_url": config.target_url,
        "created_at": _utc_now_iso(),
        "exports": [asdict(record) for record in records],
    }
    config.infographic_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


async def run_export_job(config: ExportConfig) -> Path:
    if async_playwright is None:
        raise RuntimeError("playwright is required to run exports")

    async with async_playwright() as playwright:
        context = await launch_persistent_chromium(playwright, config)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(config.target_url, wait_until="domcontentloaded")
            download, selected_format = await export_infographic(page, config)
            record = await save_download(download, config, selected_format)
            return write_manifest(config, [record])
        finally:
            await context.close()


def run_export_job_sync(config: ExportConfig) -> Path:
    return asyncio.run(run_export_job(config))
