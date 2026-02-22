from __future__ import annotations

from sqlmodel import SQLModel, Session, create_engine

from app.db.repositories import Repository


def make_repo() -> Repository:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    return Repository(session)


def test_create_board_slug_is_unique() -> None:
    repo = make_repo()
    first = repo.create_board("General Board", "@board1", 120, 300)
    second = repo.create_board("General Board", "@board2", 120, 300)

    assert first.slug == "general-board"
    assert second.slug.startswith("general-board-")
    assert first.slug != second.slug


def test_selection_and_membership() -> None:
    repo = make_repo()
    repo.sync_user(100, "user", "First", "Last")
    board = repo.create_board("Board", "@board", 120, 300)

    repo.set_user_selected_board(100, board.id)
    selection = repo.get_user_selection(100)
    membership = repo.ensure_membership(100, board.id)

    assert selection is not None
    assert selection.board_id == board.id
    assert membership.is_blocked is False


def test_admin_scope_checks() -> None:
    repo = make_repo()
    repo.sync_user(1, "super", "S", None)
    repo.sync_user(2, "boardadmin", "B", None)
    board_a = repo.create_board("A", "@a", 120, 300)
    board_b = repo.create_board("B", "@b", 120, 300)

    repo.grant_board_admin(2, board_a.id)

    assert repo.is_superadmin(1, {1}) is True
    assert repo.is_board_admin(1, board_a.id, {1}) is True
    assert repo.is_board_admin(2, board_a.id, set()) is True
    assert repo.is_board_admin(2, board_b.id, set()) is False


def test_single_active_post_archive_flow() -> None:
    repo = make_repo()
    repo.sync_user(10, "u", "U", None)
    board = repo.create_board("Board", "@board", 120, 300)

    first = repo.create_post(10, board.id, "first", 111)
    active = repo.get_active_post(10, board.id)
    assert active is not None
    assert active.id == first.id

    repo.archive_post(first)
    second = repo.create_post(10, board.id, "second", 222)

    active_after = repo.get_active_post(10, board.id)
    assert active_after is not None
    assert active_after.id == second.id
    assert active_after.is_archived is False
