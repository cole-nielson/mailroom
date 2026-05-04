from pathlib import Path

from shine_email_assistant.renderer.render import RenderedEmail, render


def _seed_tenant(root: Path) -> Path:
    tdir = root / "example"
    tdir.mkdir()
    (tdir / "config.yaml").write_text(
        "display_name: Example Co\n"
        "brand_color: '#1E3A8A'\n"
        "website: https://example.com\n"
        "address: '123 Main St'\n"
        "phone: '+1-555-0100'\n"
        "reply_signoff: '— Example Co'\n"
    )
    (tdir / "signature.html").write_text(
        "<table><tr><td><strong>{{ display_name }}</strong><br>"
        "{{ phone }} · <a href=\"{{ website }}\" style=\"color:{{ brand_color }}\">{{ website }}</a><br>"
        "{{ address }}</td></tr></table>"
    )
    (tdir / "email_template.html").write_text(
        "<html><body style=\"font-family:-apple-system,Helvetica,Arial,sans-serif;color:#222;line-height:1.5\">"
        "{{ body_html }}<hr style=\"border:none;border-top:1px solid #eee;margin:24px 0\">"
        "{{ signature_html }}</body></html>"
    )
    return tdir


def test_render_wraps_markdown_body_with_signature(tmp_path: Path):
    _seed_tenant(tmp_path)

    body_md = "Thanks for reaching out!\n\nWe can be out on Tuesday.\n\nWarmly, the Example team"
    result = render(body_md, tenant_name="example", tenants_root=tmp_path)

    assert isinstance(result, RenderedEmail)
    assert "<p>Thanks for reaching out!</p>" in result.html
    assert "<p>We can be out on Tuesday.</p>" in result.html
    assert "Example Co" in result.html  # signature rendered
    assert "example.com" in result.html
    assert "#1E3A8A" in result.html  # brand color injected
    # plaintext fallback retains the prose without HTML
    assert "Thanks for reaching out!" in result.plaintext
    assert "<" not in result.plaintext


def test_render_strips_dangerous_html_from_body(tmp_path: Path):
    _seed_tenant(tmp_path)

    body_md = "Welcome!\n\n<script>alert('xss')</script>\n\nHere are details."
    result = render(body_md, tenant_name="example", tenants_root=tmp_path)

    assert "<script>" not in result.html
    assert "alert" not in result.html
    assert "Welcome!" in result.html
    assert "Here are details" in result.html
