__mod_name__ = "Approval"

__help__ = """
> Sometimes, you might trust a user not to send unwanted content.
> Maybe not enough to make them admin, but you might be ok with locks, blocklists, and antiflood not applying to them.

> That's what approvals are for - approve of trustworthy users to allow them to send

**User commands**:
• `/approval` — Check a user's approval status in this chat.

**Admin commands**:
• `/approve` — Approve of a user. Locks, blocklists, and antiflood won't apply to them anymore.
• `/unapprove` — Unapprove of a user. They will now be subject to locks, blocklists, and antiflood again.
• `/approved` — List all approved users.
• `/unapproveall` — Unapprove ALL users in a chat. This cannot be undone.
"""
