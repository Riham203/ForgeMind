from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

# Support pgvector when installed and connected to PostgreSQL,
# with seamless TypeDecorator fallback for SQLite local environments.
try:
    from pgvector.sqlalchemy import Vector
except (ImportError, Exception):
    from sqlalchemy.types import Text, TypeDecorator

    class Vector(TypeDecorator):
        impl = Text
        cache_ok = True

        def __init__(self, dim: int = 1536, *args, **kwargs):
            self.dim = dim
            super().__init__(*args, **kwargs)

        def process_bind_param(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return json.dumps(list(value))

        def process_result_value(self, value, dialect):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            try:
                return json.loads(value)
            except Exception:
                return []


def uuid_str() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    ADMIN = "ADMIN"
    ENGINEER = "ENGINEER"
    ARTISAN = "ARTISAN"
    VIEWER = "VIEWER"


class AccountStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AuthProvider(str, enum.Enum):
    LOCAL = "manual"
    MANUAL = "manual"
    GOOGLE = "google"
    APPLE = "apple"
    MICROSOFT = "microsoft"


class BreakdownStatus(str, enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    COMPLETED = "Completed"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=uuid_str)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # Nullable for OAuth users
    auth_provider = db.Column(db.String(20), default="manual")  # 'manual', 'google', 'apple', 'microsoft'
    role = db.Column(db.String(20), default="ARTISAN")  # ADMIN, ENGINEER, ARTISAN, VIEWER
    status = db.Column(db.String(20), default="PENDING")  # PENDING, APPROVED, REJECTED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return str(self.role or "").upper() == "ADMIN"

    def can_admin(self) -> bool:
        return self.is_admin

    @property
    def is_approved(self) -> bool:
        return str(self.status or "").upper() == "APPROVED"

    @property
    def account_status(self) -> str:
        return self.status

    @account_status.setter
    def account_status(self, val: str) -> None:
        self.status = val

    def can_write(self) -> bool:
        return str(self.role or "").upper() in {"ADMIN", "ENGINEER", "ARTISAN"}

    def initials(self) -> str:
        cleaned = (self.name or "").replace("Mr.", "").replace("Mrs.", "").replace("Dr.", "")
        parts = [p for p in cleaned.split() if p]
        if not parts:
            return "FM"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class BreakdownRecord(db.Model):
    __tablename__ = "breakdown_records"

    id = db.Column(db.String(36), primary_key=True, default=uuid_str)
    code = db.Column(db.String(50), unique=True, nullable=False)  # e.g., R00000053897
    received_on = db.Column(db.DateTime, default=datetime.utcnow)
    completed_on = db.Column(db.DateTime, nullable=True)

    asset_code = db.Column(db.String(50), index=True, nullable=False)  # e.g., 21-CV-1013
    asset_description = db.Column(db.String(255), nullable=False)  # e.g., Proportioning Incline Conveyor
    description = db.Column(db.Text, nullable=False)  # Problem summary

    staff_member = db.Column(db.String(100), nullable=False)  # Technician/Artisan name
    status = db.Column(db.String(20), default="Approved")  # Approved, Completed, Pending
    work_performed = db.Column(db.Text, nullable=True)  # Corrective action
    notes = db.Column(db.Text, nullable=True)

    # RAG Vector Embedding field (1536 dims for OpenAI embeddings)
    embedding = db.Column(Vector(1536), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Additional operational fields for equipment analytics
    category = db.Column(db.String(100), default="Mechanical")
    downtime_hours = db.Column(db.Float, default=0.0)
    root_cause = db.Column(db.Text, nullable=True)
    corrective_action = db.Column(db.Text, nullable=True)
    lesson_learned = db.Column(db.Text, nullable=True)
    photo_urls = db.Column(db.JSON, default=list)

    def to_chunk(self) -> str:
        received = self.received_on.strftime("%Y-%m-%d %H:%M") if self.received_on else "N/A"
        completed = self.completed_on.strftime("%Y-%m-%d %H:%M") if self.completed_on else "Open / In Progress"
        return (
            f"[Record Code: {self.code}] | Asset Code: {self.asset_code} | Asset Description: {self.asset_description}\n"
            f"Received On: {received} | Completed On: {completed} | Staff Member: {self.staff_member}\n"
            f"Status: {self.status} | Category: {self.category or 'General'}\n"
            f"Problem Description: {self.description}\n"
            f"Work Performed: {self.work_performed or 'None recorded'}\n"
            f"Notes: {self.notes or 'None'}\n"
            f"Root Cause: {self.root_cause or 'Not recorded'}\n"
            f"Corrective Action: {self.corrective_action or 'Not recorded'}\n"
            f"Lesson Learned: {self.lesson_learned or 'Not recorded'}"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "receivedOn": self.received_on.strftime("%Y-%m-%d %H:%M") if self.received_on else "",
            "completedOn": self.completed_on.strftime("%Y-%m-%d %H:%M") if self.completed_on else "",
            "assetCode": self.asset_code,
            "assetDescription": self.asset_description,
            "description": self.description,
            "staffMember": self.staff_member,
            "status": self.status,
            "workPerformed": self.work_performed or "",
            "notes": self.notes or "",
            "category": self.category or "Mechanical",
            "downtimeHours": float(self.downtime_hours or 0.0),
            "rootCause": self.root_cause or "",
            "correctiveAction": self.corrective_action or "",
            "lessonLearned": self.lesson_learned or "",
            "photoUrls": self.photo_urls or [],
            "createdAt": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else "",
            # UI aliases
            "problem": self.description,
            "assetName": self.asset_description,
            "hasEmbedding": bool(self.embedding),
        }


# Alias for backward compatibility
KnowledgeRecord = BreakdownRecord


class Asset(db.Model):
    __tablename__ = "assets"

    id = db.Column(db.String(36), primary_key=True, default=uuid_str)
    asset_code = db.Column(db.String(50), unique=True, nullable=False)
    asset_name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    area = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.String(36), primary_key=True, default=uuid_str)
    title = db.Column(db.String(200), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
