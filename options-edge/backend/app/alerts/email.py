"""Gmail-based alerting for Options Edge discovery and exit events."""

from __future__ import annotations

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import get_settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailAlert:
    """Send HTML email alerts via the Gmail API.

    Expects a ``credentials/gmail.json`` file containing OAuth2 credentials
    (token, refresh_token, client_id, client_secret, etc.) generated through
    the Google Cloud Console OAuth flow.

    Usage::

        alert = GmailAlert()
        await alert.send_discovery_results(theses)
    """

    def __init__(self, recipient: str | None = None) -> None:
        settings = get_settings()
        self._credentials_path = settings.GMAIL_CREDENTIALS_PATH
        self._recipient = recipient or "me"
        self._service = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_service(self):
        """Build and return an authorised Gmail API service instance."""
        if self._service is not None:
            return self._service

        creds = Credentials.from_authorized_user_file(self._credentials_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        self._service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._service

    # ------------------------------------------------------------------
    # Email builders
    # ------------------------------------------------------------------

    def _create_message(self, subject: str, html_body: str) -> dict:
        """Build a base64url-encoded Gmail message dict."""
        msg = MIMEMultipart("alternative")
        msg["To"] = self._recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        return {"raw": raw}

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def send_discovery_results(self, theses: Sequence) -> None:
        """Send an email summarising today's discovery results.

        Parameters
        ----------
        theses:
            Sequence of thesis ORM objects or dicts with at minimum
            ``ticker``, ``direction``, ``spread_type``, ``confidence``,
            ``short_strike``, ``long_strike``, ``entry_price``, and ``reasoning``.
        """
        if not theses:
            logger.info("No theses to email -- skipping discovery alert")
            return

        rows = []
        for t in theses:
            ticker = getattr(t, "ticker", t.get("ticker", "?"))
            direction = getattr(t, "direction", t.get("direction", ""))
            spread = getattr(t, "spread_type", t.get("spread_type", ""))
            confidence = getattr(t, "confidence", t.get("confidence", 0))
            short_s = getattr(t, "short_strike", t.get("short_strike", 0))
            long_s = getattr(t, "long_strike", t.get("long_strike", 0))
            entry = getattr(t, "entry_price", t.get("entry_price", 0))
            reasoning = getattr(t, "reasoning", t.get("reasoning", ""))

            rows.append(f"""
            <tr>
                <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">{ticker}</td>
                <td style="padding:8px;border:1px solid #ddd;">{direction}</td>
                <td style="padding:8px;border:1px solid #ddd;">{spread}</td>
                <td style="padding:8px;border:1px solid #ddd;">{short_s}/{long_s}</td>
                <td style="padding:8px;border:1px solid #ddd;">${entry:.2f}</td>
                <td style="padding:8px;border:1px solid #ddd;">{confidence:.0%}</td>
            </tr>
            <tr>
                <td colspan="6" style="padding:8px;border:1px solid #ddd;color:#555;
                    font-size:0.9em;">{reasoning[:200]}...</td>
            </tr>
            """)

        html = f"""
        <html>
        <body style="font-family:Arial,sans-serif;">
            <h2 style="color:#1a73e8;">Options Edge - Discovery Results</h2>
            <p>{len(theses)} new thesis/theses generated today.</p>
            <table style="border-collapse:collapse;width:100%;">
                <thead>
                    <tr style="background:#f0f0f0;">
                        <th style="padding:8px;border:1px solid #ddd;">Ticker</th>
                        <th style="padding:8px;border:1px solid #ddd;">Direction</th>
                        <th style="padding:8px;border:1px solid #ddd;">Spread</th>
                        <th style="padding:8px;border:1px solid #ddd;">Strikes</th>
                        <th style="padding:8px;border:1px solid #ddd;">Entry</th>
                        <th style="padding:8px;border:1px solid #ddd;">Confidence</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows)}
                </tbody>
            </table>
            <p style="color:#888;margin-top:20px;font-size:0.85em;">
                Generated by Options Edge. Review theses in the dashboard before trading.
            </p>
        </body>
        </html>
        """

        subject = f"Options Edge: {len(theses)} New Thesis{'es' if len(theses) != 1 else ''} Found"
        message = self._create_message(subject, html)

        try:
            service = self._get_service()
            service.users().messages().send(userId="me", body=message).execute()
            logger.info("Discovery email sent with %d theses", len(theses))
        except Exception:
            logger.exception("Failed to send discovery email")

    def send_exit_alert(self, thesis, condition: str) -> None:
        """Send an email alerting that a thesis has hit an exit condition.

        Parameters
        ----------
        thesis:
            The thesis ORM object or dict.
        condition:
            One of ``"closed_target"``, ``"closed_stop"``, ``"closed_expiry"``.
        """
        ticker = getattr(thesis, "ticker", thesis.get("ticker", "?"))
        direction = getattr(thesis, "direction", thesis.get("direction", ""))
        spread = getattr(thesis, "spread_type", thesis.get("spread_type", ""))
        entry = getattr(thesis, "entry_price", thesis.get("entry_price", 0))

        condition_labels = {
            "closed_target": ("Profit Target Hit", "#2e7d32", "Your trade reached its profit target."),
            "closed_stop": ("Stop Loss Triggered", "#c62828", "Your trade hit its stop loss."),
            "closed_expiry": ("Expiration Reached", "#f57f17", "Your trade has expired."),
        }
        label, color, description = condition_labels.get(
            condition, ("Exit Triggered", "#333", "An exit condition was met.")
        )

        html = f"""
        <html>
        <body style="font-family:Arial,sans-serif;">
            <h2 style="color:{color};">{label}: {ticker}</h2>
            <p>{description}</p>
            <table style="border-collapse:collapse;">
                <tr>
                    <td style="padding:6px 12px;font-weight:bold;">Ticker</td>
                    <td style="padding:6px 12px;">{ticker}</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;font-weight:bold;">Direction</td>
                    <td style="padding:6px 12px;">{direction}</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;font-weight:bold;">Spread</td>
                    <td style="padding:6px 12px;">{spread}</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;font-weight:bold;">Entry Price</td>
                    <td style="padding:6px 12px;">${entry:.2f}</td>
                </tr>
                <tr>
                    <td style="padding:6px 12px;font-weight:bold;">Exit Reason</td>
                    <td style="padding:6px 12px;">{condition}</td>
                </tr>
            </table>
            <p style="color:#888;margin-top:20px;font-size:0.85em;">
                Review the full trade details in the Options Edge dashboard.
            </p>
        </body>
        </html>
        """

        subject = f"Options Edge Alert: {ticker} - {label}"
        message = self._create_message(subject, html)

        try:
            service = self._get_service()
            service.users().messages().send(userId="me", body=message).execute()
            logger.info("Exit alert sent for %s: %s", ticker, condition)
        except Exception:
            logger.exception("Failed to send exit alert for %s", ticker)
