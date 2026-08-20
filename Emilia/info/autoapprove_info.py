__mod_name__ = "Autoapprove"

__help__ = """
> Telegram's Join Requests feature allows admins to review members before they join. 
> Emilia's Autoapprove module takes this to the next level by automatically filtering spammers, enforcing rules, and sending captchas privately.

**Admin Commands:**
• `/autoapprove [mode]`: Configure the Join Request behavior for the chat.

**Available Modes:**
• `off`: Disables autoapprove (default).
• `on`: Accepts all join requests blindly.
• `antispam`: Automatically accepts requests, but rejects users banned on Feds or Combot Anti-Spam (CAS).
• `rules`: Private messages users the group rules; approves them only when they accept.
• `captcha`: Private messages users a captcha; approves them only when they solve it.

**Example:** `/autoapprove antispam`
"""
