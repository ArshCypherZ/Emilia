import datetime
import random

from pyrogram.enums import ChatType

from Emilia import LOGGER, pgram
from Emilia.custom_filter import register
from Emilia.helper.admins import can_change_info
from Emilia.mongo import birthday_mongo as db
from Emilia.utils.decorators import description, example, usage
from Emilia.utils.helper import j1 as scheduler

BIRTHDAY_WISHES = [
    "Happy Birthday! 🎉 May your day be filled with joy and laughter!",
    "Wishing you a very Happy Birthday! 🎂 Have a fantastic year ahead!",
    "Happy Birthday! 🎈 Hope all your birthday wishes come true!",
    "Many happy returns of the day! 🎁 Enjoy your special day!",
    "Happy Birthday! 🥳 May this year bring you success and happiness!",
    "Happy Birthday! 🍰 Eat lots of cake and have fun!",
    "Wishing you the happiest of birthdays! 🎊",
    "Happy Birthday! 🌟 Shine bright like a diamond today!",
]


@usage("/setbirthday <DD/MM>")
@example("/setbirthday 28/12")
@description("Set your birthday. If used in a group, the bot will wish you here.")
@register(pattern="setbirthday")
async def set_birthday_handler(client, message):
    args = (message.text or "").split(None, 1)
    if len(args) < 2:
        await message.reply_text("Usage: /setbirthday DD/MM")
        return

    date_str = args[1]
    try:
        date = datetime.datetime.strptime(date_str, "%d/%m")
        day = date.day
        month = date.month
    except ValueError:
        await message.reply_text("Invalid format. Please use DD/MM.")
        return

    chat_id = message.chat.id if message.chat.type != ChatType.PRIVATE else None
    sender_id = message.from_user.id if message.from_user else None
    await db.set_birthday(sender_id, day, month, chat_id)

    msg = f"Birthday set to {day}/{month}!"
    if chat_id:
        msg += " I will wish you in this group."
    await message.reply_text(msg)


@usage("/addbirthday <user> <DD/MM>")
@example("/addbirthday @username 28/12")
@description("Set a user's birthday (Admin only).")
@register(pattern="addbirthday")
async def add_birthday_handler(client, message):
    if message.chat.type == ChatType.PRIVATE:
        await message.reply_text("This command is for groups only.")
        return

    sender_id = message.from_user.id if message.from_user else None
    if not await can_change_info(message, sender_id):
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.reply_text("Usage: /addbirthday <user> <DD/MM>")
        return

    user_str = args[1]
    date_str = args[2]

    try:
        user = await client.get_users(user_str)
        user_id = user.id
    except Exception:
        await message.reply_text("User not found.")
        return

    try:
        date = datetime.datetime.strptime(date_str, "%d/%m")
        day = date.day
        month = date.month
    except ValueError:
        await message.reply_text("Invalid format. Please use DD/MM.")
        return

    await db.set_birthday(user_id, day, month, message.chat.id)
    await message.reply_text(
        f"Birthday set for {user.first_name} to {day}/{month}! I will wish them in this group."
    )


@usage("/birthday [user]")
@example("/birthday @username")
@description("Get a user's birthday.")
@register(pattern="birthday")
async def get_birthday_handler(client, message):
    user_id = message.from_user.id if message.from_user else None

    if message.reply_to_message_id:
        reply_msg = message.reply_to_message
        user_id = reply_msg.from_user.id if reply_msg.from_user else None
    elif len((message.text or "").split()) > 1:
        try:
            user = await client.get_users(message.text.split()[1])
            user_id = user.id
        except Exception:
            await message.reply_text("User not found.")
            return

    data = await db.get_birthday(user_id)
    if data:
        await message.reply_text(f"Birthday is on {data['day']}/{data['month']}.")
    else:
        await message.reply_text("Birthday not set.")


@usage("/delbirthday")
@example("/delbirthday")
@description("Delete your birthday.")
@register(pattern="delbirthday")
async def del_birthday_handler(client, message):
    sender_id = message.from_user.id if message.from_user else None
    await db.delete_birthday(sender_id)
    await message.reply_text("Birthday deleted.")


async def check_birthdays():
    today = datetime.datetime.now()
    day = today.day
    month = today.month

    async for b in db.get_birthdays_by_date(day, month):
        user_id = b["user_id"]
        chats = b.get("chats", [])

        wish = random.choice(BIRTHDAY_WISHES)

        # Try to get user name
        try:
            user = await pgram.get_users(user_id)
            name = user.first_name
        except Exception:
            name = "User"

        mention = f"[{name}](tg://user?id={user_id})"
        text = f"{wish}\nHappy Birthday {mention}!"

        # Send to chats
        for chat_id in chats:
            try:
                await pgram.send_message(chat_id, text)
            except Exception as e:
                LOGGER.error(
                    f"Failed to send birthday message to chat {chat_id} for user {user_id}: {e}"
                )

        # If no chats, send PM
        if not chats:
            try:
                await pgram.send_message(user_id, wish)
            except Exception as e:
                LOGGER.error(f"Failed to send birthday PM to {user_id}: {e}")


scheduler.add_job(check_birthdays, "cron", hour=0, minute=0)
