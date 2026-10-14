"""Release integrity checks for AcePressure.

Verifies that VERSION, LICENSE, CHANGELOG, README, PACKAGE_MANIFEST, installer
batch files, and new 1.4.x scripts/services ship together in a self-consistent
state. Pure filesystem/parse checks; no app bootstrap required.
"""
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
LICENSE_FILE = ROOT / "LICENSE"
CHANGELOG_FILE = ROOT / "docs" / "CHANGELOG.md"
README_FILE = ROOT / "README.md"
MANIFEST_JSON = ROOT / "PACKAGE_MANIFEST.json"
MANIFEST_TXT = ROOT / "PACKAGE_MANIFEST.txt"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def _manifest_entries() -> list[dict]:
    return json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))


def test_version_file_is_valid_semver_on_one_line():
    raw = VERSION_FILE.read_text(encoding="utf-8")
    stripped = raw.strip()
    # Must be exactly one non-empty line
    non_empty_lines = [ln for ln in raw.splitlines() if ln.strip()]
    assert len(non_empty_lines) == 1, f"VERSION must be a single line, got {non_empty_lines!r}"
    assert SEMVER_RE.match(stripped), f"VERSION {stripped!r} is not X.Y.Z semver"


def test_license_exists_and_is_mit():
    assert LICENSE_FILE.is_file(), "LICENSE file missing at repo root"
    text = LICENSE_FILE.read_text(encoding="utf-8")
    assert "MIT License" in text, "LICENSE does not identify as MIT License"


def test_changelog_contains_current_version_heading():
    assert CHANGELOG_FILE.is_file(), "docs/CHANGELOG.md missing"
    text = CHANGELOG_FILE.read_text(encoding="utf-8")
    version = _version()
    # Look for a markdown H1 heading starting with the version, e.g. "# 1.4.1 — ..."
    heading_re = re.compile(rf"^#\s+{re.escape(version)}\b", re.MULTILINE)
    assert heading_re.search(text), (
        f"CHANGELOG.md is missing a '# {version}' heading for the current release"
    )


def test_readme_mentions_current_version():
    assert README_FILE.is_file(), "README.md missing at repo root"
    text = README_FILE.read_text(encoding="utf-8")
    version = _version()
    assert version in text, f"README.md does not mention the current VERSION {version}"


def test_package_manifest_json_is_valid_list_of_entries():
    assert MANIFEST_JSON.is_file(), "PACKAGE_MANIFEST.json missing"
    entries = _manifest_entries()
    assert isinstance(entries, list) and entries, "PACKAGE_MANIFEST.json must be a non-empty JSON list"
    required_keys = {"path", "bytes", "sha256"}
    for i, entry in enumerate(entries):
        assert isinstance(entry, dict), f"entry {i} is not a dict"
        missing = required_keys - entry.keys()
        assert not missing, f"entry {i} ({entry.get('path')!r}) missing keys: {missing}"
        assert isinstance(entry["path"], str) and entry["path"], f"entry {i} has bad path"
        assert isinstance(entry["bytes"], int) and entry["bytes"] >= 0, f"entry {i} bytes not non-negative int"
        assert isinstance(entry["sha256"], str) and len(entry["sha256"]) == 64, (
            f"entry {i} sha256 not a 64-char hex string"
        )


def test_package_manifest_has_at_least_125_entries():
    entries = _manifest_entries()
    assert len(entries) >= 125, f"PACKAGE_MANIFEST.json has only {len(entries)} entries (expected >= 125)"


def test_sampled_manifest_paths_exist_on_disk():
    entries = _manifest_entries()
    # Sample 10 evenly-spaced entries so the check covers top, middle, and tail of the manifest
    n = len(entries)
    step = max(1, n // 10)
    sample = entries[::step][:10]
    assert len(sample) == 10, f"expected to sample 10 entries, got {len(sample)}"
    for entry in sample:
        p = ROOT / entry["path"]
        assert p.is_file(), f"manifest path missing on disk: {entry['path']}"


def test_sampled_manifest_hashes_match_disk():
    entries = _manifest_entries()
    n = len(entries)
    step = max(1, n // 10)
    sample = entries[::step][:10]
    for entry in sample:
        p = ROOT / entry["path"]
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == entry["sha256"], (
            f"sha256 mismatch for {entry['path']}: manifest={entry['sha256']} disk={actual}"
        )


def test_package_manifest_txt_entry_count_matches_json():
    assert MANIFEST_TXT.is_file(), "PACKAGE_MANIFEST.txt missing"
    txt_lines = [ln for ln in MANIFEST_TXT.read_text(encoding="utf-8").splitlines() if ln.strip()]
    json_count = len(_manifest_entries())
    assert len(txt_lines) == json_count, (
        f"PACKAGE_MANIFEST.txt has {len(txt_lines)} entries, JSON has {json_count}"
    )


def test_installer_batch_files_exist():
    for name in ("Install_Edge_TTS.bat", "Install_Piper.bat", "Setup_Tailscale_URL.bat"):
        p = ROOT / name
        assert p.is_file(), f"required installer missing at repo root: {name}"


@pytest.mark.parametrize(
    "rel_path",
    [
        "scripts/setup_tailscale_funnel.py",
        "scripts/download_piper_voices.py",
        "acepressure/edge_tts_service.py",
        "acepressure/piper_tts_service.py",
    ],
)
def test_python_source_files_exist_and_parse(rel_path):
    p = ROOT / rel_path
    assert p.is_file(), f"missing Python source: {rel_path}"
    src = p.read_text(encoding="utf-8")
    # compile raises SyntaxError if the file is not valid Python
    compile(src, str(p), "exec")


def test_manifest_ships_env_template_but_never_real_env():
    """setup.py builds .env from .env.example on first run, so the zip must contain the template.
    Builds before 1.5.9 skipped every '.env*' file, which crashed fresh installs after the password prompt."""
    paths = {e["path"] for e in _manifest_entries()}
    assert ".env.example" in paths, ".env.example missing from PACKAGE_MANIFEST (fresh installs would crash)"
    leaked = sorted(p for p in paths if p.split("/")[-1].startswith(".env") and p != ".env.example")
    assert not leaked, f"real environment files must never ship: {leaked}"


def test_env_template_contains_no_secrets():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in ["ADMIN_PASSWORD_HASH", "APP_SECRET", "IDENTITY_SECRET", "BRIDGE_TOKEN", "OVERLAY_TOKEN", "AZURE_SPEECH_KEY"]:
        assert re.search(rf"^{key}=$", text, re.MULTILINE), f"{key} must be empty in .env.example (setup.py fills it)"
