from __future__ import annotations

from dataclasses import dataclass, field

from aiogram.types import User as TelegramUser

from app.config import Settings
from app.db.models import Board, User
from app.db.repositories import Repository
from app.services.users import sync_telegram_user


@dataclass
class AdminContext:
    repo: Repository
    settings: Settings
    tg_user: TelegramUser
    _actor: User | None = field(default=None, init=False, repr=False)

    @property
    def bootstrap_superadmins(self) -> set[int]:
        return set(self.settings.superadmin_ids)

    @property
    def actor(self) -> User:
        if self._actor is None:
            self._actor = sync_telegram_user(self.repo, self.tg_user)
        return self._actor


@dataclass
class AdminAccessService:
    context: AdminContext

    def ensure_any_admin(self) -> bool:
        return self.context.repo.is_any_admin(
            user_id=self.context.actor.id,
            bootstrap_superadmins=self.context.bootstrap_superadmins,
        )

    def ensure_superadmin(self) -> bool:
        return self.context.repo.is_superadmin(
            user_id=self.context.actor.id,
            bootstrap_superadmins=self.context.bootstrap_superadmins,
        )

    def can_manage_board(self, board_id: int | None) -> bool:
        return self.context.repo.is_board_admin(
            user_id=self.context.actor.id,
            board_id=board_id,
            bootstrap_superadmins=self.context.bootstrap_superadmins,
        )

    def manageable_boards(self, *, include_archived: bool = False) -> list[Board]:
        return self.context.repo.list_manageable_boards(
            user_id=self.context.actor.id,
            bootstrap_superadmins=self.context.bootstrap_superadmins,
            include_archived=include_archived,
        )

    def active_manageable_boards(self) -> list[Board]:
        return self.manageable_boards(include_archived=False)

    def inactive_manageable_boards(self) -> list[Board]:
        return [board for board in self.manageable_boards(include_archived=True) if not board.is_active]


@dataclass
class AdminBoardService:
    context: AdminContext

    def stats(self) -> dict[str, int]:
        return self.context.repo.stats()

    def get_board(self, board_id: int) -> Board | None:
        return self.context.repo.get_board(board_id)

    def create_board(self, title: str, channel_id: str) -> Board:
        board = self.context.repo.create_board(
            title=title,
            channel_id=channel_id,
            rate_limit_seconds=self.context.settings.default_rate_limit_seconds,
            max_text_length=self.context.settings.default_max_text_length,
        )
        self.context.repo.write_audit(
            actor_user_id=self.context.actor.id,
            action="board_create",
            target_type="board",
            target_id=str(board.id),
            board_id=board.id,
            metadata={"title": board.title, "channel_id": board.channel_id},
        )
        return board

    def archive_board(self, board_id: int) -> Board | None:
        return self._set_board_active(board_id=board_id, is_active=False)

    def activate_board(self, board_id: int) -> Board | None:
        return self._set_board_active(board_id=board_id, is_active=True)

    def update_rate_limit(self, board_id: int, seconds: int) -> Board | None:
        board = self.context.repo.update_board_rate_limit(board_id=board_id, seconds=seconds)
        if board is None:
            return None

        self.context.repo.write_audit(
            actor_user_id=self.context.actor.id,
            action="board_rate_limit_update",
            target_type="board",
            target_id=str(board_id),
            board_id=board_id,
            metadata={"rate_limit_seconds": seconds},
        )
        return board

    def _set_board_active(self, board_id: int, *, is_active: bool) -> Board | None:
        board = self.context.repo.set_board_active(board_id=board_id, is_active=is_active)
        if board is None:
            return None

        self.context.repo.write_audit(
            actor_user_id=self.context.actor.id,
            action="board_activate" if is_active else "board_archive",
            target_type="board",
            target_id=str(board.id),
            board_id=board.id,
        )
        return board


@dataclass
class AdminRoleService:
    context: AdminContext

    def grant_superadmin(self, target_user_id: int) -> None:
        self.context.repo.grant_superadmin(target_user_id)
        self.context.repo.write_audit(
            actor_user_id=self.context.actor.id,
            action="grant_superadmin",
            target_type="user",
            target_id=str(target_user_id),
        )

    def grant_board_admin(self, target_user_id: int, board_id: int) -> Board | None:
        board = self.context.repo.get_board(board_id)
        if board is None:
            return None

        self.context.repo.grant_board_admin(user_id=target_user_id, board_id=board_id)
        self.context.repo.write_audit(
            actor_user_id=self.context.actor.id,
            action="grant_board_admin",
            target_type="user",
            target_id=str(target_user_id),
            board_id=board_id,
        )
        return board

    def revoke_superadmin(self, target_user_id: int) -> None:
        self.context.repo.revoke_superadmin(target_user_id)
        self.context.repo.write_audit(
            actor_user_id=self.context.actor.id,
            action="revoke_superadmin",
            target_type="user",
            target_id=str(target_user_id),
        )

    def revoke_board_admin(self, target_user_id: int, board_id: int) -> None:
        self.context.repo.revoke_board_admin(user_id=target_user_id, board_id=board_id)
        self.context.repo.write_audit(
            actor_user_id=self.context.actor.id,
            action="revoke_board_admin",
            target_type="user",
            target_id=str(target_user_id),
            board_id=board_id,
        )


@dataclass
class AdminModerationService:
    context: AdminContext

    def block_user(self, target_user_id: int, board_id: int) -> Board | None:
        return self._set_user_blocked(target_user_id=target_user_id, board_id=board_id, blocked=True)

    def unblock_user(self, target_user_id: int, board_id: int) -> Board | None:
        return self._set_user_blocked(target_user_id=target_user_id, board_id=board_id, blocked=False)

    def _set_user_blocked(self, target_user_id: int, board_id: int, *, blocked: bool) -> Board | None:
        board = self.context.repo.get_board(board_id)
        if board is None:
            return None

        self.context.repo.sync_user(user_id=target_user_id, username=None, first_name=None, last_name=None)
        self.context.repo.set_membership_blocked(user_id=target_user_id, board_id=board_id, blocked=blocked)
        self.context.repo.write_audit(
            actor_user_id=self.context.actor.id,
            action="block_user" if blocked else "unblock_user",
            target_type="user",
            target_id=str(target_user_id),
            board_id=board_id,
        )
        return board


@dataclass
class AdminServices:
    access: AdminAccessService
    boards: AdminBoardService
    roles: AdminRoleService
    moderation: AdminModerationService
