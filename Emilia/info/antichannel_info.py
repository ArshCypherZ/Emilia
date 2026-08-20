__mod_name__ = "Anti-Channel"

__help__ = """
> Anti Channel Mode is a mode to prevent unwanted channel actions.

**Admin Commands**:

• `/antichannelmode <on/yes>` — Enables Anti Channel Mode to ban users who chat using channels.
• `/antichannelmode <off/no>` — Disables Anti Channel Mode.
• `/antichannelpin <yes/no/on/off>` — Don't let telegram auto-pin linked channels. If no arguments are given, shows current setting.
• `/cleanlinked <yes/no/on/off>` — Delete messages sent by the linked channel.

**Note**: When using antichannel pins, make sure to use the /unpin command, instead of doing it manually. Otherwise, the old message will get re-pinned when the channel sends any messages.
"""
