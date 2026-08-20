__mod_name__ = "Purges"

__help__ = """
> Need to delete lots of messages? That's what purges are for!

**Admin commands**:

• `/purge` — Delete all messages from the replied to message, to the current message.
• `/spurge` — Same as purge, but doesn't send the final confirmation message.
• `/del` — Deletes the replied to message.
• `/purgefrom` — Reply to a message to mark the message as where to purge from • this should be used followed by a /purgeto.
• `/purgeto` — Delete all messages between the replied to message, and the message marked by the latest /purgefrom.

**Examples**:

• Delete all messages from the replied to message, until now.
-> /purge

• Mark the first message to purge from (as a reply).
-> /purgefrom

• Mark the message to purge to (as a reply). All messages between the previously marked /purgefrom and the newly marked /purgeto will be deleted.
-> /purgeto
"""
