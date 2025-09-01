from Emilia.helper.chat_status import isUserAdmin


async def privateNote_and_admin_checker(message, text: str):
    privateNote = True
    if "{noprivate}" in text:
        text = text.replace("{noprivate}", "")
        privateNote = False
    elif "{private}" in text:
        text = text.replace("{private}", "")
        privateNote = True
    else:
        privateNote = None

    allow = True
    if "{admin}" in text:
        text = text.replace("{admin}", "")
        if not await isUserAdmin(message, silent=True):
            allow = False
        else:
            allow = True

    return (privateNote, allow)


async def preview_text_replace(text):
    if "{preview}" in text:
        text = text.replace("{preview}", "")
        preview = False
    else:
        preview = True

    return (preview, text)
