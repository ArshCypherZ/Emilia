from Emilia import BOT_NAME

__mod_name__ = "Requests"

__help__ = f"""
> Search linked storage channels for media and let users submit automated requests when content is missing.

> When a user sends `#req <name>` or `/req <name>`, {BOT_NAME} searches all connected storage channels. If found, direct post links are shown. If not found, an automated request ticket is created for uploaders in your Request Channel, and users receive an instant PM notification when uploaded!

**User commands**:
• `#req <query>` — Search channels for query or submit a request ticket.
• `/req <query>` — Same as #req (aliases: `/request`, `/searchreq`).
• `/reqs` — View your active and completed requests (aliases: `/myrequests`).
• `/reqstatus <id>` — Check live status of a specific Request ID.

**Admin commands**:
• `/setreq <id or @username>` — Set the destination channel where new requests are dispatched.
• `/unsetreq` — Disconnect the request channel.
• `/addchannel <id or @username>` — Add a content/storage channel to the search pool.
• `/rmchannel <id or @username>` — Remove a channel from the search pool (aliases: `/delchannel`).
• `/channels` — View all linked search channels and request channel status (alias: `/reqsettings`).
• `/reqdone <id> [link]` — Mark a request fulfilled and broadcast post link to subscribers in PM.
• `/reqreject <id> [reason]` — Reject a request and notify subscribers in PM.
• `/reqmode <on/off>` — Enable or disable the request system in the chat.
• `/reqlimit <number>` — Set the maximum daily requests allowed per user.
"""
