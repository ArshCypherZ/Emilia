from Emilia import BOT_NAME

__mod_name__ = "Filters"

__help__ = f"""
Make your chat more lively with filters; The bot will reply to certain words!

Filters are case insensitive; every time someone says your trigger words, {BOT_NAME} will reply something else!
Dice messages can also match dice triggers such as the dice emoji, `dice:6`, or `🎲:6`.

**Commands**:

• /filter `<trigger> <reply>`: Every time someone says "trigger", the bot will reply with "sentence". For multiple word filters, quote the trigger.
• /filters: List all chat filters.
• /stop `<trigger>`: Stop the bot from replying to "trigger".
• /stopall: Stop ALL filters in the current chat. This cannot be undone.
"""

__sub_mod__ = ["Example Usage", "Formatting"]
