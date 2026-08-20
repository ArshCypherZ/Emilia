__mod_name__ = "Example commands"

__hidden__ = True

__help__ = """
> Locks are a powerful tool, with lots of different options. So here are a few examples to get you started and familiar on how exactly to use them.

**Examples**:
• Stop all users from sending stickers with:
-> `/lock sticker`

• You can lock/unlock multiple items by chaining them:
-> `/lock sticker photo gif video`

• Want a harsher punishment for certain actions? Set a custom lock action for it! You must separate the types from your reason with ###:
-> `/lock invitelink ### no promoting other chats {ban}`

• Reset all custom lock actions and reasons; remember to unlock again after:
-> `/lock all ###`

• To allow forwards from a specific channel, eg @SpiralTechDivision, you can allowlist it. You can also use the ID, or invitelink:
-> `/allowlist @SpiralTechDivision`

• List all locks at once:
-> `/locks list`

"""
