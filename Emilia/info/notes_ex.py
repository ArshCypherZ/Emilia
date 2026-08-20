__mod_name__ = "Example for usage"

__hidden__ = True

__help__ = """
> Notes can seem quite complicated; so here are some examples, so you can get some inspiration.

**Examples**:

• Saving a note. Now, anyone using #test or /get test will see this message. To save an image, gif, sticker, or any other kind of data, simply reply to that message
-> /save test This is a fancy note!

• You can also link notes through notebuttons. To do this, simply use the notename as the URL:
-> /save note This is a note [With a button](buttonurl://#anothernote)

• To save an admin-only note:
-> /save example This note will only be opened by admins {admin}

• To send all notes to the user's PM:
-> /privatenotes on

• To send a single note to user's PM, add a {private} tag to your note:
-> /save test This is a note that always goes to PM {private}

• If you've enabled privatenotes, but have one note that you don't want to go to PM:
-> /save test This is a note that always goes to groups {noprivate}
"""
