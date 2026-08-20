from Emilia import BOT_NAME

__mod_name__ = "Disabling"

__help__ = f"""
> Not everyone wants every feature that {BOT_NAME} offers. Some commands are best left unused; to avoid spam and abuse.

> This allows you to disable some commonly used commands, so no one can use them. It'll also allow you to autodelete them, stopping people from bluetexting.

**Admin commands**:
• `/disable <commandname>` — Stop users from using "commandname" in this group.
• `/enable <item name>` — Allow users from using "commandname" in this group.
• `/disableable` — List all disableable commands.
• `/disabledel <yes/no/on/off>` — Delete disabled commands when used by non-admins.
• `/disabled` — List the disabled commands in this chat.

**Note**:
When disabling a command, the command only gets disabled for non-admins. All admins can still use those commands.
Disabled commands are still accessible through the /connect feature. If you would be interested to see this disabled too, let me know in the support chat.
"""
