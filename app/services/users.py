from __future__ import annotations

from aiogram.types import User as TelegramUser

from app.db.models import User
from app.db.repositories import Repository


def sync_telegram_user(repo: Repository, tg_user: TelegramUser) -> User:
    return repo.sync_user(
        user_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
