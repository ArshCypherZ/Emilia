from Emilia.custom_filter import register
from Emilia.utils.decorators import *


@register(pattern="test")
@rate_limit(RATE_LIMIT_GENERAL)
async def test(event):
    await event.reply("test")