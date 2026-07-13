from Emilia import BOT_NAME

__mod_name__ = "Lock descriptions"

__hidden__ = True

__help__ = f"""
There are lots of different locks, and some of them might not be super clear; this section aims to explain each kind of lock.

**Types**:

• all: All messages.
• album: Photos or documents sent as albums.
• audio: Audio media messages.
• bot: Anyone adding bots. Note: bots (like {BOT_NAME}) cannot see other bots.
• button: Messages which contain buttons.
• command: Messages which start with a Telegram command (eg: /start).
• comment: Messages sent by users that are commenting in the linked channel, yet aren't members of the group.
• contact: Contact media messages.
• document: Document media messages. This includes photos/videos sent uncompressed.
• email: Messages which contain emails (as defined by Telegram).
• emojigame: Telegram mini games like dice, bowling, or darts.
• forward: Forwarded messages.
• forwardbot: Messages where the original sender is a bot.
• forwardchannel: Messages where the original sender is a channel.
• forwarduser: Messages where the original sender is a user.
• game: Bot API game messages.
• gif: GIF media messages.
• inline: Messages sent through inline bots, like @gif or @pic
• invitelink: Messages containing private and public links to groups or channels.
• location: Location messages.
• phone: Messages which contain phone numbers (as defined by Telegram).
• photo: Messages containing a photo.
• poll: Poll messages.
• rtl: Messages which contain right-to-left characters. Eg: Arabic, Farsi, Hebrew, etc.
• sticker: All sticker types.
• text: Messages which contain text, including media captions.
• url: Messages which contain website links (as defined by Telegram)
• video: Video media messages.
• videonote: Videonote media messages.
• voice: Voice messages.
• reaction: Reactions added to messages. Non-admin, non-approved user reactions are removed.
• outsidereaction: Reactions from users who are not members of the group.
• guestbot: Messages sent through Telegram guest bots. Allowlist trusted guest bots if needed.
• emojicustom: Messages containing custom emoji. Use `/allowlist emojipack:<>` while replying to a custom emoji message to allow a pack.

"""
