import uuid
from datetime import datetime
from typing import Optional, Any

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float,
    DateTime, BigInteger, ForeignKey, JSON, ARRAY,
    UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_user_id = Column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    onboarding_complete = Column(Boolean, default=False)

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    tailored_resumes = relationship("TailoredResume", back_populates="user", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("BrowserSession", back_populates="user", cascade="all, delete-orphan")
    credentials = relationship("Credential", back_populates="user", cascade="all, delete-orphan")
    answer_history = relationship("AnswerHistory", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    full_name = Column(String(256))
    email = Column(String(256))
    phone = Column(String(64))
    linkedin_url = Column(String(512))
    github_url = Column(String(512))
    portfolio_url = Column(String(512))
    location = Column(String(256))
    visa_status = Column(String(128))
    work_authorization = Column(JSONB, default=list)  # ["US", "EU"]
    notice_period = Column(String(64))
    salary_min = Column(Integer)
    salary_max = Column(Integer)
    preferred_locations = Column(JSONB, default=list)
    skills = Column(JSONB, default=dict)  # {"python": 5, "react": 3}
    experience = Column(JSONB, default=list)
    education = Column(JSONB, default=list)
    certifications = Column(JSONB, default=list)
    languages = Column(JSONB, default=list)
    summary = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="profile")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    version = Column(Integer, default=1)
    content_json = Column(JSONB, nullable=False)
    latex_source = Column(Text)
    pdf_path = Column(String(512))
    is_base = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="resumes")


class TailoredResume(Base):
    __tablename__ = "tailored_resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    job_description = Column(Text)
    extracted_keywords = Column(JSONB, default=list)
    ats_score = Column(Float)
    content_json = Column(JSONB)
    latex_source = Column(Text)
    pdf_path = Column(String(512))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="tailored_resumes")
    application = relationship("Application", back_populates="tailored_resume")


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    workflow_id = Column(String(256), unique=True, index=True)
    job_url = Column(Text, nullable=False)
    job_title = Column(String(512))
    company = Column(String(256))
    platform = Column(String(64))  # linkedin, greenhouse, lever, etc.
    status = Column(String(64), default="pending")
    # pending | running | paused | waiting_user | completed | failed | escalated
    error_message = Column(Text)
    confirmation_id = Column(String(256))
    applied_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="applications")
    tailored_resume = relationship("TailoredResume", back_populates="application", uselist=False)
    ai_answers = relationship("AIAnswer", back_populates="application", cascade="all, delete-orphan")
    screenshots = relationship("Screenshot", back_populates="application", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="application", cascade="all, delete-orphan")


class BrowserSession(Base):
    __tablename__ = "browser_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    platform = Column(String(64), nullable=False)  # linkedin, indeed, naukri, etc.
    storage_state = Column(Text)  # Encrypted playwright storage state JSON
    cookies_encrypted = Column(Text)
    is_valid = Column(Boolean, default=True)
    last_validated = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_user_platform_session"),
        Index("ix_browser_sessions_user_platform", "user_id", "platform"),
    )

    user = relationship("User", back_populates="sessions")


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    platform = Column(String(64), nullable=False)
    username_encrypted = Column(Text, nullable=False)
    password_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "platform", name="uq_user_platform_credential"),
    )

    user = relationship("User", back_populates="credentials")


class AIAnswer(Base):
    __tablename__ = "ai_answers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"))
    question_text = Column(Text, nullable=False)
    question_type = Column(String(64))  # text, select, radio, checkbox, file
    answer_value = Column(Text)
    confidence = Column(Float)
    classification = Column(String(64))  # deterministic, inferable, risky, impossible
    was_escalated = Column(Boolean, default=False)
    user_provided = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="ai_answers")


class AnswerHistory(Base):
    __tablename__ = "answer_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    question_hash = Column(String(64), index=True)  # SHA256 of normalized question
    question_text = Column(Text)
    answer_value = Column(Text)
    confidence = Column(Float)
    use_count = Column(Integer, default=1)
    last_used = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "question_hash", name="uq_user_question"),
    )

    user = relationship("User", back_populates="answer_history")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(128), nullable=False)
    event_data = Column(JSONB, default=dict)
    ai_provider = Column(String(64))
    ai_model = Column(String(128))
    ai_confidence = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="audit_logs")


class Screenshot(Base):
    __tablename__ = "screenshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"))
    step_name = Column(String(128))
    file_path = Column(String(512))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="screenshots")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    message = Column(Text, nullable=False)
    notification_type = Column(String(64))
    is_read = Column(Boolean, default=False)
    
    # Change the variable name, but keep "metadata" as the first argument
    notification_metadata = Column("metadata", JSONB, default=dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="notifications")
