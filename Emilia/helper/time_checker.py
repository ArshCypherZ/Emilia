from datetime import datetime, timedelta

from pyrogram.types import Message

from Emilia.helper.convert import convert_time


async def get_time(message):
    if message.reply_to_message:
        if not (len(message.text.split()) >= 2):
            await message.reply("You haven't specified a time to mute this user for!")
            return

        args = message.text.split()[1]
        if await check_time(message, args):
            return args

    elif not (message.reply_to_message):
        if not len(message.text.split()) >= 3:
            await message.reply("You haven't specified a time to mute this user for!")
            return

        args = message.text.split()[2]
        if await check_time(message, args):
            return args


async def check_time(message, args) -> bool:
    if len(args) == 0:
        await message.reply(f"failed to get specified time: You didn't provide me time")
        return

    if len(args) == 1:
        await message.reply(
            (
                f"failed to get specified time: '{args[-1]}' does not follow the expected time patterns.\n"
                "Example time values: 4m = 4 minutes, 3h = 3 hours, 6d = 6 days, 5w = 5 weeks."
            )
        )
        return False

    elif len(args) > 1:
        if not args[-2].isdigit():
            await message.reply(
                f"failed to get specified time: '{args[-2]}' is not a valid number"
            )
            return False

        elif args[-1] in ["w", "d", "h", "m"]:
            check_time_limit = await convert_time(int(args[:-1]), args[-1])
            # 31622400 ( seconds ) is 366 days
            if check_time_limit >= 31622400:
                await message.reply(
                    "failed to get specified time: temporary actions have to be between 1 minute and 366 days"
                )
                return False
            return True
        else:
            await message.reply(
                f"failed to get specified time: '{args[-1]}' is not a valid time char; expected one of w/d/h/m (weeks, days, hours, minutes)"
            )
            return False


async def time_string_helper(time_args):
    time_limit = int(time_args[:-1])
    if time_args[-1] == "w":
        time_format = "weeks"
    elif time_args[-1] == "d":
        time_format = "days"
    elif time_args[-1] == "h":
        time_format = "hours"
    elif time_args[-1] == "m":
        time_format = "minutes"
    return time_limit, time_format


async def time_converter(message: Message, time_value: str) -> datetime:
    unit = ["m", "h", "d"]  # m == minutes | h == hours | d == days
    check_unit = "".join(list(filter(time_value[-1].lower().endswith, unit)))
    currunt_time = datetime.now()
    time_digit = time_value[:-1]
    if not time_digit.isdigit():
        return await message.reply_text("Incorrect time specified")
    if check_unit == "m":
        temp_time = currunt_time + timedelta(minutes=int(time_digit))
    elif check_unit == "h":
        temp_time = currunt_time + timedelta(hours=int(time_digit))
    elif check_unit == "d":
        temp_time = currunt_time + timedelta(days=int(time_digit))
    else:
        return await message.reply_text("Incorrect time specified.")
    return temp_time


async def get_readable_time(time: int):
    if time >= 86400:
        time = int(time / (60 * 60 * 24))
        unit = "days"
    elif time >= 3600 < 86400:
        time = int(time / (60 * 60))
        unit = "hours"
    elif time >= 60 < 3600:
        time = int(time / 60)
        unit = "minutes"
    elif time < 60:
        time = int(time)
        unit = "seconds"
    return "{} {}".format(time, unit)
