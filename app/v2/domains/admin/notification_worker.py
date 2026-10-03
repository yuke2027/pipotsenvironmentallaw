"""Optional configured channels; in-app notifications are always persistent."""
from typing import Any

import os
import smtplib
from email.message import EmailMessage
from urllib.parse import urlparse

import httpx
from sqlalchemy import and_, or_, select

from app.v2.domains.admin.models import Channel, Delivery, Notification


def validate_channel(kind: str, config: dict[str, Any]) -> None:
    if kind == "webhook":
        parsed = urlparse(config.get("url", ""))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Webhook 必须为不带账号密码的 HTTPS 地址")
    elif kind == "email":
        if not config.get("host") or not config.get("recipient") or not config.get("sender"):
            raise ValueError("邮件通道需配置主机、发件人和收件人")
    else:
        raise ValueError("通道类型应为 email 或 webhook")


def deliver_pending(db: Any, settings: Any, transport: Any = None) -> None:
    with db.transaction() as session:
        channels = session.scalars(select(Channel).where(Channel.enabled.is_(True))).all()
        for channel in channels:
            # Only notifications created after a channel was enabled/created are eligible.
            notifications = session.scalars(select(Notification).outerjoin(Delivery, and_(
                Delivery.notification_id == Notification.id, Delivery.channel_id == channel.id))
                .where(Notification.created_at >= channel.created_at,
                       or_(Delivery.id.is_(None), and_(Delivery.status != "sent", Delivery.attempts < 3)))
                .order_by(Notification.created_at).limit(500)).all()
            for notification in notifications:
                delivery = session.scalar(select(Delivery).where(Delivery.notification_id == notification.id, Delivery.channel_id == channel.id))
                if delivery is None:
                    delivery = Delivery(notification_id=notification.id, channel_id=channel.id, attempts=0)
                    session.add(delivery)
                    session.flush()
                if delivery.status == "sent" or delivery.attempts >= 3: continue
                delivery.attempts += 1
                try:
                    validate_channel(channel.kind, channel.config)
                    if transport:
                        transport(channel, notification)
                    elif channel.kind == "webhook":
                        credential = os.environ.get(channel.credential_ref or "", "")
                        headers = {"Idempotency-Key": delivery.id}
                        if credential: headers["Authorization"] = f"Bearer {credential}"
                        with httpx.Client(timeout=settings.notification_timeout, follow_redirects=False) as client:
                            client.post(channel.config["url"], headers=headers, json={"id": delivery.id, "title": notification.title,
                                "body": notification.body, "href": notification.href}).raise_for_status()
                    else:
                        message = EmailMessage()
                        message["From"], message["To"], message["Subject"] = channel.config["sender"], channel.config["recipient"], notification.title
                        message["Message-ID"] = f"<{delivery.id}@environmental-platform>"
                        message.set_content(notification.body)
                        with smtplib.SMTP(channel.config["host"], channel.config.get("port", 587), timeout=settings.notification_timeout) as smtp:
                            smtp.starttls()
                            if channel.config.get("username"):
                                smtp.login(channel.config["username"], os.environ.get(channel.credential_ref or "", ""))
                            smtp.send_message(message)
                    delivery.status, delivery.error = "sent", None
                except Exception as exc:
                    delivery.status, delivery.error = "failed", f"发送失败（{type(exc).__name__}）"
