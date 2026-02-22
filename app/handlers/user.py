from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.db.repositories import Repository
from app.db.session import session_scope
from app.keyboards.user import board_picker_keyboard
from app.locales.messages import t
from app.services.posting import publish_text_post

router = Router(name="user")
settings = get_settings()


async def _send_board_picker(message: Message, text: str) -> None:
    if message.from_user is None:
        return

    with session_scope() as session:
        repo = Repository(session)
        user = repo.sync_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        boards = repo.list_boards(include_archived=False)
        selected = repo.get_user_selection(user.id)

    selected_id = selected.board_id if selected else None
    await message.answer(text, reply_markup=board_picker_keyboard(boards, selected_board_id=selected_id))


@router.message(Command("start"))
async def start(message: Message) -> None:
    await _send_board_picker(message, t("welcome", locale=settings.default_locale))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(t("help", locale=settings.default_locale))


@router.message(Command("boards"))
async def boards(message: Message) -> None:
    await _send_board_picker(message, t("no_board_selected", locale=settings.default_locale))


@router.message(F.text)
async def text_messages(message: Message) -> None:
    if message.from_user is None or message.text is None or message.bot is None:
        return

    if message.text.startswith("/"):
        await message.answer(t("unknown_command", locale=settings.default_locale))
        return

    result = await publish_text_post(
        bot=message.bot,
        tg_user=message.from_user,
        text=message.text,
        settings=settings,
    )

    if result.status == "no_board":
        await _send_board_picker(message, t("no_board_selected", locale=settings.default_locale))
        return

    if result.status == "board_inactive":
        await message.answer(t("board_inactive", locale=settings.default_locale))
        return

    if result.status == "blocked":
        await message.answer(t("user_blocked", locale=settings.default_locale))
        return

    if result.status == "too_long":
        await message.answer(
            t(
                "post_too_long",
                locale=settings.default_locale,
                limit=result.max_text_length,
            )
        )
        return

    if result.status == "too_often":
        await message.answer(
            t(
                "too_often",
                locale=settings.default_locale,
                seconds=result.rate_limit_seconds,
            )
        )
        return

    if result.status == "publish_error":
        await message.answer(t("publish_error", locale=settings.default_locale))
        return

    await message.answer(
        t(
            "publish_success",
            locale=settings.default_locale,
            title=result.board_title,
        )
    )
