from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.keyboards.admin import admin_board_actions_keyboard, admin_boards_keyboard, admin_panel_keyboard, board_action_keyboard
from app.keyboards.user import board_picker_keyboard
from app.locales.messages import t
from app.services.scopes import admin_service_scope, user_service_scope
from app.states import RateLimitStates

router = Router(name="callbacks")
settings = get_settings()


def _parse_tail(data: str | None, prefix: str) -> list[str]:
    if data is None:
        return []
    tail = data[len(prefix) :]
    if tail.startswith(":"):
        tail = tail[1:]
    return [part for part in tail.split(":") if part]


def _editable_message(callback: CallbackQuery) -> Message | None:
    if not isinstance(callback.message, Message):
        return None
    return callback.message


async def _safe_edit_text(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as error:
        if "message is not modified" in str(error):
            return
        raise


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "admin:cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer(t("action_cancelled", locale=settings.default_locale), show_alert=False)


@router.callback_query(F.data.startswith("user:select_board:"))
async def user_select_board(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    parts = _parse_tail(callback.data, "user:select_board")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    board_id = int(parts[0])

    with user_service_scope(callback.from_user) as service:
        board = service.select_board(board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        board_picker = service.board_picker_view()

    await callback.answer()
    await _safe_edit_text(message,
        t("board_selected", locale=settings.default_locale, title=board.title),
        reply_markup=board_picker_keyboard(
            board_picker.boards,
            selected_board_id=board_picker.selected_board_id,
        ),
    )


@router.callback_query(F.data == "admin:panel:home")
async def admin_panel_home(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_any_admin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

    await callback.answer()
    await _safe_edit_text(message, 
        t("admin_panel", locale=settings.default_locale),
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data == "admin:panel:boards")
async def admin_panel_boards(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_any_admin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        boards = service.access.manageable_boards(include_archived=True)

    await callback.answer()
    if not boards:
        await _safe_edit_text(message, t("admin_no_boards", locale=settings.default_locale))
        return

    await _safe_edit_text(message, 
        t("admin_boards", locale=settings.default_locale),
        reply_markup=admin_boards_keyboard(boards),
    )


@router.callback_query(F.data == "admin:panel:stats")
async def admin_panel_stats(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_any_admin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        data = service.boards.stats()

    await callback.answer()
    await _safe_edit_text(message, t("admin_stats", locale=settings.default_locale, **data))


@router.callback_query(F.data.startswith("admin:board:"))
async def admin_board_details(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    parts = _parse_tail(callback.data, "admin:board")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    board_id = int(parts[0])

    with admin_service_scope(callback.from_user, settings) as service:
        board = service.boards.get_board(board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        if not service.access.can_manage_board(board.id):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        status = "активна" if board.is_active else "архив"

    await callback.answer()
    await _safe_edit_text(message, 
        t(
            "admin_board_details",
            locale=settings.default_locale,
            title=board.title,
            board_id=board.id,
            channel_id=board.channel_id,
            slug=board.slug,
            status=status,
            rate_limit=board.rate_limit_seconds,
        ),
        reply_markup=admin_board_actions_keyboard(board),
    )


@router.callback_query(F.data.startswith("admin:board_archive:"))
async def admin_board_archive(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    parts = _parse_tail(callback.data, "admin:board_archive")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    board_id = int(parts[0])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = service.boards.archive_board(board_id=board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

    await callback.answer()
    await _safe_edit_text(message, 
        t("admin_board_archived", locale=settings.default_locale, title=board.title),
        reply_markup=admin_board_actions_keyboard(board),
    )


@router.callback_query(F.data.startswith("admin:board_activate:"))
async def admin_board_activate(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    parts = _parse_tail(callback.data, "admin:board_activate")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    board_id = int(parts[0])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = service.boards.activate_board(board_id=board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

    await callback.answer()
    await _safe_edit_text(message, 
        t("admin_board_activated", locale=settings.default_locale, title=board.title),
        reply_markup=admin_board_actions_keyboard(board),
    )


@router.callback_query(F.data.startswith("admin:add_role_super:"))
async def admin_add_role_super(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    parts = _parse_tail(callback.data, "admin:add_role_super")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("invalid_user_id", locale=settings.default_locale), show_alert=True)
        return

    target_user_id = int(parts[0])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        service.roles.grant_superadmin(target_user_id)

    await callback.answer(t("admin_role_granted", locale=settings.default_locale), show_alert=True)


@router.callback_query(F.data.startswith("admin:add_role_board:"))
async def admin_add_role_board_choose(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    parts = _parse_tail(callback.data, "admin:add_role_board")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("invalid_user_id", locale=settings.default_locale), show_alert=True)
        return

    target_user_id = int(parts[0])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        boards = service.access.active_manageable_boards()

    await callback.answer()
    await _safe_edit_text(message, 
        "Выберите доску для назначения админа:",
        reply_markup=board_action_keyboard(
            boards=boards,
            action_prefix="admin:add_role_board_select",
            user_id=target_user_id,
        ),
    )


@router.callback_query(F.data.startswith("admin:add_role_board_select:"))
async def admin_add_role_board_save(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    parts = _parse_tail(callback.data, "admin:add_role_board_select")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    target_user_id = int(parts[0])
    board_id = int(parts[1])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = service.roles.grant_board_admin(target_user_id=target_user_id, board_id=board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

    await callback.answer(t("admin_role_granted", locale=settings.default_locale), show_alert=True)


@router.callback_query(F.data.startswith("admin:remove_role_super:"))
async def admin_remove_role_super(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    parts = _parse_tail(callback.data, "admin:remove_role_super")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("invalid_user_id", locale=settings.default_locale), show_alert=True)
        return

    target_user_id = int(parts[0])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        service.roles.revoke_superadmin(target_user_id)

    await callback.answer(t("admin_role_removed", locale=settings.default_locale), show_alert=True)


@router.callback_query(F.data.startswith("admin:remove_role_board:"))
async def admin_remove_role_board_choose(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    parts = _parse_tail(callback.data, "admin:remove_role_board")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("invalid_user_id", locale=settings.default_locale), show_alert=True)
        return

    target_user_id = int(parts[0])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return
        boards = service.access.manageable_boards(include_archived=True)

    await callback.answer()
    await _safe_edit_text(message, 
        "Выберите доску для снятия прав:",
        reply_markup=board_action_keyboard(
            boards=boards,
            action_prefix="admin:remove_role_board_select",
            user_id=target_user_id,
        ),
    )


@router.callback_query(F.data.startswith("admin:remove_role_board_select:"))
async def admin_remove_role_board_save(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    parts = _parse_tail(callback.data, "admin:remove_role_board_select")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    target_user_id = int(parts[0])
    board_id = int(parts[1])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.ensure_superadmin():
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        service.roles.revoke_board_admin(target_user_id=target_user_id, board_id=board_id)

    await callback.answer(t("admin_role_removed", locale=settings.default_locale), show_alert=True)


@router.callback_query(F.data.startswith("admin:block_user_select:"))
async def admin_block_user(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    parts = _parse_tail(callback.data, "admin:block_user_select")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    target_user_id = int(parts[0])
    board_id = int(parts[1])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.can_manage_board(board_id):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = service.moderation.block_user(target_user_id=target_user_id, board_id=board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

    await callback.answer(
        t(
            "admin_user_blocked",
            locale=settings.default_locale,
            user_id=target_user_id,
            title=board.title,
        ),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("admin:unblock_user_select:"))
async def admin_unblock_user(callback: CallbackQuery) -> None:
    if callback.from_user is None:
        return

    parts = _parse_tail(callback.data, "admin:unblock_user_select")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    target_user_id = int(parts[0])
    board_id = int(parts[1])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.can_manage_board(board_id):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = service.moderation.unblock_user(target_user_id=target_user_id, board_id=board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

    await callback.answer(
        t(
            "admin_user_unblocked",
            locale=settings.default_locale,
            user_id=target_user_id,
            title=board.title,
        ),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("admin:rate_limit_board:"))
async def admin_rate_limit_choose_board(callback: CallbackQuery, state: FSMContext) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    parts = _parse_tail(callback.data, "admin:rate_limit_board")
    if len(parts) != 1 or not parts[0].isdigit():
        await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
        return

    board_id = int(parts[0])

    with admin_service_scope(callback.from_user, settings) as service:
        if not service.access.can_manage_board(board_id):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = service.boards.get_board(board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

    await state.set_state(RateLimitStates.waiting_seconds)
    await state.update_data(rate_limit_board_id=board_id)
    await callback.answer()
    await _safe_edit_text(message, 
        t("admin_rate_limit_enter_seconds", locale=settings.default_locale)
    )
