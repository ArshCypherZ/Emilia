# DONE: Topics

from telethon import functions

import Emilia.strings as strings
from Emilia import telethn as meow
from Emilia.custom_filter import register
from Emilia.functions.admins import can_manage_topics
from Emilia.utils.decorators import *


async def _get_args_text(event):
    """Return the text after the command, or None."""
    try:
        return event.text.split(None, 1)[1].strip()
    except Exception:
        return None


async def _detect_topic_id(event):
    try:
        msg = getattr(event, "message", None) or event
        r = getattr(msg, "reply_to", None)
        if r:
            top_id = getattr(r, "reply_to_top_id", None) or getattr(
                r, "reply_to_msg_id", None
            )
            if top_id:
                return int(top_id)
    except Exception:
        pass

    try:
        if getattr(event, "reply_to_msg_id", None):
            rep = await event.get_reply_message()
            rr = getattr(rep, "reply_to", None)
            if rr:
                top_id = getattr(rr, "reply_to_top_id", None) or getattr(
                    rr, "reply_to_msg_id", None
                )
                if top_id:
                    return int(top_id)
    except Exception:
        pass

    return None


@usage("/newtopic [name]")
@example("/newtopic Games")
@description(
    "This will create a new topic with the given name inside a topic-enabled group."
)
@register(pattern="newtopic")
@anonadmin_checker
@exception
@logging
async def create_topic(event):
    if event.is_private:
        return await event.reply(strings.is_pvt)

    if not await can_manage_topics(event, event.sender_id):
        return

    name = await _get_args_text(event)
    if not name:
        return await usage_string(event, create_topic)

    if event.chat.forum:
        topic = await meow(
            functions.channels.CreateForumTopicRequest(
                channel=event.chat_id, title=name
            )
        )
        result = topic.updates[1].message
        await event.reply(f"Successfully created {name}\nID: {result.id}")
        await meow.send_message(
            event.chat_id,
            f"Congratulations {name} created successfully\nID: {result.id}",
            reply_to=result.id,
        )
        return "NEW_TOPIC", None, None
    else:
        return await event.reply("You can create topics in topics-enabled groups only.")


@usage("/deletetopic [topic id]")
@example("/deletetopic 1234567890")
@description(
    "This will delete the topic with the given ID inside a topic-enabled group. It will not work for general topics."
)
@register(pattern="deletetopic")
@anonadmin_checker
@exception
@logging
async def delete_topic(event):
    if event.is_private:
        return await event.reply(strings.is_pvt)

    if not await can_manage_topics(event, event.sender_id):
        return

    if event.chat.forum:
        text_arg = await _get_args_text(event)
        topic_id = None
        if text_arg:
            try:
                topic_id = int(text_arg)
            except (ValueError, TypeError):
                topic_id = None
        if topic_id is None:
            topic_id = await _detect_topic_id(event)
        if topic_id is None:
            return await usage_string(event, delete_topic)

        await meow(
            functions.channels.DeleteTopicHistoryRequest(
                channel=event.chat_id, top_msg_id=topic_id
            )
        )
        return "DELETE_TOPIC", None, None
    else:
        return await event.reply(
            "You can perform this action in topics-enabled groups only."
        )


@usage("/closetopic [topic id]")
@example("/closetopic 1234567890")
@description(
    "This will close the topic with the given ID inside a topic-enabled group. It will not work for general topics."
)
@register(pattern="closetopic")
@anonadmin_checker
@exception
@logging
async def close_topic(event):
    if event.is_private:
        return await event.reply(strings.is_pvt)

    if not await can_manage_topics(event, event.sender_id):
        return

    if event.chat.forum:
        text_arg = await _get_args_text(event)
        topic_id = None
        if text_arg:
            try:
                topic_id = int(text_arg)
            except (ValueError, TypeError):
                topic_id = None
        if topic_id is None:
            topic_id = await _detect_topic_id(event)
        if topic_id is None:
            return await usage_string(event, close_topic)

        await meow(
            functions.channels.EditForumTopicRequest(
                channel=event.chat_id, topic_id=topic_id, closed=True
            )
        )
        return "CLOSED_TOPIC", None, None
    else:
        return await event.reply(
            "You can perform this action in topics-enabled groups only."
        )


@usage("/opentopic [topic id]")
@example("/opentopic 1234567890")
@description(
    "This will open the topic with the given ID inside a topic-enabled group. It will not work for general topics since they are already opened."
)
@register(pattern="opentopic")
@anonadmin_checker
@exception
@logging
async def open_topic(event):
    if event.is_private:
        return await event.reply(strings.is_pvt)

    if not await can_manage_topics(event, event.sender_id):
        return

    if event.chat.forum:
        text_arg = await _get_args_text(event)
        topic_id = None
        if text_arg:
            try:
                topic_id = int(text_arg)
            except (ValueError, TypeError):
                topic_id = None
        if topic_id is None:
            topic_id = await _detect_topic_id(event)
        if topic_id is None:
            return await usage_string(event, open_topic)

        await meow(
            functions.channels.EditForumTopicRequest(
                channel=event.chat_id, topic_id=topic_id, closed=False
            )
        )
        return "OPENED_TOPIC", None, None
    else:
        return await event.reply(
            "You can perform this action in topics-enabled groups only."
        )


@usage("/renametopic [new name]\nTip: Run inside the topic to auto-detect it")
@example("/renametopic Chit-chat")
@description(
    "Rename the current topic (when used in a topic) or the topic id you reply to."
)
@register(pattern="renametopic")
@exception
@anonadmin_checker
@logging
async def rename_topic(event):
    if event.is_private:
        return await event.reply(strings.is_pvt)

    if not await can_manage_topics(event, event.sender_id):
        return

    new_name = await _get_args_text(event)
    if not new_name:
        return await event.reply("Please provide a new name for the topic.")

    if event.chat.forum:
        topic_id = await _detect_topic_id(event)
        if topic_id is None:
            try:
                if "|" in new_name:
                    parts = [p.strip() for p in new_name.split("|", 1)]
                    if len(parts) == 2:
                        new_name, maybe_id = parts
                        topic_id = int(maybe_id)
            except Exception:
                topic_id = None
        if topic_id is None:
            return await event.reply(
                "Please run this inside the topic you want to rename, or provide an ID."
            )

        result = await meow(
            functions.channels.EditForumTopicRequest(
                channel=event.chat_id, topic_id=topic_id, title=new_name
            )
        )
        if result:
            try:
                topic_name = result.updates[1].message.action.title
            except Exception:
                topic_name = new_name
            await event.reply(f"Successfully renamed the topic to {topic_name}!")
            return "RENAMED_TOPIC", None, None
    else:
        return await event.reply(
            "You can perform this command in topics-enabled groups only."
        )
