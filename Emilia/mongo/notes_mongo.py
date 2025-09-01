from Emilia import db

notes = db.notes


async def SaveNote(chat_id, note_name, content, text, data_type):
    GetNotes = await notes.find_one({"chat_id": chat_id})

    if GetNotes is None:
        NoteData = {
            "chat_id": chat_id,
            "notes": [
                {
                    "note_name": note_name,
                    "content": content,
                    "text": text,
                    "data_type": data_type,
                }
            ],
        }

        # Use idempotent upsert to avoid duplicates on initial create
        await notes.update_one(
            {"chat_id": chat_id}, {"$setOnInsert": NoteData}, upsert=True
        )
    else:
        if GetNotes.get("notes"):
            # Upsert or add uniquely by note_name
            updated = await notes.update_one(
                {"chat_id": chat_id, "notes.note_name": note_name},
                {
                    "$set": {
                        "notes.$.note_name": note_name,
                        "notes.$.content": content,
                        "notes.$.text": text,
                        "notes.$.data_type": data_type,
                    }
                },
            )
            if updated.matched_count == 0:
                await notes.update_one(
                    {"chat_id": chat_id},
                    {
                        "$addToSet": {
                            "notes": {
                                "note_name": note_name,
                                "content": content,
                                "text": text,
                                "data_type": data_type,
                            }
                        }
                    },
                    upsert=True,
                )
        else:
            await notes.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "notes": [
                            {
                                "note_name": note_name,
                                "content": content,
                                "text": text,
                                "data_type": data_type,
                            }
                        ]
                    }
                },
            )


async def GetNote(chat_id, note_name):
    doc = await notes.find_one(
        {"chat_id": chat_id, "notes.note_name": note_name},
        {"notes": {"$elemMatch": {"note_name": note_name}}},
    )
    if doc and doc.get("notes"):
        n = doc["notes"][0]
        return (n["content"], n["text"], n["data_type"])
    return None


async def isNoteExist(chat_id, note_name) -> bool:
    note_count = await notes.count_documents(
        {"chat_id": chat_id, "notes.note_name": note_name}
    )
    return note_count > 0


async def NoteList(chat_id) -> list:
    names = []
    doc = await notes.find_one({"chat_id": chat_id}, {"notes.text": 1, "notes.note_name": 1})
    if doc and doc.get("notes"):
        for note in doc["notes"]:
            NoteText = note.get("text") or ""
            NoteName = note.get("note_name")
            if not NoteName:
                continue
            if "{admin}" in NoteText:
                NoteName = f"{NoteName} __{admin}__"
            names.append(NoteName)
    return names


async def ClearNote(chat_id, note_name):
    await notes.update_one(
        {"chat_id": chat_id}, {"$pull": {"notes": {"note_name": note_name}}}
    )


async def set_private_note(chat_id, private_note):
    await notes.update_one(
        {"chat_id": chat_id}, {"$set": {"private_note": private_note}}, upsert=True
    )


async def is_pnote_on(chat_id) -> bool:
    GetNoteData = await notes.find_one({"chat_id": chat_id}, {"private_note": 1})
    if GetNoteData is not None:
        return bool(GetNoteData.get("private_note"))
    else:
        return False


async def ClearAllNotes(chat_id):
    # Use correct MongoDB $unset semantics: the value is ignored, but should not be an array
    await notes.update_one({"chat_id": chat_id}, {"$unset": {"notes": ""}})
