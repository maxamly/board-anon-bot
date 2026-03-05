from __future__ import annotations

from aiogram.types import User as TelegramUser
from sqlmodel import SQLModel, Session, create_engine

from app.config import Settings
from app.db.repositories import Repository
from app.services.admin import AdminAccessService, AdminBoardService, AdminContext, AdminModerationService, AdminRoleService
from app.services.user import UserService


def make_repo() -> Repository:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    return Repository(session)


def make_tg_user(user_id: int, username: str = "user") -> TelegramUser:
    return TelegramUser(id=user_id, is_bot=False, first_name="Test", username=username)


def test_user_service_returns_board_picker_view_and_selects_board() -> None:
    repo = make_repo()
    repo.create_board("Alpha", "@alpha", 120, 300)
    target_board = repo.create_board("Beta", "@beta", 120, 300)
    assert target_board.id is not None
    service = UserService(repo=repo, tg_user=make_tg_user(100))

    selected_board = service.select_board(target_board.id)
    board_picker = service.board_picker_view()

    assert selected_board is not None
    assert selected_board.id == target_board.id
    assert [board.title for board in board_picker.boards] == ["Alpha", "Beta"]
    assert board_picker.selected_board_id == target_board.id


def test_admin_access_service_exposes_active_and_inactive_manageable_boards() -> None:
    repo = make_repo()
    repo.sync_user(1, "admin", "A", None)
    active_board = repo.create_board("Active", "@active", 120, 300)
    inactive_board = repo.create_board("Inactive", "@inactive", 120, 300)
    assert inactive_board.id is not None
    assert active_board.id is not None
    repo.set_board_active(inactive_board.id, is_active=False)
    repo.grant_board_admin(1, active_board.id)
    settings = Settings.model_construct(superadmin_ids=[])
    context = AdminContext(repo=repo, settings=settings, tg_user=make_tg_user(1, "admin"))
    service = AdminAccessService(context)

    assert [board.id for board in service.active_manageable_boards()] == [active_board.id]
    assert [board.id for board in service.inactive_manageable_boards()] == []


def test_admin_board_role_and_moderation_services_handle_single_use_cases() -> None:
    repo = make_repo()
    repo.sync_user(1, "admin", "A", None)
    settings = Settings.model_construct(
        superadmin_ids=[],
        default_rate_limit_seconds=120,
        default_max_text_length=300,
    )
    context = AdminContext(repo=repo, settings=settings, tg_user=make_tg_user(1, "admin"))
    boards = AdminBoardService(context)
    roles = AdminRoleService(context)
    moderation = AdminModerationService(context)

    board = boards.create_board("Board", "@board")
    assert board.id is not None

    granted_board = roles.grant_board_admin(target_user_id=2, board_id=board.id)
    blocked_board = moderation.block_user(target_user_id=3, board_id=board.id)
    archived_board = boards.archive_board(board.id)
    assert archived_board is not None
    assert archived_board.is_active is False

    activated_board = boards.activate_board(board.id)
    assert activated_board is not None
    assert activated_board.is_active is True

    updated_board = boards.update_rate_limit(board.id, 90)

    assert granted_board is not None
    assert blocked_board is not None
    assert updated_board is not None
    assert updated_board.rate_limit_seconds == 90
