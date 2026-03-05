from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import get_settings
from app.keyboards.admin import (
    admin_add_role_keyboard,
    admin_panel_keyboard,
    admin_remove_role_keyboard,
    board_action_keyboard,
)
from app.locales.messages import t
from app.services.scopes import admin_service_scope
from app.states import (
    AdminAddStates,
    AdminRemoveStates,
    BoardCreateStates,
    RateLimitStates,
    UserBlockStates,
    UserUnblockStates,
)

router = Router(name="admin")
settings = get_settings()


async def _ensure_any_admin(message: Message) -> bool:
    if message.from_user is None:
        return False

    with admin_service_scope(message.from_user, settings) as service:
        allowed = service.access.ensure_any_admin()

    if not allowed:
        await message.answer(t("admin_denied", locale=settings.default_locale))
        return False
    return True


async def _ensure_superadmin(message: Message) -> bool:
    if message.from_user is None:
        return False

    with admin_service_scope(message.from_user, settings) as service:
        allowed = service.access.ensure_superadmin()

    if not allowed:
        await message.answer(t("admin_denied", locale=settings.default_locale))
        return False
    return True


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not await _ensure_any_admin(message):
        return

    await message.answer(
        t("admin_panel", locale=settings.default_locale),
        reply_markup=admin_panel_keyboard(),
    )


@router.message(Command("stats"))
async def stats_command(message: Message) -> None:
    if message.from_user is None:
        return

    if not await _ensure_any_admin(message):
        return

    with admin_service_scope(message.from_user, settings) as service:
        data = service.boards.stats()

    await message.answer(t("admin_stats", locale=settings.default_locale, **data))


@router.message(Command("board_create"))
async def board_create_start(message: Message, state: FSMContext) -> None:
    if not await _ensure_superadmin(message):
        return

    await state.set_state(BoardCreateStates.waiting_title)
    await message.answer(t("admin_enter_board_title", locale=settings.default_locale))


@router.message(Command("board_archive"))
async def board_archive_command(message: Message) -> None:
    if message.from_user is None:
        return

    if not await _ensure_superadmin(message):
        return

    with admin_service_scope(message.from_user, settings) as service:
        boards = service.access.active_manageable_boards()

    if not boards:
        await message.answer(t("admin_no_boards", locale=settings.default_locale))
        return

    await message.answer(
        "Выберите доску для архивирования:",
        reply_markup=board_action_keyboard(boards=boards, action_prefix="admin:board_archive"),
    )


@router.message(Command("board_activate"))
async def board_activate_command(message: Message) -> None:
    if message.from_user is None:
        return

    if not await _ensure_superadmin(message):
        return

    with admin_service_scope(message.from_user, settings) as service:
        boards = service.access.inactive_manageable_boards()

    if not boards:
        await message.answer(t("admin_no_boards", locale=settings.default_locale))
        return

    await message.answer(
        "Выберите доску для активации:",
        reply_markup=board_action_keyboard(boards=boards, action_prefix="admin:board_activate"),
    )


@router.message(BoardCreateStates.waiting_title, F.text)
async def board_create_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(t("admin_enter_board_title", locale=settings.default_locale))
        return

    await state.update_data(title=title)
    await state.set_state(BoardCreateStates.waiting_channel_id)
    await message.answer(t("admin_enter_board_channel", locale=settings.default_locale))


@router.message(BoardCreateStates.waiting_channel_id, F.text)
async def board_create_channel(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    channel_id = (message.text or "").strip()
    if not channel_id:
        await message.answer(t("admin_enter_board_channel", locale=settings.default_locale))
        return

    data = await state.get_data()
    title = data.get("title", "Новая доска")

    with admin_service_scope(message.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await state.clear()
            await message.answer(t("admin_denied", locale=settings.default_locale))
            return

        board = service.boards.create_board(title=title, channel_id=channel_id)
        board_title = board.title
        board_id = board.id

    await state.clear()
    await message.answer(
        t(
            "admin_board_created",
            locale=settings.default_locale,
            title=board_title,
            board_id=board_id,
        )
    )


@router.message(Command("admin_add"))
async def admin_add_start(message: Message, state: FSMContext) -> None:
    if not await _ensure_superadmin(message):
        return

    await state.set_state(AdminAddStates.waiting_user_id)
    await message.answer(t("admin_enter_user_id", locale=settings.default_locale))


@router.message(AdminAddStates.waiting_user_id, F.text)
async def admin_add_user_id(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(t("invalid_user_id", locale=settings.default_locale))
        return

    user_id = int(raw)
    await state.clear()
    await message.answer(
        t("admin_role_choose", locale=settings.default_locale, user_id=user_id),
        reply_markup=admin_add_role_keyboard(user_id=user_id),
    )


@router.message(Command("admin_remove"))
async def admin_remove_start(message: Message, state: FSMContext) -> None:
    if not await _ensure_superadmin(message):
        return

    await state.set_state(AdminRemoveStates.waiting_user_id)
    await message.answer(t("admin_enter_user_id", locale=settings.default_locale))


@router.message(AdminRemoveStates.waiting_user_id, F.text)
async def admin_remove_user_id(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(t("invalid_user_id", locale=settings.default_locale))
        return

    user_id = int(raw)
    await state.clear()
    await message.answer(
        t("admin_role_choose", locale=settings.default_locale, user_id=user_id),
        reply_markup=admin_remove_role_keyboard(user_id=user_id),
    )


@router.message(Command("block_user"))
async def block_user_start(message: Message, state: FSMContext) -> None:
    if not await _ensure_any_admin(message):
        return

    await state.set_state(UserBlockStates.waiting_user_id)
    await message.answer(t("admin_enter_user_id", locale=settings.default_locale))


@router.message(UserBlockStates.waiting_user_id, F.text)
async def block_user_choose_board(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(t("invalid_user_id", locale=settings.default_locale))
        return

    target_user_id = int(raw)

    with admin_service_scope(message.from_user, settings) as service:
        boards = service.access.manageable_boards()

    await state.clear()
    if not boards:
        await message.answer(t("admin_no_boards", locale=settings.default_locale))
        return

    await message.answer(
        "Выберите доску для блокировки:",
        reply_markup=board_action_keyboard(
            boards=boards,
            action_prefix="admin:block_user_select",
            user_id=target_user_id,
        ),
    )


@router.message(Command("unblock_user"))
async def unblock_user_start(message: Message, state: FSMContext) -> None:
    if not await _ensure_any_admin(message):
        return

    await state.set_state(UserUnblockStates.waiting_user_id)
    await message.answer(t("admin_enter_user_id", locale=settings.default_locale))


@router.message(UserUnblockStates.waiting_user_id, F.text)
async def unblock_user_choose_board(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(t("invalid_user_id", locale=settings.default_locale))
        return

    target_user_id = int(raw)

    with admin_service_scope(message.from_user, settings) as service:
        boards = service.access.manageable_boards()

    await state.clear()
    if not boards:
        await message.answer(t("admin_no_boards", locale=settings.default_locale))
        return

    await message.answer(
        "Выберите доску для разблокировки:",
        reply_markup=board_action_keyboard(
            boards=boards,
            action_prefix="admin:unblock_user_select",
            user_id=target_user_id,
        ),
    )


@router.message(Command("rate_limit_set"))
async def rate_limit_start(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    if not await _ensure_any_admin(message):
        return

    with admin_service_scope(message.from_user, settings) as service:
        boards = service.access.manageable_boards()

    if not boards:
        await message.answer(t("admin_no_boards", locale=settings.default_locale))
        return

    await state.set_state(RateLimitStates.waiting_board)
    await message.answer(
        t("admin_rate_limit_choose_board", locale=settings.default_locale),
        reply_markup=board_action_keyboard(boards=boards, action_prefix="admin:rate_limit_board"),
    )


@router.message(RateLimitStates.waiting_seconds, F.text)
async def rate_limit_save(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(t("invalid_number", locale=settings.default_locale))
        return

    seconds = int(raw)
    if seconds <= 0:
        await message.answer(t("invalid_number", locale=settings.default_locale))
        return

    data = await state.get_data()
    board_id = data.get("rate_limit_board_id")
    if board_id is None:
        await state.clear()
        await message.answer(t("board_not_found", locale=settings.default_locale))
        return

    with admin_service_scope(message.from_user, settings) as service:
        if not service.access.can_manage_board(board_id):
            await state.clear()
            await message.answer(t("admin_denied", locale=settings.default_locale))
            return

        board = service.boards.update_rate_limit(board_id=board_id, seconds=seconds)
        if board is None:
            await state.clear()
            await message.answer(t("board_not_found", locale=settings.default_locale))
            return

    await state.clear()
    await message.answer(
        t(
            "admin_rate_limit_updated",
            locale=settings.default_locale,
            title=board.title,
            seconds=seconds,
        )
    )


@router.message(Command("cancel"))
async def cancel_state(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(t("action_cancelled", locale=settings.default_locale))
