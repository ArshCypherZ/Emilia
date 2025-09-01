from Emilia import db

welcome = db.welcome

DEFAUT_WELCOME = "Hey there {first}, and welcome to {chatname}! How are you?"
DEFAUT_GOODBYE = "{first}, left the chat!"


async def SetWelcome(chat_id, Content, Text, DataType):
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "welcome_message.content": Content,
                "welcome_message.text": Text,
                "welcome_message.data_type": DataType,
            },
            "$setOnInsert": {"welcome": True, "clean_service": False},
        },
        upsert=True,
    )


async def UnSetWelcome(chat_id):
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$unset": {
                "welcome_message.content": 1,
                "welcome_message.text": 1,
                "welcome_message.data_type": 1,
            }
        },
    )


async def GetWelcome(chat_id):
    doc = await welcome.find_one(
        {"chat_id": chat_id},
        {"_id": 0, "welcome_message": 1},
    )
    if doc and doc.get("welcome_message") and "text" in doc["welcome_message"]:
        wm = doc["welcome_message"]
        return (wm.get("content"), wm.get("text"), wm.get("data_type"))


async def SetWelcomeMessageOnOff(chat_id, welcome_message):
    await welcome.update_one(
        {"chat_id": chat_id}, {"$set": {"welcome": welcome_message}}, upsert=True
    )


async def GetWelcomemessageOnOff(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "welcome": 1})
    return doc.get("welcome", True) if doc else True


async def isWelcome(chat_id) -> bool:
    doc = await welcome.find_one(
        {"chat_id": chat_id}, {"_id": 0, "welcome_message.text": 1}
    )
    return bool(doc and doc.get("welcome_message", {}).get("text"))


async def SetGoodBye(chat_id, Content, Text, DataType):
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "goodbye_message.content": Content,
                "goodbye_message.text": Text,
                "goodbye_message.data_type": DataType,
            }
        },
        upsert=True,
    )


async def UnSetGoodbye(chat_id):
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$unset": {
                "goodbye_message.content": 1,
                "goodbye_message.text": 1,
                "goodbye_message.data_type": 1,
            }
        },
    )


async def GetGoobye(chat_id):
    doc = await welcome.find_one(
        {"chat_id": chat_id}, {"_id": 0, "goodbye_message": 1}
    )
    if doc and doc.get("goodbye_message") and "text" in doc["goodbye_message"]:
        gm = doc["goodbye_message"]
        return (gm.get("content"), gm.get("text"), gm.get("data_type"))


async def SetGoodbyeMessageOnOff(chat_id, goodbye_message):
    await welcome.update_one(
        {"chat_id": chat_id}, {"$set": {"goodbye": goodbye_message}}, upsert=True
    )


async def GetGoodbyemessageOnOff(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "goodbye": 1})
    return doc.get("goodbye", True) if doc else True


async def isGoodbye(chat_id) -> bool:
    doc = await welcome.find_one(
        {"chat_id": chat_id}, {"_id": 0, "goodbye_message.text": 1}
    )
    return bool(doc and doc.get("goodbye_message", {}).get("text"))


async def SetCleanService(chat_id, clean_service):
    await welcome.update_one(
        {"chat_id": chat_id},
        {"$set": {"clean_service": clean_service}},
        upsert=True,
    )


async def GetCleanService(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "clean_service": 1})
    return doc.get("clean_service", False) if doc else False


async def SetCleanWelcome(chat_id, clean_welcome):
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "clean_welcome": clean_welcome,
                "clean_welcome_message": None,
            }
        },
        upsert=True,
    )


async def SetCleanWelcomeMessage(chat_id, message_id):
    await welcome.update_one(
        {"chat_id": chat_id}, {"$set": {"clean_welcome_message": message_id}}
    )


async def GetCleanWelcome(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "clean_welcome": 1})
    return doc.get("clean_welcome", True) if doc else True


async def GetCleanWelcomeMessage(chat_id):
    doc = await welcome.find_one(
        {"chat_id": chat_id}, {"_id": 0, "clean_welcome_message": 1}
    )
    return doc.get("clean_welcome_message") if doc else None


async def SetCaptcha(chat_id, captcha):
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "captcha": {
                    "_captcha": captcha,
                    "captcha_mode": None,
                    "captcha_text": None,
                    "captcha_kick_time": None,
                    "users_welcomeIDs": [],
                    "verified_users": [],
                }
            }
        },
        upsert=True,
    )


async def isGetCaptcha(chat_id) -> bool:
    captcha_count = await welcome.count_documents(
        {"chat_id": chat_id, "captcha._captcha": True}
    )
    return captcha_count > 0


async def GetCaptchaSettings(chat_id):
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "captcha": 1})
    captcha_text_de = "Click here to prove you're human"
    if doc and doc.get("captcha"):
        cm = doc["captcha"].get("captcha_mode") or "button"
        ct = doc["captcha"].get("captcha_text") or captcha_text_de
        ckt = doc["captcha"].get("captcha_kick_time")
        return (cm, ct, ckt)
    return ("button", captcha_text_de, None)


async def SetCaptchaText(chat_id, captcha_text):
    # First ensure the document and captcha structure exists
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$setOnInsert": {
                "chat_id": chat_id,
                "captcha": {
                    "_captcha": False,
                    "captcha_mode": None,
                    "captcha_text": None,
                    "captcha_kick_time": None,
                    "users_welcomeIDs": [],
                    "verified_users": [],
                }
            }
        },
        upsert=True,
    )
    # Then set the captcha text
    await welcome.update_one(
        {"chat_id": chat_id},
        {"$set": {"captcha.captcha_text": captcha_text}},
    )


async def SetCaptchaMode(chat_id, captcha_mode):
    # First ensure the document and captcha structure exists
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$setOnInsert": {
                "chat_id": chat_id,
                "captcha": {
                    "_captcha": False,
                    "captcha_mode": None,
                    "captcha_text": None,
                    "captcha_kick_time": None,
                    "users_welcomeIDs": [],
                    "verified_users": [],
                }
            }
        },
        upsert=True,
    )
    # Then set the captcha mode
    await welcome.update_one(
        {"chat_id": chat_id},
        {"$set": {"captcha.captcha_mode": captcha_mode}},
    )


async def SetUserCaptchaMessageIDs(chat_id, user_id, message_id):
    # ensure only one entry per user via pull then push
    await welcome.update_one(
        {"chat_id": chat_id},
        {"$pull": {"captcha.users_welcomeIDs": {"user_id": user_id}}},
    )
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$push": {
                "captcha.users_welcomeIDs": {
                    "user_id": user_id,
                    "message_id": message_id,
                    "chances": None,
                    "correct_captcha": None,
                    "captcha_list": [],
                }
            }
        },
        upsert=True,
    )


async def SetCaptchaTextandChances(chat_id, user_id, captcha_text, chances, captcha_list):
    await welcome.update_one(
        {"chat_id": chat_id, "captcha.users_welcomeIDs.user_id": user_id},
        {
            "$set": {
                "captcha.users_welcomeIDs.$.correct_captcha": captcha_text,
                "captcha.users_welcomeIDs.$.chances": chances,
                "captcha.users_welcomeIDs.$.captcha_list": captcha_list,
            }
        },
        upsert=True,
    )


async def CaptchaChanceUpdater(chat_id, user_id, chances):
    await welcome.update_one(
        {"chat_id": chat_id, "captcha.users_welcomeIDs.user_id": user_id},
        {"$set": {"captcha.users_welcomeIDs.$.chances": chances}},
    )


async def GetChance(chat_id, user_id):
    doc = await welcome.find_one(
        {"chat_id": chat_id},
        {"_id": 0, "captcha.users_welcomeIDs": {"$elemMatch": {"user_id": user_id}}},
    )
    arr = (doc or {}).get("captcha", {}).get("users_welcomeIDs", [])
    return arr[0].get("chances") if arr else None


async def GetUserCaptchaMessageIDs(chat_id: int, user_id: int):
    doc = await welcome.find_one(
        {"chat_id": chat_id},
        {"_id": 0, "captcha.users_welcomeIDs": {"$elemMatch": {"user_id": user_id}}},
    )
    arr = (doc or {}).get("captcha", {}).get("users_welcomeIDs", [])
    if not arr:
        return None
    u = arr[0]
    return (
        u.get("message_id"),
        u.get("correct_captcha"),
        u.get("chances"),
        u.get("captcha_list"),
    )


async def DeleteUsercaptchaData(chat_id, user_id):
    await welcome.update_one(
        {"chat_id": chat_id},
        {"$pull": {"captcha.users_welcomeIDs": {"user_id": user_id}}},
    )


async def AppendVerifiedUsers(chat_id, user_id):
    await welcome.update_one(
        {"chat_id": chat_id}, {"$addToSet": {"captcha.verified_users": user_id}}, upsert=True
    )


async def isUserVerified(chat_id, user_id) -> bool:
    doc = await welcome.find_one(
        {"chat_id": chat_id, "captcha.verified_users": user_id}, {"_id": 0}
    )
    return bool(doc)


async def setReCaptcha(chat_id: int, reCaptcha: bool):
    await welcome.update_one(
        {"chat_id": chat_id}, {"$set": {"reCaptcha": reCaptcha}}, upsert=True
    )


async def isReCaptcha(chat_id: int) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "reCaptcha": 1})
    return doc.get("reCaptcha", False) if doc else False


async def setRuleCaptcha(chat_id: int, rule_captcha: bool):
    await welcome.update_one(
        {"chat_id": chat_id}, {"$set": {"rule_captcha": rule_captcha}}, upsert=True
    )


async def isRuleCaptcha(chat_id: int) -> bool:
    doc = await welcome.find_one(
        {"chat_id": chat_id}, {"_id": 0, "rule_captcha": 1}
    )
    return doc.get("rule_captcha", False) if doc else False
