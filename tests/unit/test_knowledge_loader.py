import time
from pathlib import Path

from shine_email_assistant.knowledge.loader import KnowledgeBundle, KnowledgeLoader


def _seed_tenant(root: Path, name: str) -> Path:
    tdir = root / name
    (tdir / "knowledge").mkdir(parents=True)
    (tdir / "knowledge" / "pricing.md").write_text("# Pricing\n\n$25/class\n")
    (tdir / "knowledge" / "schedule.md").write_text("# Schedule\n\nMon 6pm\n")
    (tdir / "voice.md").write_text("# Voice\n\nWarm and concise.\n")
    return tdir


def test_load_returns_concatenated_kb_and_voice(tmp_path: Path):
    tenant_dir = _seed_tenant(tmp_path, "shine")
    loader = KnowledgeLoader(tmp_path)

    bundle = loader.load("shine")

    assert isinstance(bundle, KnowledgeBundle)
    assert "Pricing" in bundle.kb_text
    assert "Schedule" in bundle.kb_text
    assert "Warm and concise" in bundle.voice_text
    # version should be a stable hash of the content
    assert isinstance(bundle.version, str) and len(bundle.version) >= 8


def test_load_caches_until_file_changes(tmp_path: Path):
    tenant_dir = _seed_tenant(tmp_path, "shine")
    loader = KnowledgeLoader(tmp_path)

    first = loader.load("shine")
    second = loader.load("shine")
    assert first is second  # same cached object

    # mutate a file; loader should detect and reload
    time.sleep(0.01)
    (tenant_dir / "knowledge" / "pricing.md").write_text("# Pricing\n\n$30/class\n")
    third = loader.load("shine")
    assert third is not first
    assert "$30/class" in third.kb_text
    assert third.version != first.version


def test_load_raises_if_tenant_missing(tmp_path: Path):
    loader = KnowledgeLoader(tmp_path)
    try:
        loader.load("nonexistent")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
