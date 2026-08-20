__mod_name__ = "Notes"

__sub_mod__ = ["Example for usage", "Formatting"]

__help__ = """
> Save data for future users with notes!

> Notes are great to save random tidbits of information; a phone number, a nice gif, a funny picture - anything!

**User commands**:
• `/get <notename>` — Get a note.
• #notename: Same as /get.

**Admin commands**:
• `/save <notename> <note text>` — Save a new note called "word". Replying to a message will save that message. Even works on media!
• `/clear <notename>` — Delete the associated note.
• `/notes` — List all notes in the current chat.
• `/saved` — Same as /notes.
• `/clearall` — Delete ALL notes in a chat. This cannot be undone.
• `/privatenotes` — Whether or not to send notes in PM. Will send a message with a button which users can click to get the note in PM.
"""
