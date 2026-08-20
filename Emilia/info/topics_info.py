from Emilia import BOT_NAME

__mod_name__ = "Topics"

__help__ = f"""
> Manage your topic settings through {BOT_NAME}!

> Topics introduce lots of small differences to normal supergroups; this could affect how you would usually manage your chat.

> You never need to know or type a topic ID. Run any command below inside the
> topic you want to act on and {BOT_NAME} detects it automatically; run it
> without one (e.g. from General) and you get a tap-to-pick button list instead.

**Admin commands**:

• `/topics` — List every open topic with inline Close/Delete buttons.
• `/newtopic <name>` — Create a new topic.
• `/renametopic <name>` — Rename a topic - run inside it to rename that one, or pick from a list.
• `/opentopic` — Reopen a closed topic - run inside it, or pick from a list of closed topics.
• `/closetopic` — Close a topic - run inside it, or pick from a list.
• `/deletetopic` — Delete a topic and all its messages (cannot be undone) - run inside it, or pick from a list.

An explicit topic ID as an argument still works for scripting/automation, but is never required.
"""
