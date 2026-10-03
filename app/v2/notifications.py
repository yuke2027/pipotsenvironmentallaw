"""Compatibility facade for notification delivery."""
from app.v2.domains.admin.notification_worker import deliver_pending, validate_channel

__all__ = ["deliver_pending", "validate_channel"]
