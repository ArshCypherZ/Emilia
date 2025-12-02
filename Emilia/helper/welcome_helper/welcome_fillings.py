import html




async def Welcomefillings(message, message_text, NewUserJson):
    if NewUserJson is not None:
        user_id = NewUserJson.id
        first_name = NewUserJson.first_name
        last_name = NewUserJson.last_name
        if last_name is None:
            last_name = ""
        full_name = f"{first_name} {last_name}"
        username = NewUserJson.username if NewUserJson.username else NewUserJson.mention
        mention = NewUserJson.mention
        chat_title = html.escape(message.chat.title)
        count = (await message._client.get_chat(message.chat.id)).members_count

        if "{id}" in message_text:
            message_text = message_text.replace("{id}", str(user_id))
        if "{first}" in message_text:
            message_text = message_text.replace("{first}", first_name)
        if "{fullname}" in message_text:
            message_text = message_text.replace("{fullname}", full_name)
        if "{username}" in message_text:
            message_text = message_text.replace("{username}", username)
        if "{mention}" in message_text:
            message_text = message_text.replace("{mention}", mention)
        if "{chatname}" in message_text:
            message_text = message_text.replace("{chatname}", chat_title)
        if "{count}" in message_text:
            message_text = message_text.replace("{count}", str(count))

        FillingText = message_text

    else:
        FillingText = message_text

    return FillingText
