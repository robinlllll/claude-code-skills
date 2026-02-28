"""Lightweight email sender for analysis delivery. Best-effort, never raises."""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv(Path.home() / "Screenshots" / ".env")

EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "") or EMAIL_USER
EMAIL_DEFAULT_RECIPIENTS = os.environ.get("EMAIL_DEFAULT_RECIPIENTS", "")
EMAIL_SMTP_HOST = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "587"))


def _strip_frontmatter(md: str) -> str:
    """Remove YAML frontmatter (---...---) from markdown."""
    if md.startswith("---"):
        end = md.find("---", 3)
        if end != -1:
            return md[end + 3 :].lstrip("\n")
    return md


def _md_to_html(md: str) -> str:
    """Convert markdown to email-safe HTML with inline CSS."""
    md = _strip_frontmatter(md)
    try:
        import markdown

        html_body = markdown.markdown(md, extensions=["tables", "fenced_code", "nl2br"])
    except ImportError:
        # Fallback: wrap in <pre> if markdown package unavailable
        html_body = f"<pre>{md}</pre>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
             max-width: 800px; margin: 0 auto; padding: 20px; color: #1a1a1a; line-height: 1.6;">
<style>
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
  pre {{ background: #f5f5f5; padding: 12px; border-radius: 6px; overflow-x: auto; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: 8px; }}
  h2 {{ border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 24px; }}
  blockquote {{ border-left: 3px solid #ccc; margin: 12px 0; padding: 8px 16px; color: #555; }}
</style>
{html_body}
<hr style="margin-top: 40px; border: none; border-top: 1px solid #ddd;">
<p style="color: #999; font-size: 0.85em;">Sent from Robin's analysis pipeline</p>
</body></html>"""


def _parse_recipients(recipients: Optional[str] = None) -> list[str]:
    """Parse comma-separated recipients, falling back to default."""
    raw = recipients or EMAIL_DEFAULT_RECIPIENTS
    if not raw:
        return []
    return [r.strip() for r in raw.split(",") if r.strip()]


def send_email(
    subject: str,
    md_content: str,
    recipients: Optional[str] = None,
    attachments: Optional[list[str]] = None,
) -> bool:
    """Send an email with markdown content converted to HTML.

    Args:
        subject: Email subject line
        md_content: Markdown text (frontmatter auto-stripped)
        recipients: Comma-separated emails (falls back to EMAIL_DEFAULT_RECIPIENTS)
        attachments: List of file paths to attach

    Returns:
        True if sent successfully, False otherwise. Never raises.
    """
    if not EMAIL_USER or not EMAIL_APP_PASSWORD:
        return False

    to_addrs = _parse_recipients(recipients)
    if not to_addrs:
        return False

    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(to_addrs)
        msg["Subject"] = subject

        # HTML body from markdown
        html = _md_to_html(md_content)
        msg.attach(MIMEText(html, "html", "utf-8"))

        # Attachments
        for path_str in attachments or []:
            path = Path(path_str)
            if not path.exists():
                continue
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition", f'attachment; filename="{path.name}"'
            )
            msg.attach(part)

        with smtplib.SMTP(EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, to_addrs, msg.as_string())

        return True
    except Exception:
        return False


def send_analysis_email(
    analysis_type: str,
    title: str,
    md_content: str,
    obsidian_path: Optional[str] = None,
    recipients: Optional[str] = None,
    attachments: Optional[list[str]] = None,
) -> bool:
    """Convenience wrapper for analysis emails.

    Args:
        analysis_type: e.g. "13F", "Earnings", "Peer Comparison"
        title: e.g. "Berkshire Hathaway 2025-Q3 Gemini+Grok"
        md_content: Full analysis markdown
        obsidian_path: Path to .md file in vault (auto-attached)
        recipients: Override default recipients
        attachments: Additional file paths to attach

    Returns:
        True if sent, False otherwise. Never raises.
    """
    subject = f"[{analysis_type}] {title}"
    all_attachments = list(attachments or [])
    if obsidian_path and Path(obsidian_path).exists():
        all_attachments.append(obsidian_path)

    return send_email(subject, md_content, recipients, all_attachments)
