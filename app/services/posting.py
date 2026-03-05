from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timezone
import logging
from typing import Protocol

from aiogram import Bot
from aiogram.types import User as TelegramUser

from app.config import Settings
from app.db.repositories import Repository
from app.db.session import session_scope
from app.services.users import sync_telegram_user
from app.utils.time import utc_now

logger = logging.getLogger(__name__)
_publish_locks: dict[tuple[int, int], asyncio.Lock] = {}


class PublishBot(Protocol):
    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = True,
    ) -> SentMessage: ...

    async def delete_message(self, chat_id: str, message_id: int) -> None: ...


class SentMessage(Protocol):
    message_id: int


@dataclass
class PostResult:
    status: str
    board_title: str | None = None
    rate_limit_seconds: int | None = None
    max_text_length: int | None = None


def _publish_lock(user_id: int, board_id: int) -> asyncio.Lock:
    key = (user_id, board_id)
    lock = _publish_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _publish_locks[key] = lock
    return lock


async def _delete_published_message(bot: Bot | PublishBot, channel_id: str, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id=channel_id, message_id=message_id)
    except Exception:
        logger.warning(
            "Failed to delete channel post during cleanup",
            extra={"channel_id": channel_id, "message_id": message_id},
        )


async def publish_text_post(bot: Bot | PublishBot, tg_user: TelegramUser, text: str, settings: Settings) -> PostResult:
    bootstrap_superadmins = set(settings.superadmin_ids)

    with session_scope() as session:
        repo = Repository(session)
        user = sync_telegram_user(repo, tg_user)
        selected_board = repo.get_selected_board(user.id)
        if selected_board is None:
            return PostResult(status="no_board")

        board_id = selected_board.id

    if board_id is None:
        return PostResult(status="no_board")

    async with _publish_lock(tg_user.id, board_id):
        with session_scope() as session:
            repo = Repository(session)
            user = sync_telegram_user(repo, tg_user)
            selected_board = repo.get_selected_board(user.id)
            if selected_board is None or selected_board.id != board_id:
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
                posted_at = active_post.posted_at
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                delta = (utc_now() - posted_at).total_seconds()
                if delta < selected_board.rate_limit_seconds:
                    return PostResult(
                        status="too_often",
                        board_title=selected_board.title,
                        rate_limit_seconds=selected_board.rate_limit_seconds,
                    )

            board_title = selected_board.title
            board_channel_id = selected_board.channel_id

        try:
            sent_message = await bot.send_message(
                chat_id=board_channel_id,
                text=text,
                parse_mode=None,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception(
                "Failed to send message to channel",
                extra={"user_id": tg_user.id, "board_id": board_id},
            )
            return PostResult(status="publish_error", board_title=board_title)

        previous_channel_message_id: int | None = None
        try:
            with session_scope() as session:
                repo = Repository(session)
                user = sync_telegram_user(repo, tg_user)
                selected_board = repo.get_selected_board(user.id)
                if selected_board is None or selected_board.id != board_id:
                    await _delete_published_message(bot, board_channel_id, sent_message.message_id)
                    return PostResult(status="no_board")

                if not selected_board.is_active:
                    await _delete_published_message(bot, board_channel_id, sent_message.message_id)
                    return PostResult(status="board_inactive")

                membership = repo.ensure_membership(user_id=user.id, board_id=selected_board.id)
                if user.is_globally_blocked or membership.is_blocked:
                    await _delete_published_message(bot, board_channel_id, sent_message.message_id)
                    return PostResult(status="blocked", board_title=selected_board.title)

                active_post = repo.get_active_post(user_id=user.id, board_id=selected_board.id)
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
        except Exception:
            logger.exception(
                "Failed to persist published message",
                extra={"user_id": tg_user.id, "board_id": board_id, "message_id": sent_message.message_id},
            )
            await _delete_published_message(bot, board_channel_id, sent_message.message_id)
            return PostResult(status="publish_error", board_title=board_title)

        if previous_channel_message_id:
            await _delete_published_message(bot, board_channel_id, previous_channel_message_id)

        return PostResult(status="success", board_title=board_title)
