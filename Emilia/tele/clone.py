import asyncio
import traceback
from telethon import TelegramClient, errors

from Emilia import API_HASH, API_ID, LOGGER, db, CLONE_LIMIT, SUPPORT_CHAT
from Emilia.custom_filter import register, auth
from Emilia.tele.clone_manager import clone_manager

clone_db = db.clone
startpic = db.startpic

async def get_clone_info_by_bot_id(bot_id):
    return await clone_db.find_one({"bot_id": bot_id})

@auth(pattern="stats")
async def stats_(event):
    users = await db.users.count_documents({})
    chats = await db.chats.count_documents({})
    bots = await clone_db.count_documents({})
    active_clones = len(clone_manager.clones)
    
    await event.reply(
        f"**Bot Statistics**\n\n"
        f"**Chats**: {chats}\n"
        f"**Users**: {users}\n"
        f"**Cloned Bots in Database**: {bots}\n"
        f"**Active Clone Clients**: {active_clones}\n\n"
    )

async def create_clone_client(user_id, token, bot_id):
    # Validate token first
    try:
        temp_client = TelegramClient(None, API_ID, API_HASH)
        await temp_client.start(bot_token=token)
        bot = await temp_client.get_me()
        bot_username = bot.username
        bot_name = bot.first_name
        await temp_client.disconnect()
    except errors.AccessTokenExpiredError:
        return False, "expired", None
    except errors.AccessTokenInvalidError:
        return False, "invalid", None
    except (errors.FloodWaitError, ConnectionError, OSError) as e:
        LOGGER.warning(f"Network/rate limit error for user {user_id}: {e}")
        await asyncio.sleep(30)
        return False, None, None
    except Exception as e:
        LOGGER.error(f"Error validating token for user {user_id}: {e}")
        return False, None, None

    # Start clone via manager
    try:
        success, bot_username, bot_name = await clone_manager.start_clone(user_id, token, bot_id)
        if success:
            return True, bot_username, bot_name
        return False, None, None
    except Exception as e:
        LOGGER.error(f"Error starting clone for user {user_id}: {e}\n{traceback.format_exc()}")
        return False, None, None

async def delete_clone(user_id):
    try:
        clone_info = await clone_db.find_one({"_id": user_id})
        if clone_info and clone_info.get("bot_id"):
            bot_id = clone_info["bot_id"]
            await db.users.update_many({"bot_ids": bot_id}, {"$pull": {"bot_ids": bot_id}})
            await db.chats.update_many({"bot_ids": bot_id}, {"$pull": {"bot_ids": bot_id}})
        
        await stop_clone_client(user_id)
        await clone_db.delete_one({"_id": user_id})
        LOGGER.info(f"Deleted clone for user {user_id}")
        return True
    except Exception as e:
        LOGGER.error(f"Error deleting clone for user {user_id}: {e}")
        return False

async def stop_clone_client(user_id):
    await clone_manager.stop_clone(user_id)

async def clone(user_id, token, bot_id):
    success, bot_username, bot_name = await create_clone_client(user_id, token, bot_id)
    
    if not success:
        if bot_username == "expired":
            await delete_clone(user_id)
            return "expired", None, None
        elif bot_username == "invalid":
            return "invalid", None, None
        return "error", None, None
    
    return "success", bot_username, bot_name

async def clone_start_up():
    LOGGER.info("Starting existing clones...")
    try:
        all_users = await clone_db.find({}).to_list(length=None)
        
        if not all_users:
            LOGGER.info("No clones to start")
            return
        
        started = 0
        for index, user in enumerate(all_users):
            try:
                user_id = user["_id"]
                token = user.get("token")
                if not token:
                    continue

                bot_id = user.get("bot_id")
                if not bot_id:
                    try:
                        bot_id = int(token.split(':')[0])
                        await clone_db.update_one({"_id": user_id}, {"$set": {"bot_id": bot_id}})
                    except:
                        await clone_db.delete_one({"_id": user_id})
                        continue

                if index > 0:
                    await asyncio.sleep(2) # Reduced delay since we are not spawning processes
                
                result, _, _ = await clone(user_id, token, bot_id)
                if result in ["expired", "invalid"]:
                    await clone_db.delete_one({"_id": user_id})
                elif result == "success":
                    started += 1
            except asyncio.CancelledError:
                LOGGER.info(f"Clone startup cancelled at user {user_id}")
                raise
            except Exception as e:
                LOGGER.error(f"Error starting clone for user {user_id}: {e}")
                continue
        
        LOGGER.info(f"Started {started} clones")
    except asyncio.CancelledError:
        LOGGER.info("Clone startup cancelled")
        raise
    except Exception as e:
        LOGGER.error(f"Error in clone_start_up: {e}")

@register(pattern="clone")
async def clone_bot(event):
    if getattr(event.client, "is_clone", False):
        return await event.reply("This feature is only available for the original bot.")
    if not event.is_private:
        return await event.reply("Please clone **Emilia** in your private chat.")
    
    user_id = event.sender_id
    if await clone_db.find_one({"_id": user_id}):
        return await event.reply(
            "You have already cloned **Emilia**. If you want to delete the clone, use `/deleteclone <bottoken>`"
        )
    
    if len(event.text.split()) == 1:
        return await event.reply(
            "Please provide the bot token from @BotFather in order to clone **Emilia**.\n**Example**: `/clone 219218219:jksswq`"
        )
    
    if await clone_db.count_documents({}) > CLONE_LIMIT:
        return await event.reply(f"Clones have reached the default limit {CLONE_LIMIT} for this bot. Please contact @{SUPPORT_CHAT} to clone this bot.")
    
    token = event.text.split(None, 1)[1]
    try:
        bot_id = int(token.split(':')[0])
    except:
        return await event.reply("Invalid bot token provided.")
    
    if await clone_db.find_one({"token": token}):
        return await event.reply("The same bot token has been used to clone **Emilia**. Please use a different bot token.")
    
    wait = await event.reply("Creating your clone bot. Please wait...")
    
    try:
        result, bot_username, bot_name = await clone(user_id, token, bot_id)
        
        if result == "expired":
            await wait.delete()
            return await event.reply("The bot token you provided is expired. Please provide the correct bot token.")
        elif result == "invalid":
            await wait.delete()
            return await event.reply("The bot token you provided is invalid. Please provide the correct bot token. Perhaps you forgot to remove [] or <> around the token?")
        elif result == "error":
            await wait.delete()
            return await event.reply("An error occurred while creating your clone. Please try again or contact support @SpiralTechDivision.")
        elif result == "success":
            await clone_db.update_one(
                {"_id": user_id},
                {"$set": {
                    "_id": user_id,
                    "token": token,
                    "bot_id": bot_id,
                    "bot_username": bot_username,
                    "bot_name": bot_name
                }},
                upsert=True,
            )
            await wait.edit(
                f"🎉 **Clone created successfully!**\n\n"
                f"**Bot Name:** {bot_name}\n"
                f"**Bot Username:** @{bot_username}\n\n"
                f"Your bot is **now live** and ready to use! Add it to your groups and assign admin privileges.\n\n"
                f"If you want to delete the clone, use `/deleteclone {token}`"
            )
    except Exception as e:
        LOGGER.error(f"Clone error: {e}")
        await wait.delete()
        await event.reply("An error occurred while cloning **Emilia**. Please try again or contact support @SpiralTechDivision.")

@register(pattern="deleteclone")
async def delete_cloned(event):
    if getattr(event.client, "is_clone", False):
        return await event.reply("This feature is only available in the original bot.")
    if not event.is_private:
        return await event.reply("Please delete Emilia's clone in your private chat.")
    
    user_id = event.sender_id
    check = await clone_db.find_one({"_id": user_id})
    if not check:
        return await event.reply(
            "You have not cloned **Emilia** yet. If you want to clone it, use `/clone <bottoken>`"
        )
    
    if len(event.text.split()) == 1:
        return await event.reply(
            "Please provide the bot token from @BotFather in order to delete the cloned **Emilia**. Example: `/deleteclone 219218219:jksswq`"
        )
    
    token = event.text.split(None, 1)[1]
    if check["token"] != token:
        return await event.reply(
            "The bot token you provided is incorrect. Please provide the correct bot token."
        )
    
    wait = await event.reply("Stopping your clone bot...")
    
    try:
        if await delete_clone(user_id):
            await wait.edit(
                "**Clone deleted successfully!**\n\n"
                "Your clone bot has been **stopped** and removed from our servers.\n"
                "You can create a new clone immediately if needed."
            )
        else:
            await wait.edit("An error occurred while deleting your clone. Please try again or contact support.")
    except Exception as e:
        LOGGER.error(f"Delete error: {e}")
        await wait.edit("An error occurred while deleting your clone. Please try again or contact support.")

@register(pattern="setstartpic")
async def set_startpic(event):
    if not getattr(event.client, "is_clone", False):
        return await event.reply("This feature is only available in cloned bots. Learn more about cloning Emilia by using `/help Clone`.")

    me = await event.client.get_me()
    clone_info = await get_clone_info_by_bot_id(me.id)
    
    if not clone_info or event.sender_id != clone_info.get("_id"):
        return await event.reply("You are not authorized to set the start picture for this bot.")

    reply_message = await event.get_reply_message()
    if reply_message and reply_message.media:
        await startpic.update_one(
            {"bot_id": me.id}, 
            {"$set": {"file_id": reply_message.media.file_id, "user_id": clone_info["_id"], "token": clone_info["token"]}}, 
            upsert=True
        )
        await event.reply(
            "**Start picture updated successfully!**\n\n"
            "The new start picture will be used immediately for your clone bot."
        )
    else:
        args = event.text.split(None, 1)
        if len(args) < 2:
            return await event.reply("Please provide a valid image URL. Example: `/setstartpic <image_url>`")
        
        url = args[1]
        if not url.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return await event.reply("The url you provided is not an image url. Please provide a valid image url. It should end with `.jpg`, `.jpeg`, `.png`, or `.webp`.")
        
        await startpic.update_one(
            {"bot_id": me.id}, 
            {"$set": {"url": url, "user_id": clone_info["_id"], "token": clone_info["token"]}}, 
            upsert=True
        )
        await event.reply(
            f"**Start picture updated successfully!**\n\n"
            f"The new start picture will be used immediately for your clone bot.\n"
            f"**Preview URL:** {url}"
        )

@register(pattern="broadcast")
async def broadcast(event):
    if not getattr(event.client, "is_clone", False):
        return await event.reply("**Broadcast is only available on cloned bots**\n\nPlease use your cloned bot to broadcast messages.")
    
    if not event.reply_to_msg_id:
        return await event.reply("Please reply to a message to broadcast it!")
    
    me = await event.client.get_me()
    bot_id = me.id
    clone_info = await get_clone_info_by_bot_id(bot_id)
    
    if not clone_info or event.sender_id != clone_info["_id"]:
        return await event.reply("You are not authorized to use this command.")
    
    args = event.text.split(None, 1)
    if len(args) < 2 or args[1].lower() not in ["-all", "-users", "-chats"]:
        user_count = await db.users.count_documents({"bot_ids": bot_id})
        chat_count = await db.chats.count_documents({"bot_ids": bot_id})
        return await event.reply(
            f"Please provide a mode: `/broadcast -all`, `/broadcast -users`, or `/broadcast -chats`\n\n"
            f"**Users**: {user_count}\n"
            f"**Chats**: {chat_count}"
        )
    
    mode = args[1].lower()
    reply = await event.get_reply_message()
    wait = await event.reply("Starting broadcast...")
    
    try:
        if mode == "-all":
            us, uf = await broadcast_to_users(bot_id, reply, event.client)
            cs, cf = await broadcast_to_chats(bot_id, reply, event.client)
            await wait.edit(
                f"**Broadcast Complete**\n\n"
                f"Users: {us} success, {uf} failed\n"
                f"Chats: {cs} success, {cf} failed"
            )
        elif mode == "-users":
            s, f = await broadcast_to_users(bot_id, reply, event.client)
            await wait.edit(f"**User Broadcast Complete**\n\nUsers: {s} success, {f} failed")
        else:
            s, f = await broadcast_to_chats(bot_id, reply, event.client)
            await wait.edit(f"**Chat Broadcast Complete**\n\nChats: {s} success, {f} failed")
    except Exception as e:
        LOGGER.error(f"Broadcast error: {e}")
        await wait.edit(f"Broadcast failed: {str(e)}")

async def broadcast_to_users(bot_id, message, client):
    cursor = db.users.find({"bot_ids": bot_id}, {"user_id": 1})
    success, failed = 0, 0
    
    async for doc in cursor:
        uid = doc["user_id"]
        try:
            await client.forward_messages(uid, message)
            success += 1
            await asyncio.sleep(0.05)
        except errors.UserIsBlockedError:
            await db.users.update_one({"user_id": uid}, {"$pull": {"bot_ids": bot_id}})
            failed += 1
        except errors.FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except:
            failed += 1
    
    return success, failed

async def broadcast_to_chats(bot_id, message, client):
    cursor = db.chats.find({"bot_ids": bot_id}, {"chat_id": 1})
    success, failed = 0, 0
    
    async for doc in cursor:
        cid = doc["chat_id"]
        try:
            await client.forward_messages(cid, message)
            success += 1
            await asyncio.sleep(0.05)
        except (errors.ChatWriteForbiddenError, errors.UserNotParticipantError):
            await db.chats.update_one({"chat_id": cid}, {"$pull": {"bot_ids": bot_id}})
            failed += 1
        except errors.FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except:
            failed += 1
    
    return success, failed

@auth(pattern="clonestatus")
async def clone_status(event):
    if not clone_manager.clones:
        return await event.reply("No active clone clients running.")
    
    status_msg = "**Active Clone Clients Status**\n\n"
    for user_id, info in clone_manager.clones.items():
        status_msg += f"**User ID**: `{user_id}`\n"
        status_msg += f"**Bot**: @{info.get('bot_username', 'Unknown')} ({info.get('bot_name', 'Unknown')})\n"
        status_msg += f"**Status**: Online\n\n"
    
    status_msg += f"**Total Active Clones**: {len(clone_manager.clones)}"
    await event.reply(status_msg)

async def shutdown_all_clones():
    await clone_manager.stop_all_clones()