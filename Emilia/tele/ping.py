import time

from Emilia.custom_filter import register
from Emilia.functions.admins import get_time
from Emilia.helper.disable import disable

StartTime = time.time()


@register(pattern="ping", disable=True)
@disable
async def ping(event):
    start_time = time.time()
    message = await event.reply("Pinging...")
    end_time = time.time()
    telegram_ping = str(round((end_time - start_time) * 1000, 3)) + " ms"
    uptime = await get_time((int(time.time()) - int(StartTime)))

    await message.edit(
        f"**PONG!!**\n**Time Taken:** `{telegram_ping}`\n**Service uptime:** `{uptime}`"
    )
