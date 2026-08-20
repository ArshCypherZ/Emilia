__mod_name__ = "Antiflood"

__help__ = """
> You know how sometimes, people join, send 100 messages, and ruin your chat? With antiflood, that happens no more!

> Antiflood allows you to take action on users that send more than x messages in a row. Actions are: ban/mute/kick/tban/tmute

**Admin commands**:

• `/flood` — Get the current antiflood settings
• `/setflood <number/off/no>` — Set the number of messages after which to take action on a user. Set to '0', 'off', or 'no' to disable.
• `/setfloodtimer <count> <duration>` — Set the number of messages and time required for timed antiflood to take action on a user. Set to just 'off' or 'no' to disable.
• `/setfloodmode <action type>` — Choose which action to take on a user who has been flooding. Possible actions: ban/mute/kick/tban/tmute

• `/clearflood <on/off>` — Whether to delete the messages that triggered the flood.

**Examples**:

• Set antiflood to trigger after 7 messages:
-> /setflood 7

• Disable antiflood:
-> /setflood off

• Set timed antiflood to trigger after 10 messages in 30 seconds:
-> /setfloodtimer 10 30s

• Set the antiflood action to mute:
-> /setfloodmode mute

• Set the antiflood action to a 3 day ban:
-> /setfloodmode tban 3d
"""
