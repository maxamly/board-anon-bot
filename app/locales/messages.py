from __future__ import annotations

from typing import Any

RU_MESSAGES = {
    "welcome": "Привет! Я публикую анонимные сообщения в доски. Выбери доску ниже.",
    "help": (
        "Отправь текст, и я опубликую его анонимно в выбранной доске.\n"
        "Сменить доску: /boards\n"
        "Админ-панель: /admin"
    ),
    "no_board_selected": "Сначала выбери доску через кнопки ниже.",
    "board_selected": "Выбрана доска: <b>{title}</b>",
    "board_not_found": "Доска не найдена или недоступна.",
    "board_inactive": "Эта доска сейчас не активна.",
    "too_often": "Слишком часто. Между постами должно пройти минимум {seconds} сек.",
    "user_blocked": "Вы не можете публиковать в этой доске. Обратитесь к администратору.",
    "post_too_long": "Сообщение слишком длинное. Максимум: {limit} символов.",
    "publish_success": "Сообщение опубликовано в «{title}».",
    "publish_error": "Не удалось отправить сообщение в канал. Попробуйте позже.",
    "unknown_command": "Не понял команду. Используй /help.",
    "admin_denied": "Недостаточно прав для этого действия.",
    "admin_panel": "Админ-панель. Выберите раздел:",
    "admin_boards": "Список досок:",
    "admin_no_boards": "Пока нет досок. Создайте через /board_create.",
    "admin_board_details": (
        "<b>{title}</b>\n"
        "ID: <code>{board_id}</code>\n"
        "Канал: <code>{channel_id}</code>\n"
        "Slug: <code>{slug}</code>\n"
        "Статус: {status}\n"
        "Лимит: {rate_limit} сек"
    ),
    "admin_enter_board_title": "Введите название новой доски.",
    "admin_enter_board_channel": "Введите channel id или @channel_username.",
    "admin_board_created": "Доска создана: <b>{title}</b> (ID {board_id}).",
    "admin_board_archived": "Доска «{title}» архивирована.",
    "admin_board_activated": "Доска «{title}» активирована.",
    "admin_enter_user_id": "Введите Telegram user_id.",
    "admin_role_choose": "Выберите уровень доступа для user_id={user_id}.",
    "admin_role_granted": "Права выданы.",
    "admin_role_removed": "Права сняты.",
    "admin_user_blocked": "Пользователь {user_id} заблокирован в доске «{title}».",
    "admin_user_unblocked": "Пользователь {user_id} разблокирован в доске «{title}».",
    "admin_rate_limit_choose_board": "Выберите доску для изменения лимита.",
    "admin_rate_limit_enter_seconds": "Введите новый лимит в секундах (например 120).",
    "admin_rate_limit_updated": "Для доски «{title}» лимит установлен: {seconds} сек.",
    "admin_stats": (
        "<b>Статистика</b>\n"
        "Пользователей: {users}\n"
        "Досок всего: {boards_total}\n"
        "Досок активных: {boards_active}\n"
        "Постов всего: {posts_total}\n"
        "Активных постов: {posts_active}"
    ),
    "invalid_user_id": "Некорректный user_id. Нужен только числовой ID.",
    "invalid_number": "Некорректное число.",
    "action_cancelled": "Действие отменено.",
}

LOCALES = {"ru": RU_MESSAGES}


def t(key: str, locale: str = "ru", **kwargs: Any) -> str:
    messages = LOCALES.get(locale, RU_MESSAGES)
    template = messages.get(key, key)
    return template.format(**kwargs)
