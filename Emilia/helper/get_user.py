


async def get_user_id(message):
    if message.reply_to_message and not message.forward_from:
        if len(message.text.split()) >= 2:
            args = message.text.split()[1]
            if args.startswith("@") or (
                args.isdigit() and (len(args) >= 5 or len(args) <= 15)
            ):
                user_info = await message._client.get_users(user_ids=args)
                return user_info
            else:
                user_info = message.reply_to_message.from_user
                return user_info
        else:
            user_info = message.reply_to_message.from_user
            return user_info

    elif message.forward_from:
        user_info = message.forward_from
        return user_info

    elif not (message.reply_to_message or message.forward_from):
        if not (len(message.text.split()) >= 2):
            await message.reply(
                "I don't know who you're talking about, you're going to need to specify a user...!"
            )
            return False

        user = message.text.split()[1]
        user_info = await message._client.get_users(user_ids=user)

        return user_info


async def get_text(message):
    if message.reply_to_message:
        if len(message.text.split()) >= 2 and (
            message.text.split()[1].startswith("@")
            or (
                message.text.split()[1].isdigit()
                and (
                    len(message.text.split()[1]) >= 5
                    or len(message.text.split()[1]) <= 15
                )
            )
        ):
            text = " ".join(message.text.split()[2:])
        else:
            text = " ".join(message.text.split()[1:])

    elif not message.reply_to_message:
        text = " ".join(message.text.split()[2:])

    return text
