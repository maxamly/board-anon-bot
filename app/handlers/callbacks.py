from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.db.repositories import Repository
from app.db.session import session_scope
from app.keyboards.admin import admin_board_actions_keyboard, admin_boards_keyboard, admin_panel_keyboard, board_action_keyboard
from app.keyboards.user import board_picker_keyboard
from app.locales.messages import t
from app.services.access import can_manage_board, is_any_admin, is_superadmin
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

    with session_scope() as session:
        repo = Repository(session)
        user = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        board = repo.get_board(board_id)
        if board is None or not board.is_active:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        repo.set_user_selected_board(user_id=user.id, board_id=board.id)
        repo.ensure_membership(user_id=user.id, board_id=board.id)

        boards = repo.list_boards(include_archived=False)

    await callback.answer()
    await _safe_edit_text(message, 
        t("board_selected", locale=settings.default_locale, title=board.title),
        reply_markup=board_picker_keyboard(boards, selected_board_id=board.id),
    )


@router.callback_query(F.data == "admin:panel:home")
async def admin_panel_home(callback: CallbackQuery) -> None:
    message = _editable_message(callback)
    if callback.from_user is None or message is None:
        return

    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        if not is_any_admin(repo, callback.from_user.id, settings):
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

    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        if not is_any_admin(repo, callback.from_user.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        boards = repo.list_boards(include_archived=True)

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

    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        if not is_any_admin(repo, callback.from_user.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        data = repo.stats()

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

    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        board = repo.get_board(board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        if not can_manage_board(repo, callback.from_user.id, board.id, settings):
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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        if not is_superadmin(repo, actor.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = repo.set_board_active(board_id=board_id, is_active=False)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        repo.write_audit(
            actor_user_id=actor.id,
            action="board_archive",
            target_type="board",
            target_id=str(board.id),
            board_id=board.id,
        )

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        if not is_superadmin(repo, actor.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = repo.set_board_active(board_id=board_id, is_active=True)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        repo.write_audit(
            actor_user_id=actor.id,
            action="board_activate",
            target_type="board",
            target_id=str(board.id),
            board_id=board.id,
        )

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        if not is_superadmin(repo, actor.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        repo.grant_superadmin(target_user_id)
        repo.write_audit(
            actor_user_id=actor.id,
            action="grant_superadmin",
            target_type="user",
            target_id=str(target_user_id),
        )

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        if not is_superadmin(repo, actor.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        boards = repo.list_boards(include_archived=False)

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        if not is_superadmin(repo, actor.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = repo.get_board(board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        repo.grant_board_admin(user_id=target_user_id, board_id=board_id)
        repo.write_audit(
            actor_user_id=actor.id,
            action="grant_board_admin",
            target_type="user",
            target_id=str(target_user_id),
            board_id=board_id,
        )

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        if not is_superadmin(repo, actor.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        repo.revoke_superadmin(target_user_id)
        repo.write_audit(
            actor_user_id=actor.id,
            action="revoke_superadmin",
            target_type="user",
            target_id=str(target_user_id),
        )

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )
        if not is_superadmin(repo, actor.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return
        boards = repo.list_boards(include_archived=True)

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        if not is_superadmin(repo, actor.id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        repo.revoke_board_admin(user_id=target_user_id, board_id=board_id)
        repo.write_audit(
            actor_user_id=actor.id,
            action="revoke_board_admin",
            target_type="user",
            target_id=str(target_user_id),
            board_id=board_id,
        )

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        if not can_manage_board(repo, actor.id, board_id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = repo.get_board(board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        repo.sync_user(user_id=target_user_id, username=None, first_name=None, last_name=None)
        repo.set_membership_blocked(user_id=target_user_id, board_id=board_id, blocked=True)
        repo.write_audit(
            actor_user_id=actor.id,
            action="block_user",
            target_type="user",
            target_id=str(target_user_id),
            board_id=board_id,
        )

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

    with session_scope() as session:
        repo = Repository(session)
        actor = repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        if not can_manage_board(repo, actor.id, board_id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = repo.get_board(board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

        repo.sync_user(user_id=target_user_id, username=None, first_name=None, last_name=None)
        repo.set_membership_blocked(user_id=target_user_id, board_id=board_id, blocked=False)
        repo.write_audit(
            actor_user_id=actor.id,
            action="unblock_user",
            target_type="user",
            target_id=str(target_user_id),
            board_id=board_id,
        )

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

    with session_scope() as session:
        repo = Repository(session)
        repo.sync_user(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        if not can_manage_board(repo, callback.from_user.id, board_id, settings):
            await callback.answer(t("admin_denied", locale=settings.default_locale), show_alert=True)
            return

        board = repo.get_board(board_id)
        if board is None:
            await callback.answer(t("board_not_found", locale=settings.default_locale), show_alert=True)
            return

    await state.set_state(RateLimitStates.waiting_seconds)
    await state.update_data(rate_limit_board_id=board_id)
    await callback.answer()
    await _safe_edit_text(message, 
        t("admin_rate_limit_enter_seconds", locale=settings.default_locale)
    )
