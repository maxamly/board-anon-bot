from __future__ import annotations

from typing import Any, Optional, cast

from slugify import slugify
from sqlmodel import Session, select

from app.db.models import (
    AdminRole,
    AuditLog,
    Board,
    BoardMembership,
    Post,
    User,
    UserBoardSelection,
)
from app.utils.time import utc_now

ROLE_SUPERADMIN = "superadmin"
ROLE_BOARD_ADMIN = "board_admin"


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def sync_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> User:
        user = self.session.get(User, user_id)
        if user is None:
            user = User(id=user_id, username=username, first_name=first_name, last_name=last_name)
            self.session.add(user)
            self.session.flush()
            return user

        if username is not None:
            user.username = username
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        self.session.add(user)
        self.session.flush()
        return user

    def get_user(self, user_id: int) -> Optional[User]:
        return self.session.get(User, user_id)

    @staticmethod
    def _require_board_id(board_id: int | None) -> int:
        if board_id is None:
            raise ValueError("board_id must not be None")
        return board_id

    def list_boards(self, include_archived: bool = True) -> list[Board]:
        statement = select(Board)
        statement = statement.order_by(Board.title)
        boards = list(self.session.exec(statement).all())
        if include_archived:
            return boards
        return [board for board in boards if board.is_active]

    def get_board(self, board_id: int | None) -> Optional[Board]:
        if board_id is None:
            return None
        return self.session.get(Board, board_id)

    def create_board(
        self,
        title: str,
        channel_id: str,
        rate_limit_seconds: int,
        max_text_length: int,
    ) -> Board:
        base_slug = slugify(title) or "board"
        slug = base_slug
        counter = 2
        while self.session.exec(select(Board).where(Board.slug == slug)).first() is not None:
            slug = f"{base_slug}-{counter}"
            counter += 1

        board = Board(
            slug=slug,
            title=title,
            channel_id=channel_id,
            rate_limit_seconds=rate_limit_seconds,
            max_text_length=max_text_length,
            is_active=True,
        )
        self.session.add(board)
        self.session.flush()
        return board

    def set_board_active(self, board_id: int | None, is_active: bool) -> Optional[Board]:
        board = self.get_board(board_id)
        if board is None:
            return None
        board.is_active = is_active
        self.session.add(board)
        self.session.flush()
        return board

    def update_board_rate_limit(self, board_id: int | None, seconds: int) -> Optional[Board]:
        board = self.get_board(board_id)
        if board is None:
            return None
        board.rate_limit_seconds = seconds
        self.session.add(board)
        self.session.flush()
        return board

    def set_user_selected_board(self, user_id: int, board_id: int | None) -> UserBoardSelection:
        board_id = self._require_board_id(board_id)
        selection = self.session.get(UserBoardSelection, user_id)
        if selection is None:
            selection = UserBoardSelection(user_id=user_id, board_id=board_id)
        else:
            selection.board_id = board_id
            selection.updated_at = utc_now()
        self.session.add(selection)
        self.session.flush()
        return selection

    def get_user_selection(self, user_id: int) -> Optional[UserBoardSelection]:
        return self.session.get(UserBoardSelection, user_id)

    def get_selected_board(self, user_id: int) -> Optional[Board]:
        selection = self.get_user_selection(user_id)
        if selection is None:
            return None
        return self.get_board(selection.board_id)

    def ensure_membership(self, user_id: int, board_id: int | None) -> BoardMembership:
        board_id = self._require_board_id(board_id)
        statement = select(BoardMembership).where(
            BoardMembership.user_id == user_id,
            BoardMembership.board_id == board_id,
        )
        membership = self.session.exec(statement).first()
        if membership is None:
            membership = BoardMembership(user_id=user_id, board_id=board_id, is_blocked=False)
            self.session.add(membership)
            self.session.flush()
        return membership

    def set_membership_blocked(self, user_id: int, board_id: int | None, blocked: bool) -> BoardMembership:
        membership = self.ensure_membership(user_id=user_id, board_id=board_id)
        membership.is_blocked = blocked
        self.session.add(membership)
        self.session.flush()
        return membership

    def get_active_post(self, user_id: int, board_id: int | None) -> Optional[Post]:
        if board_id is None:
            return None

        statement = select(Post).where(
            Post.user_id == user_id,
            Post.board_id == board_id,
            cast(Any, Post.is_archived).is_(False),
        )
        posts = list(self.session.exec(statement).all())
        if not posts:
            return None
        return max(posts, key=lambda item: item.posted_at)

    def archive_post(self, post: Post) -> Post:
        post.is_archived = True
        post.archived_at = utc_now()
        self.session.add(post)
        self.session.flush()
        return post

    def create_post(self, user_id: int, board_id: int | None, text: str, telegram_message_id: int) -> Post:
        board_id = self._require_board_id(board_id)
        post = Post(user_id=user_id, board_id=board_id, text=text, telegram_message_id=telegram_message_id)
        self.session.add(post)
        self.session.flush()
        return post

    def is_superadmin(self, user_id: int, bootstrap_superadmins: set[int]) -> bool:
        if user_id in bootstrap_superadmins:
            return True
        statement = select(AdminRole).where(
            AdminRole.user_id == user_id,
            AdminRole.role == ROLE_SUPERADMIN,
        )
        return self.session.exec(statement).first() is not None

    def is_board_admin(self, user_id: int, board_id: int | None, bootstrap_superadmins: set[int]) -> bool:
        if board_id is None:
            return False
        if self.is_superadmin(user_id=user_id, bootstrap_superadmins=bootstrap_superadmins):
            return True
        statement = select(AdminRole).where(
            AdminRole.user_id == user_id,
            AdminRole.board_id == board_id,
            AdminRole.role == ROLE_BOARD_ADMIN,
        )
        return self.session.exec(statement).first() is not None

    def is_any_admin(self, user_id: int, bootstrap_superadmins: set[int]) -> bool:
        if self.is_superadmin(user_id=user_id, bootstrap_superadmins=bootstrap_superadmins):
            return True
        statement = select(AdminRole).where(AdminRole.user_id == user_id)
        return self.session.exec(statement).first() is not None

    def grant_superadmin(self, user_id: int) -> AdminRole:
        statement = select(AdminRole).where(
            AdminRole.user_id == user_id,
            AdminRole.role == ROLE_SUPERADMIN,
            cast(Any, AdminRole.board_id).is_(None),
        )
        role = self.session.exec(statement).first()
        if role is not None:
            return role
        role = AdminRole(user_id=user_id, role=ROLE_SUPERADMIN, board_id=None)
        self.session.add(role)
        self.session.flush()
        return role

    def grant_board_admin(self, user_id: int, board_id: int | None) -> AdminRole:
        board_id = self._require_board_id(board_id)
        statement = select(AdminRole).where(
            AdminRole.user_id == user_id,
            AdminRole.board_id == board_id,
            AdminRole.role == ROLE_BOARD_ADMIN,
        )
        role = self.session.exec(statement).first()
        if role is not None:
            return role
        role = AdminRole(user_id=user_id, board_id=board_id, role=ROLE_BOARD_ADMIN)
        self.session.add(role)
        self.session.flush()
        return role

    def revoke_superadmin(self, user_id: int) -> int:
        statement = select(AdminRole).where(
            AdminRole.user_id == user_id,
            AdminRole.role == ROLE_SUPERADMIN,
            cast(Any, AdminRole.board_id).is_(None),
        )
        roles = list(self.session.exec(statement).all())
        for role in roles:
            self.session.delete(role)
        self.session.flush()
        return len(roles)

    def revoke_board_admin(self, user_id: int, board_id: int | None) -> int:
        if board_id is None:
            return 0
        statement = select(AdminRole).where(
            AdminRole.user_id == user_id,
            AdminRole.role == ROLE_BOARD_ADMIN,
            AdminRole.board_id == board_id,
        )
        roles = list(self.session.exec(statement).all())
        for role in roles:
            self.session.delete(role)
        self.session.flush()
        return len(roles)

    def write_audit(
        self,
        actor_user_id: int,
        action: str,
        target_type: str,
        target_id: str | None = None,
        board_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        metadata_json = None
        if metadata:
            metadata_json = str(metadata)

        item = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            board_id=board_id,
            metadata_json=metadata_json,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def stats(self) -> dict[str, int]:
        boards = self.list_boards(include_archived=True)
        posts = list(self.session.exec(select(Post)).all())

        return {
            "users": len(self.session.exec(select(User.id)).all()),
            "boards_total": len(boards),
            "boards_active": len([board for board in boards if board.is_active]),
            "posts_total": len(posts),
            "posts_active": len([post for post in posts if not post.is_archived]),
        }
