from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from aiogram.types import User as TelegramUser

from app.config import Settings, get_settings
from app.db.repositories import Repository
from app.db.session import session_scope
from app.services.admin import (
    AdminAccessService,
    AdminBoardService,
    AdminContext,
    AdminModerationService,
    AdminRoleService,
    AdminServices,
)
from app.services.user import UserService


@contextmanager
def admin_service_scope(tg_user: TelegramUser, settings: Settings | None = None) -> Iterator[AdminServices]:
    active_settings = settings or get_settings()
    with session_scope() as session:
        context = AdminContext(repo=Repository(session), settings=active_settings, tg_user=tg_user)
        yield AdminServices(
            access=AdminAccessService(context),
            boards=AdminBoardService(context),
            roles=AdminRoleService(context),
            moderation=AdminModerationService(context),
        )


@contextmanager
def user_service_scope(tg_user: TelegramUser) -> Iterator[UserService]:
    with session_scope() as session:
        yield UserService(repo=Repository(session), tg_user=tg_user)
