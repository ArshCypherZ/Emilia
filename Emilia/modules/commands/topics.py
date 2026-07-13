# DONE: Topics

from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import Emilia.strings as strings
from Emilia.custom_filter import callbackquery, register
from Emilia.helper.admins import can_manage_topics
from Emilia.utils.decorators import *

ACTION_VERBS = {
    "close": ("Close", "closed"),
    "delete": ("Delete", "deleted"),
    "open": ("Reopen", "reopened"),
}


async def _get_args_text(message):
    """Return the text after the command, or None."""
    try:
        return message.text.split(None, 1)[1].strip()
    except Exception:
        return None


async def _detect_topic_id(message):
    """Best-effort topic id detector when running inside a forum topic.
    Uses message_thread_id / reply_to_top_message_id from the current or
    replied message. Returns int topic_id or None.
    """
    # Try direct attributes on current message
    try:
        top_id = (
            getattr(message, "message_thread_id", None)
            or getattr(message, "reply_to_top_message_id", None)
            or getattr(message, "reply_to_message_id", None)
        )
        if top_id:
            return int(top_id)
    except Exception:
        pass

    # Try via the replied message
    try:
        rep = message.reply_to_message
        if rep:
            top_id = (
                getattr(rep, "message_thread_id", None)
                or getattr(rep, "reply_to_top_message_id", None)
                or getattr(rep, "reply_to_message_id", None)
            )
            if top_id:
                return int(top_id)
    except Exception:
        pass

    return None


async def _send_topic_picker(client, message, action: str):
    """No topic id could be auto-detected - instead of making the admin type
    one, list matching topics as buttons so they just tap one."""
    verb, _ = ACTION_VERBS[action]
    want_closed = action == "open"
    topics = [
        t
        async for t in client.get_forum_topics(message.chat.id)
        if t.id != 1 and t.is_closed == want_closed
    ]
    if not topics:
        state = "closed" if want_closed else "open"
        return await message.reply_text(f"No {state} topics found.")

    buttons = [
        [
            InlineKeyboardButton(
                f"{verb}: {t.title}"[:64], callback_data=f"topicact:{action}:{t.id}"
            )
        ]
        for t in topics
    ]
    await message.reply_text(
        f"Run this inside the topic to auto-detect it next time, or pick one to {verb.lower()}:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _run_topic_action(client, chat_id: int, topic_id: int, action: str):
    if action == "close":
        await client.close_forum_topic(chat_id, topic_id)
    elif action == "delete":
        await client.delete_forum_topic(chat_id, topic_id)
    elif action == "open":
        # kurigram has no reopen_forum_topic; edit with closed=False
        await client.edit_forum_topic(chat_id, topic_id, closed=False)


@usage("/newtopic [name]")
@example("/newtopic Games")
@description(
    "This will create a new topic with the given name inside a topic-enabled group."
)
@register(pattern="newtopic")
@anonadmin_checker
@exception
@log_to_channel
async def create_topic(client, message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(strings.is_pvt)

    user_id = message.from_user.id if message.from_user else None
    if not await can_manage_topics(message, user_id):
        return

    name = await _get_args_text(message)
    if not name:
        return await usage_string(message, create_topic)

    if message.chat.is_forum:
        topic = await client.create_forum_topic(message.chat.id, name)
        await message.reply_text(f"Successfully created {name}\nID: {topic.id}")
        await client.send_message(
            message.chat.id,
            f"Congratulations {name} created successfully\nID: {topic.id}",
            message_thread_id=topic.id,
        )
        return "NEW_TOPIC", None, None
    else:
        return await message.reply_text(strings.NOT_FORUM)


async def _topic_action_command(client, message, action: str, register_result: str):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(strings.is_pvt)

    user_id = message.from_user.id if message.from_user else None
    if not await can_manage_topics(message, user_id):
        return

    if not message.chat.is_forum:
        return await message.reply_text(strings.NOT_FORUM)

    text_arg = await _get_args_text(message)
    topic_id = None
    if text_arg:
        try:
            topic_id = int(text_arg)
        except (ValueError, TypeError):
            topic_id = None
    if topic_id is None:
        topic_id = await _detect_topic_id(message)
    if topic_id is None:
        # No id could be inferred - the ID-based flow is scripting/automation
        # only; the actual UX is picking the topic from a button list.
        await _send_topic_picker(client, message, action)
        return

    await _run_topic_action(client, message.chat.id, topic_id, action)
    return register_result, None, None


@usage("/deletetopic [topic id]\nTip: run inside the topic, or omit the id to pick from a list")
@example("/deletetopic 1234567890")
@description(
    "Delete a topic. Run inside the topic to auto-detect it, or omit the id to choose from a button list. Doesn't work on the General topic."
)
@register(pattern="deletetopic")
@anonadmin_checker
@exception
@log_to_channel
async def delete_topic(client, message):
    return await _topic_action_command(client, message, "delete", "DELETE_TOPIC")


@usage("/closetopic [topic id]\nTip: run inside the topic, or omit the id to pick from a list")
@example("/closetopic 1234567890")
@description(
    "Close a topic. Run inside the topic to auto-detect it, or omit the id to choose from a button list. Doesn't work on the General topic."
)
@register(pattern="closetopic")
@anonadmin_checker
@exception
@log_to_channel
async def close_topic(client, message):
    return await _topic_action_command(client, message, "close", "CLOSED_TOPIC")


@usage("/opentopic [topic id]\nTip: omit the id to pick a closed topic from a list")
@example("/opentopic 1234567890")
@description(
    "Reopen a closed topic. Omit the id to choose from a button list of closed topics. Doesn't work on the General topic, which is always open."
)
@register(pattern="opentopic")
@anonadmin_checker
@exception
@log_to_channel
async def open_topic(client, message):
    return await _topic_action_command(client, message, "open", "OPENED_TOPIC")


@callbackquery(pattern=r"topicact:(close|delete|open):(\d+)")
async def _topic_action_cb(client, query):
    action = query.pattern_match.group(1)
    topic_id = int(query.pattern_match.group(2))
    user_id = query.from_user.id if query.from_user else None
    if not await can_manage_topics(query.message, user_id):
        return await query.answer(strings.NOT_TOPIC, show_alert=True)

    _, past = ACTION_VERBS[action]
    try:
        await _run_topic_action(client, query.message.chat.id, topic_id, action)
    except Exception as exc:
        return await query.answer(f"Failed: {exc}", show_alert=True)
    await query.answer(f"Topic {past}.")
    await query.message.edit_text(f"Topic {topic_id} {past}.")


@usage("/renametopic [new name]\nTip: Run inside the topic to auto-detect it")
@example("/renametopic Chit-chat")
@description(
    "Rename the current topic (when used in a topic) or the topic id you reply to."
)
@register(pattern="renametopic")
@exception
@anonadmin_checker
@log_to_channel
async def rename_topic(client, message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(strings.is_pvt)

    user_id = message.from_user.id if message.from_user else None
    if not await can_manage_topics(message, user_id):
        return

    new_name = await _get_args_text(message)
    if not new_name:
        return await message.reply_text("Please provide a new name for the topic.")

    if message.chat.is_forum:
        topic_id = await _detect_topic_id(message)
        if topic_id is None:
            # Scripting/automation escape hatch: id after name separated
            # by ' | ', e.g. /renametopic New name | 123456
            # (the actual UX for interactive use is the button picker below)
            try:
                if "|" in new_name:
                    parts = [p.strip() for p in new_name.split("|", 1)]
                    if len(parts) == 2:
                        new_name, maybe_id = parts
                        topic_id = int(maybe_id)
            except Exception:
                topic_id = None
        if topic_id is None:
            # Let them pick the topic from a list, then rename via a
            # follow-up reply instead of requiring a manual id lookup.
            topics = [
                t
                async for t in client.get_forum_topics(message.chat.id)
                if t.id != 1
            ]
            if not topics:
                return await message.reply_text("No topics found to rename.")
            buttons = [
                [
                    InlineKeyboardButton(
                        t.title[:64], callback_data=f"topicrenpick:{t.id}"
                    )
                ]
                for t in topics
            ]
            await message.reply_text(
                f"Pick the topic to rename to '{new_name}':",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            _PENDING_RENAMES[(message.chat.id, message.from_user.id)] = new_name
            return

        result = await client.edit_forum_topic(
            message.chat.id, topic_id, title=new_name
        )
        if result:
            # edit_forum_topic returns a bool, so the requested
            # name is used instead of parsing raw updates for the new title.
            await message.reply_text(f"Successfully renamed the topic to {new_name}!")
            return "RENAMED_TOPIC", None, None
        else:
            return await message.reply_text("Failed to rename the topic.")
    else:
        return await message.reply_text(strings.NOT_FORUM)


# Short-lived (process-local) pending rename requests, keyed by
# (chat_id, user_id) -> new_name, consumed by the picker callback below.
_PENDING_RENAMES = {}


@callbackquery(pattern=r"topicrenpick:(\d+)")
async def _topic_rename_pick_cb(client, query):
    user_id = query.from_user.id if query.from_user else None
    if not await can_manage_topics(query.message, user_id):
        return await query.answer(strings.NOT_TOPIC, show_alert=True)

    new_name = _PENDING_RENAMES.pop((query.message.chat.id, user_id), None)
    if new_name is None:
        return await query.answer(
            "This rename request expired, run /renametopic again.", show_alert=True
        )

    topic_id = int(query.pattern_match.group(1))
    try:
        await client.edit_forum_topic(query.message.chat.id, topic_id, title=new_name)
    except Exception as exc:
        return await query.answer(f"Failed to rename: {exc}", show_alert=True)
    await query.answer("Renamed.")
    await query.message.edit_text(f"Topic renamed to '{new_name}'.")


@usage("/topics")
@description(
    "List open topics in this group with quick Close/Delete buttons - no need to remember topic IDs."
)
@register(pattern="topics")
@anonadmin_checker
@exception
async def list_topics(client, message):
    if message.chat.type == ChatType.PRIVATE:
        return await message.reply_text(strings.is_pvt)

    user_id = message.from_user.id if message.from_user else None
    if not await can_manage_topics(message, user_id):
        return

    if not message.chat.is_forum:
        return await message.reply_text(strings.NOT_FORUM)

    open_topics = [
        t
        async for t in client.get_forum_topics(message.chat.id)
        if not t.is_closed and t.id != 1
    ]
    if not open_topics:
        return await message.reply_text("No open topics to manage.")

    buttons = [
        [
            InlineKeyboardButton(f"{t.title}"[:40], callback_data=f"topicnoop:{t.id}"),
            InlineKeyboardButton("Close", callback_data=f"topicact:close:{t.id}"),
            InlineKeyboardButton("Delete", callback_data=f"topicact:delete:{t.id}"),
        ]
        for t in open_topics
    ]
    await message.reply_text(
        "Open topics - tap Close/Delete to manage:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@callbackquery(pattern=r"topicnoop:(.*)")
async def _topic_noop_cb(client, query):
    await query.answer()
