__mod_name__ = "Federation Owner Commands"

__hidden__ = True

__help__ = """
> These are the list of available fed owner commands. To run these, you have to own the current federation.

**Owner Commands**:
• `/newfed <fedname>` — Creates a new federation with the given name. Only one federation per user.
• `/renamefed <fedname>` — Rename your federation.
• `/delfed` — Deletes your federation, and any information related to it. Will not unban any banned users.
• `/fedtransfer <reply/username/mention/userid>` — Transfer your federation to another user.
• `/fpromote` — Promote a user to fedadmin in your fed. To avoid unwanted fedadmin, the user will get a message to confirm this.
• `/fdemote` — Demote a federation admin in your fed.
• `/fedreason <yes/no/on/off>` — Whether or not fedbans should require a reason.
• `/fednotif <yes/no/on/off>` — Whether or not to receive PM notifications of every fed action.
• `/subfed <FedId>` — Subscribe your federation to another. Users banned in the subscribed fed will also be banned in this one.
Note: This does not affect your banlist. You just inherit any bans.
• `/unsubfed <FedId>` — Unsubscribes your federation from another. Bans from the other fed will no longer take effect.
• `/fedexport <csv/minicsv/json/human>` — Get the list of currently banned users. Default output is CSV.
• `/fedimport <overwrite/keep> <csv/minicsv/json/human>` — Import a list of banned users.
• `/setfedlog` — Sets the current chat as the federation log. All federation events will be logged here.
• `/unsetfedlog` — Unset the federation log. Events will no longer be logged.
"""
