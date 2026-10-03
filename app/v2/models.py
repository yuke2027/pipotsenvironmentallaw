"""Compatibility facade registering all domain ORM models in one shared metadata."""
from app.v2.shared.persistence import Base, Entity, now, uid
from app.v2.domains.auth.models import User, LoginSession, Audit
from app.v2.domains.monitoring.models import City, Station, StationAlias, Observation, Standard, Evaluation, AQIResult
from app.v2.domains.collection.models import SourceFile, SourceAttempt
from app.v2.domains.enforcement.models import Enterprise, EnterpriseRecord, Lead, Inspection, WorkflowEvent, Rectification, Attachment
from app.v2.domains.jobs.models import Job, Outbox
from app.v2.domains.ml.models import ModelArtifact, ModelActivation, DerivedValue
from app.v2.domains.admin.models import Law, Notification, Channel, Delivery

__all__ = ['Base', 'Entity', 'now', 'uid', 'User', 'LoginSession', 'Audit', 'City', 'Station', 'StationAlias', 'Observation', 'Standard', 'Evaluation', 'AQIResult', 'SourceFile', 'SourceAttempt', 'Enterprise', 'EnterpriseRecord', 'Lead', 'Inspection', 'WorkflowEvent', 'Rectification', 'Attachment', 'Job', 'Outbox', 'ModelArtifact', 'ModelActivation', 'DerivedValue', 'Law', 'Notification', 'Channel', 'Delivery']
