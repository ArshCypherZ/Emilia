__mod_name__ = "Warnings"

__help__ = """
> Keep your members in check with warnings; stop them getting out of control!

> If you're looking for automated warnings, go read about the blocklist module.

**Admin commands**:

• `/warn <reason>` — Warn a user.
• `/dwarn <reason>` — Warn a user by reply, and delete their message.
• `/swarn <reason>` — Silently warn a user, and delete your message.
• `/warns` — See your warnings. Users cannot inspect other users' warnings.
• `/warns <user>` — Admins can inspect another user's warnings.
• `/resetwarn` — Reset all of a user's warnings to 0.
• `/resetallwarns` — Delete all the warnings in a chat. All users return to 0 warns.
• `/warnings` — Get the chat's warning settings.
• `/warnmode <ban/mute/kick/tban/tmute>` — View or set the chat's warn mode.
• `/warnlimit <number>` — View or set the number of warnings before users are punished.

**Examples**:

• Warn a user.

-> /warn @user For disobeying the rules
"""
