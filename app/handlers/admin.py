from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.config import get_settings
from app.db.repositories import Repository
from app.db.session import session_scope
from app.keyboards.admin import (
    admin_add_role_keyboard,
    admin_panel_keyboard,
    admin_remove_role_keyboard,
    board_action_keyboard,
)
from app.locales.messages import t
from app.services.access import can_manage_board, is_any_admin, is_superadmin
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

    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        allowed = is_any_admin(repo, message.from_user.id, settings)

    if not allowed:
        await message.answer(t("admin_denied", locale=settings.default_locale))
        return False
    return True


async def _ensure_superadmin(message: Message) -> bool:
    if message.from_user is None:
        return False

    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        allowed = is_superadmin(repo, message.from_user.id, settings)

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
    if not await _ensure_any_admin(message):
        return

    with session_scope() as session:
        repo = Repository(session)
        data = repo.stats()

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

    with session_scope() as session:
        repo = Repository(session)
        boards = [board for board in repo.list_boards(include_archived=False) if board.is_active]

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

    with session_scope() as session:
        repo = Repository(session)
        boards = [board for board in repo.list_boards(include_archived=True) if not board.is_active]

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

    with session_scope() as session:
        repo = Repository(session)
        admin_user = repo.sync_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

        if not is_superadmin(repo, admin_user.id, settings):
            await state.clear()
            await message.answer(t("admin_denied", locale=settings.default_locale))
            return

        board = repo.create_board(
            title=title,
            channel_id=channel_id,
            rate_limit_seconds=settings.default_rate_limit_seconds,
            max_text_length=settings.default_max_text_length,
        )
        repo.write_audit(
            actor_user_id=admin_user.id,
            action="board_create",
            target_type="board",
            target_id=str(board.id),
            board_id=board.id,
            metadata={"title": board.title, "channel_id": board.channel_id},
        )
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


def _manageable_boards(repo: Repository, admin_user_id: int) -> list:
    boards = repo.list_boards(include_archived=False)
    return [
        board
        for board in boards
        if can_manage_board(repo, admin_user_id, board.id, settings)
    ]


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

    with session_scope() as session:
        repo = Repository(session)
        boards = _manageable_boards(repo, message.from_user.id)

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

    with session_scope() as session:
        repo = Repository(session)
        boards = _manageable_boards(repo, message.from_user.id)

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

    with session_scope() as session:
        repo = Repository(session)
        boards = _manageable_boards(repo, message.from_user.id)

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

    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

        if not can_manage_board(repo, message.from_user.id, board_id, settings):
            await state.clear()
            await message.answer(t("admin_denied", locale=settings.default_locale))
            return

        board = repo.update_board_rate_limit(board_id=board_id, seconds=seconds)
        if board is None:
            await state.clear()
            await message.answer(t("board_not_found", locale=settings.default_locale))
            return

        repo.write_audit(
            actor_user_id=message.from_user.id,
            action="board_rate_limit_update",
            target_type="board",
            target_id=str(board_id),
            board_id=board_id,
            metadata={"rate_limit_seconds": seconds},
        )

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
