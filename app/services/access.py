from __future__ import annotations

from app.config import Settings
from app.db.repositories import Repository


def is_superadmin(repo: Repository, user_id: int, settings: Settings) -> bool:
    return repo.is_superadmin(user_id=user_id, bootstrap_superadmins=set(settings.superadmin_ids))


def is_any_admin(repo: Repository, user_id: int, settings: Settings) -> bool:
    return repo.is_any_admin(user_id=user_id, bootstrap_superadmins=set(settings.superadmin_ids))


def can_manage_board(repo: Repository, user_id: int, board_id: int | None, settings: Settings) -> bool:
    return repo.is_board_admin(
        user_id=user_id,
        board_id=board_id,
        bootstrap_superadmins=set(settings.superadmin_ids),
    )
