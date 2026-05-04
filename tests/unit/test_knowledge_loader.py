import time
from pathlib import Path

from mailroom.knowledge.loader import KnowledgeBundle, KnowledgeLoader


def _seed_tenant(root: Path, name: str) -> Path:
    tdir = root / name
    (tdir / "knowledge").mkdir(parents=True)
    (tdir / "knowledge" / "pricing.md").write_text("# Pricing\n\nFree estimates.\n")
    (tdir / "knowledge" / "services.md").write_text("# Services\n\nInspections, repairs, replacements.\n")
    (tdir / "voice.md").write_text("# Voice\n\nWarm and concise.\n")
    return tdir


def test_load_returns_concatenated_kb_and_voice(tmp_path: Path):
    tenant_dir = _seed_tenant(tmp_path, "example")
    loader = KnowledgeLoader(tmp_path)

    bundle = loader.load("example")

    assert isinstance(bundle, KnowledgeBundle)
    assert "Pricing" in bundle.kb_text
    assert "Services" in bundle.kb_text
    assert "Warm and concise" in bundle.voice_text
    # version should be a stable hash of the content
    assert isinstance(bundle.version, str) and len(bundle.version) >= 8


def test_load_caches_until_file_changes(tmp_path: Path):
    tenant_dir = _seed_tenant(tmp_path, "example")
    loader = KnowledgeLoader(tmp_path)

    first = loader.load("example")
    second = loader.load("example")
    assert first is second  # same cached object

    # mutate a file; loader should detect and reload
    time.sleep(0.01)
    (tenant_dir / "knowledge" / "pricing.md").write_text("# Pricing\n\nNow charging for estimates.\n")
    third = loader.load("example")
    assert third is not first
    assert "Now charging" in third.kb_text
    assert third.version != first.version


def test_load_raises_if_tenant_missing(tmp_path: Path):
    loader = KnowledgeLoader(tmp_path)
    try:
        loader.load("nonexistent")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
