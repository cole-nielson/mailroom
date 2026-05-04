from pathlib import Path

import pytest

from shine_email_assistant.config import TenantConfig, load_tenant_config


def test_load_tenant_config_reads_yaml(tmp_path: Path):
    tenant_dir = tmp_path / "example"
    tenant_dir.mkdir()
    (tenant_dir / "config.yaml").write_text(
        "display_name: Example Co\n"
        "brand_color: '#1E3A8A'\n"
        "website: https://example.com\n"
        "address: 123 Main St, Anytown USA\n"
        "phone: '+1-555-0100'\n"
        "reply_signoff: '— Example Co'\n"
    )

    cfg = load_tenant_config(tenant_dir)

    assert isinstance(cfg, TenantConfig)
    assert cfg.display_name == "Example Co"
    assert cfg.brand_color == "#1E3A8A"
    assert cfg.website == "https://example.com"
    assert cfg.address == "123 Main St, Anytown USA"
    assert cfg.phone == "+1-555-0100"
    assert cfg.reply_signoff == "— Example Co"


def test_load_tenant_config_missing_field_raises_with_helpful_message(tmp_path: Path):
    tenant_dir = tmp_path / "example"
    tenant_dir.mkdir()
    (tenant_dir / "config.yaml").write_text("display_name: Example Co\n")
    with pytest.raises(KeyError, match="brand_color"):
        load_tenant_config(tenant_dir)


def test_load_tenant_config_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_tenant_config(tmp_path / "nope")
