__mod_name__ = "Bans"

__sub_mod__ = ["Admin"]

__help__ = """
Some people need to be publicly banned; spammers, annoyances, or just trolls.

This module allows you to do that easily, by exposing some common actions, so everyone will see!

**Admin commands**:

• /ban: Ban a user.
• /dban: Ban a user by reply, and delete their message.
• /sban: Silently ban a user, and delete your message.
• /tban: Temporarily ban a user. Example time values: 4m = 4 minutes, 3h = 3 hours, 6d = 6 days, 5w = 5 weeks.
• /unban: Unban a user.
• /unbanall: Unban All Banned Users
• /dnd: Turn it on in a group chat to kick new users who do not have a username. Helpful to prevent unwanted spambots.
• /zombies: To check for deleted accounts in a group chat. To ban them use `/zombies clean`.
• /kickdead: To kick people who are inactive for more than a month.

• /mute: Mute a user.
• /dmute: Mute a user by reply, and delete their message.
• /smute: Silently mute a user, and delete your message.
• /tmute: Temporarily mute a user. Example time values: 4m = 4 minutes, 3h = 3 hours, 6d = 6 days, 5w = 5 weeks.
• /unmute: Unmute a user.
• /unmuteall: Unmute All Muted Users.
Muted users cannot send messages or react to messages until they are unmuted.

• /kick: Kick a user.
• /dkick: Kick a user by reply, and delete their message.
• /skick: Silently kick a user, and delete your message

**Examples**:
• Mute a user for two hours.
-> /tmute @username 2h
"""
