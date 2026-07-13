__mod_name__ = "Blocklists"

__help__ = """
Want to stop people asking stupid questions? or ban anyone saying censored words? Blocklists is the module for you!

From blocking rude words, filenames/extensions, to specific emoji, everything is possible.

**Admin commands:**
• /addblocklist `<blocklist trigger> <reason>`: Add a blocklist trigger. You can blocklist an entire sentence by putting it in "quotes".
• /addblocklist emojipack:<>: Reply to a message with custom emoji to blocklist every custom emoji pack used in that message.
• /rmblocklist `<blocklist trigger>`: Remove a blocklist trigger.
• /unblocklistall: Remove all blocklist triggers • chat creator only.
• /blocklist: List all blocklisted items.
• /blocklistmode `<blocklist mode>`: Set the desired action to take when someone says a blocklisted item. Available: nothing/ban/mute/kick/warn/tban/tmute.
• /blocklistdelete `<yes/no/on/off>`: Set whether blocklisted messages should be deleted. Default: (on)
• /setblocklistreason `<reason>`: Set the default blocklist reason to warn people with.
• /resetblocklistreason: Reset the default blocklist reason to default • nothing.

Top tip:
Blocklists allow you to use some modifiers to match "unknown" characters. For example, you can use the ? character to match a single occurrence of any non-whitespace character.
You could also use the * modifier, which matches any number of any character. If you want to blocklist urls, this will allow you to match the full thing. It matches every character except spaces. This is cool if you want to block, for example, url shorteners.

Custom emoji pack blocklists are useful when spam uses premium emoji instead of normal text.
"""


__sub_mod__ = ["Blocklist Command Examples"]
