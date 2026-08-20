__mod_name__ = "Bot2Bot"

__help__ = """
> Control whether other bots can run commands in this chat. This is useful for AI bots,
> automation bots, and helper bots, but should stay disabled unless you trust the flow.

**Admin commands**:

• `/bot2bot` — Show the current bot-to-bot settings.
• `/bot2bot <off/admin/all>` — Choose which bots can ask Emilia to run commands.
  - off: Ignore commands sent by other bots.
  - admin: Only allow commands from bots that are admins in the chat.
  - all: Allow commands from any bot in the chat.
• `/bot2botskipreview <on/off>` — Toggle whether allowed bot commands need admin approval before execution.

When review is enabled, Emilia asks a chat admin to approve or reject the bot command.
Approved commands run using the approving admin's permissions.

Default is `off`. Review is enabled by default. Anonymous admins will be asked to confirm
with a button before changing these settings.
"""
