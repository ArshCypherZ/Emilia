__mod_name__ = "Quotes"

__help__ = """
> Quotes module allows you to create beautiful quote stickers out of Telegram messages natively!

**Commands**:

• `/q <reply to message>` — Creates a high-quality quote sticker from the replied message (supports text, photos, stickers, and voice messages!). 
  **Optional Arguments**: 
  - `<number>`: Quote a chain of messages (e.g., `/q 5` for up to 25 messages)
  - `<color>`: Set background via name (`red`) or hex code (`#ff0000`)
  - `p`: Output as a Photo instead of a sticker
  - `r`: Include the message that was replied to in a small bubble

• `/qrate <on/off>` — Enables upvoting/downvoting buttons on quotes in a group.

• `/qtop` — Shows the top highest-rated quotes in the group.

• `/qrand` — Sends a random quote from the group's saved quotes.
"""
