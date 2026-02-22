from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db.models import Board


def board_picker_keyboard(boards: list[Board], selected_board_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for board in boards:
        marker = "✅ " if selected_board_id == board.id else ""
        row.append(
            InlineKeyboardButton(
                text=f"{marker}{board.title}",
                callback_data=f"user:select_board:{board.id}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    if not rows:
        rows = [[InlineKeyboardButton(text="Нет доступных досок", callback_data="noop")]]

    return InlineKeyboardMarkup(inline_keyboard=rows)
