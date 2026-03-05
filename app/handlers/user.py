from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.keyboards.user import board_picker_keyboard
from app.locales.messages import t
from app.services.posting import publish_text_post
from app.services.scopes import user_service_scope

router = Router(name="user")
settings = get_settings()


async def _send_board_picker(message: Message, text: str) -> None:
    if message.from_user is None:
        return

    with user_service_scope(message.from_user) as service:
        board_picker = service.board_picker_view()

    await message.answer(
        text,
        reply_markup=board_picker_keyboard(
            board_picker.boards,
            selected_board_id=board_picker.selected_board_id,
        ),
    )


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
