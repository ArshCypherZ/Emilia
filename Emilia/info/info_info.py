__mod_name__ = "Info"

__help__ = """
> This module allows user to check own's or other's certain information.

**ID**:
• `/id` — get the current group id. If used by replying to a message, gets that user's id.
• `/gifid` — reply to a gif to me to tell you its file ID.
• `/stickerid` — reply to a sticker to me to tell you its file ID.


**Self addded information**:
• `/setme <text>` — will set your info
• `/me` — will get your or another user's info.

> Examples:
> - `/setme I am a cat.`
> - `/me @username(defaults to yours if no user specified)`


**Information others add on you**:
• `/bio` — will get your or another user's bio. This cannot be set by yourself.
• `/setbio <text>` — while replying, will save another user's bio

> Examples:
> - `/bio @username(defaults to yours if not specified).`
> - `/setbio This user is a cat` (reply to the user)


**Overall Information**:
• `/info` — get information about a user.
• `/ginfo` — get information about a chat.
"""
