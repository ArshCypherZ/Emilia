"""Safe accessors for Message.forward_origin.

forward_origin is a union of MessageOriginUser / MessageOriginHiddenUser /
MessageOriginChat / MessageOriginChannel / MessageOriginImport - each only
defines a subset of attributes, so plain attribute access raises
AttributeError on the wrong subtype. Mirrors pyrogram's own deprecated
Message.forward_from* property implementations (message.py), which use
getattr with a default for exactly this reason.
"""


def fwd_user(message):
    return getattr(message.forward_origin, "sender_user", None)


def fwd_chat(message):
    origin = message.forward_origin
    return getattr(origin, "chat", getattr(origin, "sender_chat", None))


def fwd_date(message):
    return getattr(message.forward_origin, "date", None)
