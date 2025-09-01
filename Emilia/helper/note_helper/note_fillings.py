async def NoteFillings(message, message_text):
    if message is not None and message.from_user:
        user_id = message.from_user.id
        first_name = message.from_user.first_name
        last_name = message.from_user.last_name
        if last_name is None:
            last_name = ""
        full_name = f"{first_name} {last_name}"
        username = (
            message.from_user.username
            if message.from_user.username
            else message.from_user.mention
        )
        mention = message.from_user.mention
        chat_title = message.chat.title

        try:
            FillingText = message_text.format(
                id=user_id,
                first=first_name,
                last=last_name,
                fullname=full_name,
                username=username,
                mention=mention,
                chatname=chat_title,
            )
        except KeyError:
            FillingText = message_text

    else:
        FillingText = message_text

    return FillingText
