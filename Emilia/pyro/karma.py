from pyrogram import Client, filters

from Emilia import custom_filter, db
from Emilia.helper.chat_status import check_user
from Emilia.mongo.karma_mongo import is_karma_on, karma_off, karma_on
from Emilia.utils.decorators import *

regex_upvote = r"(?i)^(\+|\+\+|\+1|thx|tnx|ty|thank you|thanx|thanks|pro|cool|good|👍|nice|noice|piro|arsh)$"
regex_downvote = (
    r"(?i)^(\-|\-\-|\-1|👎|noob|Noob|gross|fuck off|gay|tamilvip|moezilla)$"
)

karma_positive_group = 30
karma_negative_group = 40


@usage("/karma [enable/disable]")
@example("/karma enable")
@description(
    "This will enable or disable karma system in group. Karma system is basically point counting system which shows a user's respect level in a particular group chat."
)
@Client.on_message(custom_filter.command(commands="karma") & filters.group)
@logging
async def captcha_state(_, message):
    if not await check_user(message, privileges="can_change_info"):
        return
    if len(message.text.split()) != 2:
        await usage_string(message, captcha_state)
        return
    chat_id = message.chat.id
    state = message.text.split(None, 1)[1].strip()
    state = state.lower()
    if state == "enable":
        await karma_on(chat_id)
        await message.reply_text("Enabled Karma System for this chat.")
        return "KARMA_ENABLE", None, None
    elif state == "disable":
        await karma_off(chat_id)
        await message.reply_text("Disabled Karma System for this chat.")
        return "KARMA_DISABLE", None, None
    else:
        await message.reply_text(usage)


users_collection = db.chatlevels


async def increase_points(user_id, chat_id, points):
    # Use targeted filter and upsert to avoid read-before-write; ensured index on (chat_id, user_id)
    flt = {"user_id": int(user_id), "chat_id": int(chat_id)}
    return await users_collection.update_one(flt, {"$inc": {"points": points}}, upsert=True)


@Client.on_message(
    filters.text
    & filters.group
    & filters.incoming
    & filters.reply
    & filters.regex(regex_upvote)
    & ~filters.via_bot
    & ~filters.bot,
    group=karma_positive_group,
)
async def upvote(_, message):
    chat_id = message.chat.id
    is_karma = await is_karma_on(chat_id)
    if is_karma:
        if not message.reply_to_message.from_user:
            return
        if not message.from_user:
            return
        if message.reply_to_message.from_user.id == message.from_user.id:
            return
        user_id = message.reply_to_message.from_user.id
        user_mention = message.reply_to_message.from_user.mention
        await increase_points(user_id, chat_id, 1)
        fuser = await users_collection.find_one({"user_id": int(user_id), "chat_id": int(chat_id)}, {"points": 1})
        await message.reply_text(
            f"Incremented Karma of {user_mention} By 1 \nTotal Points: {fuser['points']}"
        )


@Client.on_message(
    filters.text
    & filters.group
    & filters.incoming
    & filters.reply
    & filters.regex(regex_downvote)
    & ~filters.via_bot
    & ~filters.bot,
    group=karma_negative_group,
)
async def downvote(_, message):
    chat_id = message.chat.id
    is_karma = await is_karma_on(chat_id)
    if is_karma:
        if not message.reply_to_message.from_user:
            return
        if not message.from_user:
            return
        if message.reply_to_message.from_user.id == message.from_user.id:
            return
        user_id = message.reply_to_message.from_user.id
        user_mention = message.reply_to_message.from_user.mention
        await increase_points(user_id, chat_id, -1)
        fuser = await users_collection.find_one({"user_id": int(user_id), "chat_id": int(chat_id)}, {"points": 1})
        await message.reply_text(
            f"Decremented Karma of {user_mention} By 1 \nTotal Points: {fuser['points']}"
        )
