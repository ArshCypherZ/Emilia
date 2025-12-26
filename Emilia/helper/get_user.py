


from pyrogram.enums import MessageEntityType

async def get_user_id(message):
    text = message.text or message.caption
    entities = message.entities or message.caption_entities

    if message.reply_to_message and not message.forward_from:
        # Check if there's an argument command (e.g., /promote @user)
        # If so, prioritize the argument. If not, use the replied user.
        # Logic: If text has explicit user mention/id as arg, use it.
        # But existing logic prefer args over reply if args exist.
        
        # Check entities first for arguments
        user_arg = None
        if entities:
            for ent in entities:
                if ent.offset > 0: # Skip command entity if possible
                    if ent.type == MessageEntityType.TEXT_MENTION:
                        return ent.user
                    elif ent.type == MessageEntityType.MENTION:
                        user_arg = text[ent.offset:ent.offset + ent.length]
                    elif ent.type == MessageEntityType.TEXT_LINK:
                         if ent.url.startswith("tg://user?id="):
                             try:
                                 return await message._client.get_users(int(ent.url.split("=")[1]))
                             except:
                                 pass
        
        if user_arg:
             return await message._client.get_users(user_ids=user_arg)
        
        if len(text.split()) >= 2:
             args = text.split()[1]
             # If just an ID or username string without entity (rare but possible)
             if args.startswith("@") or args.isdigit():
                 return await message._client.get_users(user_ids=args)
        
        # Default to reply user
        return message.reply_to_message.from_user

    elif message.forward_from:
        return message.forward_from

    elif not (message.reply_to_message or message.forward_from):
        # Look for entity in command arguments
        if entities:
            for ent in entities:
                if ent.offset > 0: # skip command itself
                     if ent.type == MessageEntityType.TEXT_MENTION:
                        return ent.user
                     elif ent.type == MessageEntityType.TEXT_LINK:
                         if ent.url.startswith("tg://user?id="):
                             try:
                                 return await message._client.get_users(int(ent.url.split("=")[1]))
                             except:
                                 pass
                     elif ent.type == MessageEntityType.MENTION:
                         user_token = text[ent.offset:ent.offset+ent.length]
                         return await message._client.get_users(user_token)

        if len(text.split()) >= 2:
            user = text.split()[1]
            return await message._client.get_users(user_ids=user)
        
        if not (len(text.split()) >= 2):
            await message.reply(
                "I don't know who you're talking about, you're going to need to specify a user...!"
            )
            return False

        return False


async def get_text(message):
    text = message.text or message.caption
    entities = message.entities or message.caption_entities
    
    # Check if there is a command entity + user entity
    target_entity = None
    if entities:
        for ent in entities:
             if ent.offset > 0:
                 target_entity = ent
                 break
    
    if target_entity:
        if target_entity.type in [MessageEntityType.TEXT_MENTION, MessageEntityType.MENTION, MessageEntityType.TEXT_LINK]:
             # If we found a user entity, the reason is everything after it
             end_offset = target_entity.offset + target_entity.length
             reason = text[end_offset:].strip()
             return reason if reason else None

    if message.reply_to_message:
        if len(text.split()) >= 2 and (
            text.split()[1].startswith("@")
            or (
                text.split()[1].isdigit()
                and (
                    len(text.split()[1]) >= 5
                    or len(text.split()[1]) <= 15
                )
            )
        ):
            text = " ".join(text.split()[2:])
        else:
            text = " ".join(text.split()[1:])

    elif not message.reply_to_message:
        text = " ".join(text.split()[2:])
    
    return text
