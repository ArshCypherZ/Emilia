import datetime
import random
from telethon import events
from Emilia import telethn, LOGGER
from Emilia.custom_filter import register
from Emilia.utils.decorators import usage, example, description
from Emilia.mongo import birthday_mongo as db
from Emilia.utils.helper import j1 as scheduler
from Emilia.functions.admins import can_change_info

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
async def set_birthday_handler(event):
    args = event.text.split(None, 1)
    if len(args) < 2:
        await event.reply("Usage: /setbirthday DD/MM")
        return

    date_str = args[1]
    try:
        date = datetime.datetime.strptime(date_str, "%d/%m")
        day = date.day
        month = date.month
    except ValueError:
        await event.reply("Invalid format. Please use DD/MM.")
        return

    chat_id = event.chat_id if not event.is_private else None
    await db.set_birthday(event.sender_id, day, month, chat_id)
    
    msg = f"Birthday set to {day}/{month}!"
    if chat_id:
        msg += " I will wish you in this group."
    await event.reply(msg)

@usage("/addbirthday <user> <DD/MM>")
@example("/addbirthday @username 28/12")
@description("Set a user's birthday (Admin only).")
@register(pattern="addbirthday")
async def add_birthday_handler(event):
    if event.is_private:
        await event.reply("This command is for groups only.")
        return

    if not await can_change_info(event, event.sender_id):
        return

    args = event.text.split()
    if len(args) < 3:
        await event.reply("Usage: /addbirthday <user> <DD/MM>")
        return

    user_str = args[1]
    date_str = args[2]

    try:
        user = await telethn.get_entity(user_str)
        user_id = user.id
    except Exception:
        await event.reply("User not found.")
        return

    try:
        date = datetime.datetime.strptime(date_str, "%d/%m")
        day = date.day
        month = date.month
    except ValueError:
        await event.reply("Invalid format. Please use DD/MM.")
        return

    await db.set_birthday(user_id, day, month, event.chat_id)
    await event.reply(f"Birthday set for {user.first_name} to {day}/{month}! I will wish them in this group.")

@usage("/birthday [user]")
@example("/birthday @username")
@description("Get a user's birthday.")
@register(pattern="birthday")
async def get_birthday_handler(event):
    user_id = event.sender_id
    
    if event.reply_to_msg_id:
        reply_msg = await event.get_reply_message()
        user_id = reply_msg.sender_id
    elif len(event.text.split()) > 1:
        try:
            user = await telethn.get_entity(event.text.split()[1])
            user_id = user.id
        except Exception:
            await event.reply("User not found.")
            return

    data = await db.get_birthday(user_id)
    if data:
        await event.reply(f"Birthday is on {data['day']}/{data['month']}.")
    else:
        await event.reply("Birthday not set.")

@usage("/delbirthday")
@example("/delbirthday")
@description("Delete your birthday.")
@register(pattern="delbirthday")
async def del_birthday_handler(event):
    await db.delete_birthday(event.sender_id)
    await event.reply("Birthday deleted.")

async def check_birthdays():
    today = datetime.datetime.now()
    day = today.day
    month = today.month
    
    birthdays = await db.get_birthdays_by_date(day, month)
    for b in birthdays:
        user_id = b['user_id']
        chats = b.get('chats', [])
        
        wish = random.choice(BIRTHDAY_WISHES)
        
        # Try to get user name
        try:
            user = await telethn.get_entity(user_id)
            name = user.first_name
        except:
            name = "User"
            
        mention = f"[{name}](tg://user?id={user_id})"
        text = f"{wish}\nHappy Birthday {mention}!"

        # Send to chats
        for chat_id in chats:
            try:
                await telethn.send_message(chat_id, text)
            except Exception as e:
                LOGGER.error(f"Failed to send birthday message to chat {chat_id} for user {user_id}: {e}")

        # If no chats, send PM
        if not chats:
             try:
                await telethn.send_message(user_id, wish)
             except Exception as e:
                LOGGER.error(f"Failed to send birthday PM to {user_id}: {e}")

scheduler.add_job(check_birthdays, "cron", hour=0, minute=0)