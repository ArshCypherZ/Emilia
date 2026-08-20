__mod_name__ = "User Commands"

__hidden__ = True

__help__ = """
> These commands do not require you to be admin of a federation. These commands are for general commands, such as looking up information on a fed, or checking a user's fbans.

**Commands**:
• `/fedinfo <FedID>` — Information about a federation.
• `/fedadmins <FedID>` — List the admins in a federation.
• `/fedsubs <FedID>` — List all federations your federation is subscribed to.
• `/joinfed <FedID>` — Join the current chat to a federation. A chat can only join one federation. Chat owners only.
• `/leavefed` — Leave the current federation. Only chat owners can do this.
• `/fedstat` — List all the federations that you have been banned in.
• `/chatfed` — Information about the federation the current chat is in.
• `/quietfed <yes/no/on/off>` — Whether or not to send ban notifications when fedbanned users join the chat.
"""
