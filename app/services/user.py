from __future__ import annotations

from dataclasses import dataclass, field

from aiogram.types import User as TelegramUser

from app.db.models import Board, User
from app.db.repositories import Repository
from app.services.users import sync_telegram_user


@dataclass
class BoardPickerView:
    boards: list[Board]
    selected_board_id: int | None


@dataclass
class UserService:
    repo: Repository
    tg_user: TelegramUser
    _user: User | None = field(default=None, init=False, repr=False)

    @property
    def user(self) -> User:
        if self._user is None:
            self._user = sync_telegram_user(self.repo, self.tg_user)
        return self._user

    def board_picker_view(self) -> BoardPickerView:
        selected = self.repo.get_user_selection(self.user.id)
        return BoardPickerView(
            boards=self.repo.list_boards(include_archived=False),
            selected_board_id=selected.board_id if selected else None,
        )

    def select_board(self, board_id: int) -> Board | None:
        board = self.repo.get_board(board_id)
        if board is None or not board.is_active or board.id is None:
            return None

        self.repo.set_user_selected_board(user_id=self.user.id, board_id=board.id)
        self.repo.ensure_membership(user_id=self.user.id, board_id=board.id)
        return board
