import random
from datetime import datetime, timedelta

from pyrogram import Client, enums

from Emilia import custom_filter, db, LOGGER
from Emilia.helper.disable import disable

collection = db.coup


async def select_couples(client, chat_id):
    try:
        members = []
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot:
                members.append(member.user.id)

        if len(members) < 2:
            await client.send_message(
                chat_id, "Oops! We need at least two members to form a couple!"
            )
            return

        couple_a, couple_b = random.sample(members, 2)
        current_time = datetime.now()
        expiration_time = current_time + timedelta(hours=24)

        await collection.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "couple_a": int(couple_a),
                    "couple_b": int(couple_b),
                    "expiration_time": expiration_time,
                }
            },
            upsert=True,
        )

        couple_a_user = await client.get_users(couple_a)
        couple_b_user = await client.get_users(couple_b)

        couple_a_mention = couple_a_user.mention if couple_a_user else "User not found"
        couple_b_mention = couple_b_user.mention if couple_b_user else "User not found"

        await client.send_message(
            chat_id,
            f"New couples have been selected! They're bound by fate for the next 24 hours! 🎉💖\n\n"
            f"💑 {couple_a_mention} and {couple_b_mention} 💑",
        )

    except Exception as e:
        await client.send_message(chat_id, f"Something went wrong: {str(e)}")


async def get_couples(chat_id):
    return await collection.find_one({"chat_id": chat_id})


@Client.on_message(custom_filter.command(("couples"), disable=True))
@disable
async def choose_couples_command(client, message):
    chat_id = message.chat.id

    if message.chat.type == enums.ChatType.PRIVATE:
        await message.reply_text("Sorry! This magic works only in group chats! 🎩✨")
        return

    couple_data = await get_couples(chat_id)
    if couple_data and couple_data.get("expiration_time", None) > datetime.now():
        couple_a_id = couple_data.get("couple_a")
        couple_b_id = couple_data.get("couple_b")

        couple_a = await get_user_or_not_found(client, couple_a_id)
        couple_b = await get_user_or_not_found(client, couple_b_id)
        if couple_a is None or couple_b is None:
            await select_couples(client, chat_id)
            return
        remaining_time = couple_data["expiration_time"] - datetime.now()
        hours_left = remaining_time.seconds // 3600
        await client.send_message(
            chat_id,
            f"🥰 **{couple_a.first_name}** and **{couple_b.first_name}** are the couple of the day! 🥰\n\n"
            f"⏳ {hours_left} hours left until the next selection! ⏳",
        )

    else:
        await select_couples(client, chat_id)


async def get_user_or_not_found(client, user_id):
    try:
        user = await client.get_users(user_id)
        return user
    except Exception as e:
        LOGGER.error(f"Error retrieving user: {e}")
        return None