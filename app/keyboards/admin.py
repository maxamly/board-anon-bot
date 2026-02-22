from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Board


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Доски", callback_data="admin:panel:boards")],
            [InlineKeyboardButton(text="Статистика", callback_data="admin:panel:stats")],
        ]
    )


def admin_boards_keyboard(boards: list[Board]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for board in boards:
        status = "🟢" if board.is_active else "⚪"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {board.title}",
                    callback_data=f"admin:board:{board.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:panel:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_board_actions_keyboard(board: Board) -> InlineKeyboardMarkup:
    toggle_button = InlineKeyboardButton(
        text="Архивировать" if board.is_active else "Активировать",
        callback_data=(
            f"admin:board_archive:{board.id}" if board.is_active else f"admin:board_activate:{board.id}"
        ),
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [toggle_button],
            [InlineKeyboardButton(text="Назад к доскам", callback_data="admin:panel:boards")],
        ]
    )


def board_action_keyboard(
    boards: list[Board],
    action_prefix: str,
    user_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for board in boards:
        callback = f"{action_prefix}:{board.id}"
        if user_id is not None:
            callback = f"{action_prefix}:{user_id}:{board.id}"

        rows.append([InlineKeyboardButton(text=board.title, callback_data=callback)])

    rows.append([InlineKeyboardButton(text="Отмена", callback_data="admin:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_add_role_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Глобальный админ",
                    callback_data=f"admin:add_role_super:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Админ конкретной доски",
                    callback_data=f"admin:add_role_board:{user_id}",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:cancel")],
        ]
    )


def admin_remove_role_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Снять глобального админа",
                    callback_data=f"admin:remove_role_super:{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Снять админа доски",
                    callback_data=f"admin:remove_role_board:{user_id}",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:cancel")],
        ]
    )
