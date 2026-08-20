__mod_name__ = "Pin"

__help__ = """
> All the pin related commands can be found here; keep your chat up to date on the latest news with a simple pinned message!

**User commands**:
• `/pinned` — Get the current pinned message.

**Admin commands**:

• `/pin` — Pin the message you replied to. Add 'loud' or 'notify' to send a notification to group members.
• `/unpin` — Unpin the current pinned message. If used as a reply, unpins the replied to message.
• `/unpinall` — Unpins all pinned messages.
• `/antichannelpin <yes/no/on/off>` — Don't let telegram auto-pin linked channels. If no arguments are given, shows current setting.
• `/cleanlinked <yes/no/on/off>` — Delete messages sent by the linked channel.

**Note**: When using antichannel pins, make sure to use the /unpin command, instead of doing it manually. Otherwise, the old message will get re-pinned when the channel sends any messages.
"""
