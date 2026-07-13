__mod_name__ = "Locks"

__help__ = """
Do stickers annoy you? or want to avoid people sharing links? or pictures? You're in the right place!

The locks module allows you to lock away some common items in the Telegram world; the bot will automatically delete them!

**Admin commands**:

• /lock <item(s)>: Lock one or more items. Now, only admins can use this type!
• /unlock <item(s)>: Unlock one or more items. Everyone can use this type again!
• /locks: List currently locked items.
• /lockwarns <yes/no/on/off>: Enabled or disable whether a user should be warned when using a locked item.
• /locktypes: Show the list of all lockable items.
• /allowlist <url/id/@channelname(s)>: Allowlist a URL, group ID, channel @, or bot @ to stop them being deleted by URL, forward, invitelink, inline, and guestbot locks. Separate with a space to add multiple items at once. If no arguments are given, returns the current allowlist.
• /allowlist emojipack:<>: Reply to a message with custom emoji to allow that custom emoji pack while `emojicustom` is locked.
• /rmallowlist <url/id/@channelname(s)>: Remove an item from the allowlist - url, invitelink, and forward locking will now take effect on messages containing it again. Separate with a space to remove multiple items.
• /rmallowlistall: Remove all allowlisted items.
"""

__sub_mod__ = ["Example commands", "Lock descriptions"]
