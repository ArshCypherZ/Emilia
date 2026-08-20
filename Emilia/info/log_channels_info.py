from Emilia import BOT_NAME

__mod_name__ = "Logging"

__help__ = f"""
> Recent actions are nice, but they don't help you log every action taken by the bot. This is why you need log channels!

> Log channels can help you keep track of exactly what the other admins are doing. Bans, Mutes, warns, notes - everything can be moderated.

> Setting a log channel is done by the following steps:
>  - Add {BOT_NAME} to your channel, as an admin. This is done via the "add administrators" tab.
>  - Send /setlog to your channel.
>  - Forward the /setlog command to the group you wish to be logged.
>  - Congrats! all done :)

**Admin commands:**
• `/logchannel` — Get the name of the current log channel.
• `/setlog` — Set the log channel for the current chat. Only the group owner can use this; anonymous owners will be asked to confirm with a button.
• `/unsetlog` — Unset the log channel for the current chat.
"""
