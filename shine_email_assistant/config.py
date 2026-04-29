"""Tenant config loader. Reads tenants/<name>/config.yaml into a typed dataclass."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class TenantConfig:
    display_name: str
    brand_color: str
    website: str
    address: str
    phone: str
    reply_signoff: str


def load_tenant_config(tenant_dir: Path) -> TenantConfig:
    config_path = tenant_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"No config.yaml in {tenant_dir}")
    raw = yaml.safe_load(config_path.read_text())
    return TenantConfig(
        display_name=raw["display_name"],
        brand_color=raw["brand_color"],
        website=raw["website"],
        address=raw["address"],
        phone=raw["phone"],
        reply_signoff=raw["reply_signoff"],
    )
