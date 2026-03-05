from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from aiogram.types import User as TelegramUser

from app.config import get_settings
from app.db.repositories import Repository
from app.db.session import init_db, reset_engine, session_scope
from app.services.posting import publish_text_post


class FakeSentMessage:
    def __init__(self, message_id: int):
        self.message_id = message_id


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.deleted: list[tuple[str, int]] = []

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = True,
    ) -> FakeSentMessage:
        self.sent.append((chat_id, text))
        await asyncio.sleep(0.05)
        return FakeSentMessage(700 + len(self.sent))

    async def delete_message(self, chat_id: str, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))


@pytest.fixture
def configured_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("SUPERADMIN_IDS", "")
    get_settings.cache_clear()
    reset_engine()
    init_db()
    yield
    reset_engine()
    get_settings.cache_clear()


def prepare_board(user_id: int = 100) -> TelegramUser:
    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(user_id, "user", "Test", None)
        board = repo.create_board("Board", "@board", 120, 300)
        repo.set_user_selected_board(user_id, board.id)
        repo.ensure_membership(user_id, board.id)

    return TelegramUser(id=user_id, is_bot=False, first_name="Test", username="user")


@pytest.mark.asyncio
async def test_publish_serializes_same_user_board_requests(configured_db: None) -> None:
    settings = get_settings()
    tg_user = prepare_board()
    bot = FakeBot()

    first, second = await asyncio.gather(
        publish_text_post(bot=bot, tg_user=tg_user, text="first", settings=settings),
        publish_text_post(bot=bot, tg_user=tg_user, text="second", settings=settings),
    )

    assert [first.status, second.status] == ["success", "too_often"]
    assert bot.sent == [("@board", "first")]

    with session_scope() as session:
        repo = Repository(session)
        selected_board = repo.get_selected_board(tg_user.id)
        assert selected_board is not None
        active_post = repo.get_active_post(tg_user.id, selected_board.id)
        stats = repo.stats()

    assert active_post is not None
    assert active_post.text == "first"
    assert stats["posts_total"] == 1
    assert stats["posts_active"] == 1


@pytest.mark.asyncio
async def test_publish_cleans_up_channel_message_when_persist_fails(
    configured_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()
    tg_user = prepare_board()
    bot = FakeBot()

    def broken_create_post(self: Repository, user_id: int, board_id: int | None, text: str, telegram_message_id: int):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(Repository, "create_post", broken_create_post)

    result = await publish_text_post(bot=bot, tg_user=tg_user, text="hello", settings=settings)

    assert result.status == "publish_error"
    assert bot.sent == [("@board", "hello")]
    assert bot.deleted == [("@board", 701)]

    with session_scope() as session:
        repo = Repository(session)
        selected_board = repo.get_selected_board(tg_user.id)
        assert selected_board is not None
        assert repo.get_active_post(tg_user.id, selected_board.id) is None
