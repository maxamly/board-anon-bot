from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Index, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.utils.time import utc_now


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int = Field(primary_key=True)
    username: Optional[str] = Field(default=None, max_length=64)
    first_name: Optional[str] = Field(default=None, max_length=128)
    last_name: Optional[str] = Field(default=None, max_length=128)
    is_globally_blocked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class Board(SQLModel, table=True):
    __tablename__ = "boards"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(sa_column=Column(String(64), nullable=False, unique=True, index=True))
    title: str = Field(sa_column=Column(String(128), nullable=False))
    channel_id: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    is_active: bool = Field(default=True, index=True)
    rate_limit_seconds: int = Field(default=120, nullable=False)
    max_text_length: int = Field(default=300, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class UserBoardSelection(SQLModel, table=True):
    __tablename__ = "user_board_selections"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    board_id: int = Field(foreign_key="boards.id", nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class BoardMembership(SQLModel, table=True):
    __tablename__ = "board_memberships"
    __table_args__ = (UniqueConstraint("user_id", "board_id", name="uq_membership_user_board"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", nullable=False, index=True)
    board_id: int = Field(foreign_key="boards.id", nullable=False, index=True)
    is_blocked: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class AdminRole(SQLModel, table=True):
    __tablename__ = "admin_roles"
    __table_args__ = (UniqueConstraint("user_id", "board_id", "role", name="uq_admin_role_scope"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", nullable=False, index=True)
    board_id: Optional[int] = Field(default=None, foreign_key="boards.id")
    role: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class Post(SQLModel, table=True):
    __tablename__ = "posts"
    __table_args__ = (Index("ix_posts_user_board_active", "user_id", "board_id", "is_archived"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", nullable=False, index=True)
    board_id: int = Field(foreign_key="boards.id", nullable=False, index=True)
    text: str = Field(sa_column=Column(String(4000), nullable=False))
    posted_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    telegram_message_id: Optional[int] = Field(default=None, index=True)
    is_archived: bool = Field(default=False, nullable=False, index=True)
    archived_at: Optional[datetime] = Field(default=None)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    actor_user_id: int = Field(foreign_key="users.id", nullable=False, index=True)
    action: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    target_type: str = Field(sa_column=Column(String(64), nullable=False))
    target_id: Optional[str] = Field(default=None, max_length=128)
    board_id: Optional[int] = Field(default=None, foreign_key="boards.id")
    metadata_json: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
