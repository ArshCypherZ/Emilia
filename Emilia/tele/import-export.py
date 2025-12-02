from Emilia import db
from Emilia.functions.admins import is_owner
from Emilia.custom_filter import register
import Emilia.strings as strings
from Emilia.utils.decorators import rate_limit, RATE_LIMIT_SUPER_HEAVY
from Emilia.pyro.connection.connection import connection
import orjson
import os
from bson import ObjectId

def default(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError

collections = {
    'blocklists': db['blocklists'],
    'disable': db['disable'],
    'filters': db['filters'],
    'locks': db['locks'],
    'notes': db['notes'],
    'rules': db['rules'],
    'warnings': db['warnings'],
    'welcome': db['welcome']
}

@register(pattern="export")
@rate_limit(RATE_LIMIT_SUPER_HEAVY)
async def export_settings(event):
    chat_id = await connection(event) if await connection(event) else event.chat_id
    if event.is_private and not str(chat_id).startswith('-100'):
        return await event.reply(strings.is_pvt)
    
    if not await is_owner(event, event.sender_id, chat_id):
        await event.reply("Only the chat owner can export settings.")
        return

    args = event.raw_text.split()[1:]

    exported_data = {}
    if not args:
        for key, collection in collections.items():
            settings = await collection.find_one({'chat_id': chat_id})
            if settings:
                settings.pop('_id', None)
                settings.pop('chat_id', None)
                exported_data[key] = settings
    else:
        for arg in args:
            collection = collections.get(arg)
            if collection:
                settings = await collection.find_one({'chat_id': chat_id})
                if settings:
                    settings.pop('_id', None)
                    settings.pop('chat_id', None)
                    exported_data[arg] = settings

    if not exported_data:
        await event.reply("No settings found.")
        return

    settings_json = orjson.dumps(exported_data, option=orjson.OPT_INDENT_2, default=default).decode('utf-8')
    file_name = f"chat_settings_{chat_id}.json"
    
    with open(file_name, 'w') as file:
        file.write(settings_json)
    
    await event.respond(file=file_name)
    os.remove(file_name)


@register(pattern="import")
@rate_limit(RATE_LIMIT_SUPER_HEAVY)
async def import_settings(event):
    chat_id = await connection(event) if await connection(event) else event.chat_id
    if event.is_private and not str(chat_id).startswith('-100'):
        return await event.reply(strings.is_pvt)

    if not await is_owner(event, event.sender_id, chat_id):
        await event.reply("Only the chat owner can import settings.")
        return

    if not event.is_reply:
        await event.reply("Reply to the JSON file containing settings.")
        return

    message = await event.get_reply_message()
    if not message.file or not message.file.name.endswith('.json'):
        await event.reply("Please reply to a valid JSON file.")
        return

    file_path = await message.download_media()

    with open(file_path, 'rb') as file:
        settings = orjson.loads(file.read())

    for key, value in settings.items():
        collection = collections.get(key)
        if collection is not None:
            value.pop('_id', None)
            value['chat_id'] = chat_id
            await collection.update_one({'chat_id': chat_id}, {'$set': value}, upsert=True)

    await event.reply("Settings imported successfully.")
    os.remove(file_path)


@register(pattern="chatreset")
@rate_limit(RATE_LIMIT_SUPER_HEAVY)
async def reset_settings(event):
    chat_id = await connection(event) if await connection(event) else event.chat_id
    if event.is_private and not str(chat_id).startswith('-100'):
        return await event.reply(strings.is_pvt)

    if not await is_owner(event, event.sender_id, chat_id):
        await event.reply("Only the chat owner can reset settings.")
        return

    for collection in collections.values():
        await collection.delete_one({'chat_id': chat_id})

    await event.reply("All chat settings have been reset.")