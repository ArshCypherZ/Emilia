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
        return (await message._client.get_users(text)).id
    elif entity.type == MessageEntityType.URL:
        return (await message._client.get_users(text.split("/")[-1])).id
    elif entity.type == MessageEntityType.TEXT_LINK:
        if entity.url.startswith("tg://user?id="):
            return int(entity.url.split("=")[1])
    if entity.type == MessageEntityType.TEXT_MENTION:
        return entity.user.id
    return None


async def extract_user_and_reason(message, sender_chat=False):
    args = message.text.strip().split()
    text = message.text
    user = None
    reason = None
    
    # Reply case
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

    # Entity based extraction (Text Mention / Link)
    # Check entities skipping the first one (command)
    entities = message.entities
    target_entity = None
    if entities:
        for ent in entities:
             if ent.offset > 0:
                 target_entity = ent
                 break
    
    if target_entity:
        # Extract user from entity
        user_id = None
        if target_entity.type == MessageEntityType.TEXT_MENTION:
            user_id = target_entity.user.id
        elif target_entity.type == MessageEntityType.MENTION:
            # We need to extract the text to resolve it? extract_userid does get_users(text)
            # Text coverage:
            e_text = text[target_entity.offset : target_entity.offset + target_entity.length]
            user_id = (await message._client.get_users(e_text)).id
        elif target_entity.type == MessageEntityType.TEXT_LINK:
             if target_entity.url.startswith("tg://user?id="):
                 user_id = int(target_entity.url.split("=")[1])
        
        if user_id:
             # Extract reason
             end_offset = target_entity.offset + target_entity.length
             reason = text[end_offset:].strip() or None
             return user_id, reason

    # if not reply to a message and no reason is given
    if len(args) == 2:
        user = text.split(None, 1)[1]
        return await extract_userid(message, user), None

    # if reason is given
    if len(args) > 2:
        user, reason = text.split(None, 2)[1:]
        return await extract_userid(message, user), reason

    return user, reason
