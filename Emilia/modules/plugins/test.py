from pyrogram import Client

import Emilia.custom_filter as custom_filter
from Emilia import LOGGER


@Client.on_message(custom_filter.command("gae"))
async def startgae(client, message):
    try:
        await message.reply(
            "Hello! I am Emilia, your friendly bot. How can I assist you today?"
        )
        LOGGER.info("Starting Emilia...")
    except Exception as e:
        LOGGER.error(f"Error in start command: {e}")
    finally:
        LOGGER.info("Start command processed.")
