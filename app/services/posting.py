from __future__ import annotations

from dataclasses import dataclass
import logging

from aiogram import Bot
from aiogram.types import User as TelegramUser

from app.config import Settings
from app.db.repositories import Repository
from app.db.session import session_scope
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


@dataclass
class PostResult:
    status: str
    board_title: str | None = None
    rate_limit_seconds: int | None = None
    max_text_length: int | None = None


async def publish_text_post(bot: Bot, tg_user: TelegramUser, text: str, settings: Settings) -> PostResult:
    bootstrap_superadmins = set(settings.superadmin_ids)
    previous_channel_message_id: int | None = None
    board_channel_id: str | None = None

    with session_scope() as session:
        repo = Repository(session)
        user = repo.sync_user(
            user_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )

        selected_board = repo.get_selected_board(user.id)
        if selected_board is None:
            return PostResult(status="no_board")

        if not selected_board.is_active:
            return PostResult(status="board_inactive")

        membership = repo.ensure_membership(user_id=user.id, board_id=selected_board.id)
        if user.is_globally_blocked or membership.is_blocked:
            return PostResult(status="blocked", board_title=selected_board.title)

        if len(text) > selected_board.max_text_length:
            return PostResult(
                status="too_long",
                board_title=selected_board.title,
                max_text_length=selected_board.max_text_length,
            )

        active_post = repo.get_active_post(user_id=user.id, board_id=selected_board.id)
        is_board_admin = repo.is_board_admin(
            user_id=user.id,
            board_id=selected_board.id,
            bootstrap_superadmins=bootstrap_superadmins,
        )

        if active_post and not is_board_admin:
            delta = (utc_now() - active_post.posted_at).total_seconds()
            if delta < selected_board.rate_limit_seconds:
                return PostResult(
                    status="too_often",
                    board_title=selected_board.title,
                    rate_limit_seconds=selected_board.rate_limit_seconds,
                )

        try:
            sent_message = await bot.send_message(
                chat_id=selected_board.channel_id,
                text=text,
                parse_mode=None,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception(
                "Failed to send message to channel",
                extra={"user_id": user.id, "board_id": selected_board.id},
            )
            return PostResult(status="publish_error", board_title=selected_board.title)

        if active_post:
            repo.archive_post(active_post)
            previous_channel_message_id = active_post.telegram_message_id

        repo.create_post(
            user_id=user.id,
            board_id=selected_board.id,
            text=text,
            telegram_message_id=sent_message.message_id,
        )
        repo.write_audit(
            actor_user_id=user.id,
            action="post_publish",
            target_type="post",
            target_id=str(sent_message.message_id),
            board_id=selected_board.id,
        )

        board_channel_id = selected_board.channel_id
        board_title = selected_board.title

    if previous_channel_message_id and board_channel_id:
        try:
            await bot.delete_message(chat_id=board_channel_id, message_id=previous_channel_message_id)
        except Exception:
            logger.warning(
                "Failed to delete previous channel post",
                extra={
                    "channel_id": board_channel_id,
                    "message_id": previous_channel_message_id,
                },
            )

    return PostResult(status="success", board_title=board_title)
