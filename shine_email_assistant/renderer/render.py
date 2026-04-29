"""Wrap LLM body markdown in styled HTML + tenant signature template."""
from dataclasses import dataclass
from pathlib import Path

import markdown as md_lib
from jinja2 import Environment, StrictUndefined

from shine_email_assistant.config import load_tenant_config


@dataclass(frozen=True)
class RenderedEmail:
    html: str
    plaintext: str


def render(body_markdown: str, tenant_name: str, tenants_root: Path) -> RenderedEmail:
    tenant_dir = tenants_root / tenant_name
    cfg = load_tenant_config(tenant_dir)

    env = Environment(undefined=StrictUndefined, autoescape=False)

    body_html = md_lib.markdown(body_markdown, extensions=["extra"])

    sig_template = env.from_string((tenant_dir / "signature.html").read_text())
    signature_html = sig_template.render(
        display_name=cfg.display_name,
        brand_color=cfg.brand_color,
        website=cfg.website,
        address=cfg.address,
        phone=cfg.phone,
    )

    page_template = env.from_string((tenant_dir / "email_template.html").read_text())
    html = page_template.render(body_html=body_html, signature_html=signature_html)

    return RenderedEmail(html=html, plaintext=body_markdown)
