from pyrogram.enums import MessageEntityType

from Emilia import db

db_ = db.users


async def extract_userid(message, text: str):
    """
    NOT TO BE USED OUTSIDE THIS FILE
    """

    def is_int(text: str):
        try:
            int(text)
        except ValueError:
            return False
        return True

    text = text.strip()

    if is_int(text):
        return int(text)

    entities = message.entities
    if len(entities) < 2:
        return (await message._client.get_users(text)).id
    entity = entities[1]
    if entity.type == MessageEntityType.MENTION:
        # using to avoid flooding tg api
        m = await db_.find_one({"user_name": text.replace("@", "")})
        if m and m["user_id"]:
            return m["user_id"]
        return (await message._client.get_users(text)).id
    elif entity.type == MessageEntityType.URL:
        m = await db_.find_one({"user_name": text.split("/")[-1]})
        if m and m["user_id"]:
            return m["user_id"]
        return (await message._client.get_users(text.split("/")[-1])).id
    if entity.type == MessageEntityType.TEXT_MENTION:
        return entity.user.id
    return None


async def extract_user_and_reason(message, sender_chat=False):
    args = message.text.strip().split()
    text = message.text
    user = None
    reason = None
    if message.reply_to_message:
        reply = message.reply_to_message
        # if reply to a message and no reason is given
        if not reply.from_user:
            if (
                reply.sender_chat
                and reply.sender_chat != message.chat.id
                and sender_chat
            ):
                id_ = reply.sender_chat.id
            else:
                return None, None
        else:
            id_ = reply.from_user.id

        if len(args) < 2:
            reason = None
        else:
            reason = text.split(None, 1)[1]
        return id_, reason

    # if not reply to a message and no reason is given
    if len(args) == 2:
        user = text.split(None, 1)[1]
        return await extract_userid(message, user), None

    # if reason is given
    if len(args) > 2:
        user, reason = text.split(None, 2)[1:]
        return await extract_userid(message, user), reason

    return user, reason
