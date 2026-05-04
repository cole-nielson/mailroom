"""Wrap LLM body markdown in styled HTML + tenant signature template."""
import re
from dataclasses import dataclass
from pathlib import Path

import bleach
import markdown as md_lib
from jinja2 import Environment, StrictUndefined

from mailroom.config import load_tenant_config

# Tags whose entire content (not just the tag) must be removed.
_STRIP_CONTENT_RE = re.compile(
    r"<(script|style|iframe|object|embed|form|input|button|textarea|select|link|meta)"
    r"[\s\S]*?</\1>",
    re.IGNORECASE,
)

_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "b", "i", "u",
    "ul", "ol", "li",
    "a",
    "code", "pre",
    "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
    "hr",
}
_ALLOWED_ATTRS = {"a": ["href", "title"]}


@dataclass(frozen=True)
class RenderedEmail:
    html: str
    plaintext: str


def render(body_markdown: str, tenant_name: str, tenants_root: Path) -> RenderedEmail:
    tenant_dir = tenants_root / tenant_name
    cfg = load_tenant_config(tenant_dir)

    env = Environment(undefined=StrictUndefined, autoescape=False)

    body_html = md_lib.markdown(body_markdown, extensions=["extra"])
    body_html = _STRIP_CONTENT_RE.sub("", body_html)
    body_html = bleach.clean(body_html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, strip=True)

    sig_template = env.from_string((tenant_dir / "signature.html").read_text())
    signature_html = sig_template.render(
        display_name=cfg.display_name,
        brand_color=cfg.brand_color,
        website=cfg.website,
        address=cfg.address,
        phone=cfg.phone,
        email=cfg.email,
    )

    page_template = env.from_string((tenant_dir / "email_template.html").read_text())
    html = page_template.render(body_html=body_html, signature_html=signature_html)

    return RenderedEmail(html=html, plaintext=body_markdown)
