import asyncio
from asyncio import sleep
from telethon import TelegramClient, errors
import sys
import os
import logging
import traceback

from Emilia import API_HASH, API_ID, LOGGER, db, DEV_USERS, CLONE_LIMIT, SUPPORT_CHAT, IS_CLONE
from Emilia.custom_filter import register, auth

clone_db = db.clone
timer = db.timer
startpic = db.startpic
user_db = db.users
chat_db = db.chats

active_clone_clients = {}

_PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))  # .../Emilia
_REPO_ROOT = os.path.abspath(os.path.join(_PACKAGE_DIR, os.pardir))  # repo root containing the Emilia package
_LOGS_DIR = os.path.join(_REPO_ROOT, "clone_logs")
os.makedirs(_LOGS_DIR, exist_ok=True)

async def get_clone_info_by_bot_id(bot_id):
    """Get clone info from database using bot_id"""
    return await clone_db.find_one({"bot_id": bot_id})

@auth(pattern="stats")
async def stats_(event):
    users = await db.users.count_documents({})
    chats = await db.chats.count_documents({})
    bots = await clone_db.count_documents({})
    active_clones = len(active_clone_clients)
    
    message = (
        f"**Bot Statistics**\n\n"
        f"**Chats**: {chats}\n"
        f"**Users**: {users}\n"
        f"**Cloned Bots in Database**: {bots}\n"
        f"**Active Clone Clients**: {active_clones}\n\n"
    )
    await event.reply(message)


async def create_clone_client(user_id, token, bot_id):
    """Create and start a new clone client as a subprocess."""
    try:
        temp_client = TelegramClient(None, API_ID, API_HASH)
        
        await temp_client.start(bot_token=token)
        bot = await temp_client.get_me()
        bot_username = bot.username
        bot_name = bot.first_name
        await temp_client.disconnect()

    except errors.AccessTokenExpiredError:
        LOGGER.error(f"Bot token expired for user {user_id}")
        return False, "expired", None
    except errors.AccessTokenInvalidError:
        LOGGER.error(f"Invalid bot token for user {user_id}")
        return False, "invalid", None
    except Exception as e:
        LOGGER.error(f"Error creating clone client for user {user_id}: {e}")
        return False, None, None

    try:
        env = os.environ.copy()
        env["EMILIA_IS_CLONE"] = "true"
        env["EMILIA_TOKEN"] = token
        env["EMILIA_OWNER_ID"] = str(user_id)
        env["PYTHONUNBUFFERED"] = "1"

        # Prepare per-clone log files to capture subprocess output for debugging
        stdout_path = os.path.join(_LOGS_DIR, f"clone_{user_id}.out.log")
        stderr_path = os.path.join(_LOGS_DIR, f"clone_{user_id}.err.log")
        stdout_f = open(stdout_path, "ab", buffering=0)
        stderr_f = open(stderr_path, "ab", buffering=0)

        # Preflight diagnostics
        exe_ok = os.path.isfile(sys.executable) and os.access(sys.executable, os.X_OK)
        pkg_dir = _PACKAGE_DIR
        pkg_ok = os.path.isdir(pkg_dir) and os.path.isfile(os.path.join(pkg_dir, "__init__.py"))
        main_ok = os.path.isfile(os.path.join(pkg_dir, "__main__.py"))
        cwd_ok = os.path.isdir(_REPO_ROOT)
        LOGGER.info(
            f"Clone preflight | exe_ok={exe_ok} cwd_ok={cwd_ok} pkg_ok={pkg_ok} main_ok={main_ok}"
        )
        if not exe_ok or not cwd_ok or not pkg_ok or not main_ok:
            msg = (
                f"Preflight failed: exe={sys.executable} exists={os.path.isfile(sys.executable)} x_ok={os.access(sys.executable, os.X_OK)}, "
                f"cwd={_REPO_ROOT} exists={cwd_ok}, pkg_dir={pkg_dir} ok={pkg_ok}, main={os.path.join(pkg_dir, '__main__.py')} ok={main_ok}"
            )
            LOGGER.error(msg)
            try:
                stderr_f.write((msg + "\n").encode())
            except Exception:
                pass
            stdout_f.close()
            stderr_f.close()
            return False, None, None

        LOGGER.info(
            f"Starting clone subprocess for user {user_id} | bot @{bot_username} | "
            f"python: {sys.executable} | cwd: {_REPO_ROOT}"
        )

        # Subprocess management with Python 3.13+ compatibility
        try:
            if sys.version_info >= (3, 13):
                # Python 3.13+ - child watchers are completely removed
                LOGGER.info("Using Python 3.13+ subprocess management.")
                # We'll use subprocess.Popen directly instead of asyncio.create_subprocess_exec
            elif sys.version_info >= (3, 12):
                # Python 3.12 - subprocess management is automatic
                LOGGER.info("Using Python 3.12+ subprocess management.")
            elif os.name == "posix":
                # Python < 3.12 - use child watcher on POSIX systems
                policy = asyncio.get_event_loop_policy()
                setcw = getattr(policy, "set_child_watcher", None)
                getcw = getattr(policy, "get_child_watcher", None)
                watcher = None
                if getcw:
                    try:
                        watcher = getcw()
                    except NotImplementedError:
                        watcher = None
                if setcw and watcher is None:
                    try:
                        watcher = asyncio.SafeChildWatcher()
                    except Exception:
                        watcher = asyncio.ThreadedChildWatcher()
                    setcw(watcher)
                    LOGGER.info("Installed child watcher locally before spawning clone subprocess.")
        except Exception as _cw_err:
            LOGGER.error(f"Failed to ensure subprocess management setup: {_cw_err}")

        # Use different subprocess creation methods based on Python version
        if sys.version_info >= (3, 13):
            # For Python 3.13+, use subprocess.Popen directly
            import subprocess
            
            process_args = [
                sys.executable,
                "-u",
                "-m", 
                "Emilia"
            ]
            
            popen = subprocess.Popen(
                process_args,
                env=env,
                cwd=_REPO_ROOT,
                stdout=stdout_f,
                stderr=stderr_f,
                start_new_session=True
            )
            
            class AsyncProcessWrapper:
                def __init__(self, popen):
                    self.popen = popen
                    self.pid = popen.pid
                    self.returncode = None
                
                async def wait(self):
                    # Non-blocking wait
                    while self.popen.poll() is None:
                        await asyncio.sleep(0.1)
                    self.returncode = self.popen.returncode
                    return self.returncode
                
                def terminate(self):
                    try:
                        self.popen.terminate()
                    except:
                        pass
                
                def kill(self):
                    try:
                        self.popen.kill()
                    except:
                        pass
            
            process = AsyncProcessWrapper(popen)
        else:
            # Use asyncio.create_subprocess_exec for Python < 3.13
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                "-m",
                "Emilia",
                env=env,
                cwd=_REPO_ROOT,
                stdout=stdout_f,
                stderr=stderr_f,
            )

        active_clone_clients[user_id] = {
            'process': process,
            'token': token,
            'bot_id': bot_id,
            'bot_username': bot_username,
            'bot_name': bot_name,
            'stdout_log': stdout_f,
            'stderr_log': stderr_f,
        }

        LOGGER.info(f"Successfully started clone process for user {user_id} with bot @{bot_username}")
        return True, bot_username, bot_name
    except Exception as e:
        tb = traceback.format_exc()
        LOGGER.error(f"Error starting clone subprocess for user {user_id}: {e!r}\n{tb}")
        # Also write traceback into the per-clone error log if possible
        try:
            if 'stderr_f' in locals() and stderr_f:
                stderr_f.write((tb + "\n").encode())
        except Exception:
            pass
        # Ensure we don't leak file descriptors on failure
        try:
            stdout_f.close()
        except Exception:
            pass
        try:
            stderr_f.close()
        except Exception:
            pass
        return False, None, None



async def delete_clone(user_id):
    """Delete a clone from the database and stop the client if running"""
    try:
        await stop_clone_client(user_id)
        
        await clone_db.delete_one({"_id": user_id})
        
        LOGGER.info(f"Successfully deleted clone for user {user_id}")
        return True
    except Exception as e:
        LOGGER.error(f"Error deleting clone for user {user_id}: {e}")
        return False

async def stop_clone_client(user_id):
    """Stop and remove a clone client from memory"""
    if user_id in active_clone_clients:
        try:
            process = active_clone_clients[user_id]['process']
            process.terminate()
            await process.wait()
            # Close any log files if present
            for key in ('stdout_log', 'stderr_log'):
                fobj = active_clone_clients[user_id].get(key)
                try:
                    if fobj:
                        fobj.close()
                except Exception:
                    pass
            del active_clone_clients[user_id]
            LOGGER.info(f"Successfully stopped clone client for user {user_id}")
        except Exception as e:
            LOGGER.error(f"Error stopping clone client for user {user_id}: {e}")


async def clone(user_id, token, bot_id):
    """New in-memory clone implementation"""
    LOGGER.info(f"Creating in-memory clone for user {user_id}")
    
    success, bot_username, bot_name = await create_clone_client(user_id, token, bot_id)
    
    if not success:
        if bot_username == "expired":
            await delete_clone(user_id)
            return "expired", None, None
        elif bot_username == "invalid":
            return "invalid", None, None
        else:
            return "error", None, None
    
    LOGGER.info(f"Clone successfully created for user {user_id} - Bot: @{bot_username} ({bot_name})")
    return "success", bot_username, bot_name


async def clone_start_up():
    """Initialize all existing clones on startup"""
    LOGGER.info("Starting up existing clones...")
    all_users = await clone_db.find({}).to_list(length=None)
    
    tasks = []
    
    started_clones = set()
    for index, user in enumerate(all_users):
        user_id = user["_id"]
        if user_id not in started_clones:
            token = user.get("token")
            if not token:
                LOGGER.warning(f"User {user_id} is missing a token. Skipping.")
                continue

            bot_id = user.get("bot_id")
            if not bot_id:
                LOGGER.warning(f"bot_id not found for user {user_id}. Extracting from token.")
                try:
                    bot_id = int(token.split(':')[0])
                    await clone_db.update_one({"_id": user_id}, {"$set": {"bot_id": bot_id}})
                    LOGGER.info(f"Successfully extracted and updated bot_id for user {user_id}.")
                except (ValueError, IndexError):
                    LOGGER.error(f"Invalid token format for user {user_id}. Deleting invalid clone.")
                    await clone_db.delete_one({"_id": user_id})
                    continue

            delay = index * 5
            task = asyncio.create_task(clone_with_delay(user_id, token, bot_id, delay))
            tasks.append(task)
            started_clones.add(user_id)
    
    if tasks:
        await asyncio.gather(*tasks)
    LOGGER.info(f"Finished starting up {len(started_clones)} clones")

async def clone_with_delay(user_id, token, bot_id, delay):
    """Start a clone with a delay to avoid rate limits"""
    await asyncio.sleep(delay)
    result, _, _ = await clone(user_id, token, bot_id)
    if result in ["expired", "invalid", "error"]:
        LOGGER.error(f"Failed to start clone for user {user_id}: {result}")
        if result in ["expired", "invalid"]:
            await clone_db.delete_many({"_id": user_id})

@register(pattern="clone")
async def clone_bot(event):
    if IS_CLONE:
        return await event.reply("This feature is only available for the original bot.")
    if not event.is_private:
        return await event.reply("Please clone **Emilia** in your private chat.")
    user_id = event.sender_id
    check = await clone_db.find_one({"_id": user_id})
    if check:
        return await event.reply(
            "You have already cloned **Emilia**. If you want to delete the clone, use `/deleteclone <bottoken>`"
        )
    if len(event.text.split()) == 1:
        return await event.reply(
            "Please provide the bot token from @BotFather in order to clone **Emilia**.\n**Example**: `/clone 219218219:jksswq`"
        )
    bots = await clone_db.count_documents({})
    token = event.text.split(None, 1)[1]
    try:
        bot_id = int(token.split(':')[0])
    except (ValueError, IndexError):
        return await event.reply("Invalid bot token provided.")

    if (bots > CLONE_LIMIT):
        return await event.reply(f"Clones have reached the default limit {CLONE_LIMIT} for this bot. Please contact @{SUPPORT_CHAT} to clone this bot.")
    
    check_token = await clone_db.find_one({"token": token})
    if check_token:
        return await event.reply("The same bot token has been used to clone **Emilia**. Please use a different bot token.")
    
    wait = await event.reply("Creating your clone bot. Please wait...")
    
    try:
        result, bot_username, bot_name = await clone(user_id, token, bot_id)
        
        if result == "expired":
            await wait.delete()
            await event.reply("The bot token you provided is expired. Please provide the correct bot token.")
            return
        elif result == "invalid":
            await wait.delete()
            await event.reply("The bot token you provided is invalid. Please provide the correct bot token. Perhaps you forgot to remove [] or <> around the token?")
            return
        elif result == "error":
            await wait.delete()
            await event.reply("An error occurred while creating your clone. Please try again or contact support @SpiralTechDivision.")
            return
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
        else:
            await wait.delete()
            await event.reply("An unexpected error occurred. Please try again or contact support @SpiralTechDivision.")
            
    except Exception as e:
        LOGGER.error(f"An error occurred while cloning: {e}")
        await wait.delete()
        await event.reply("An error occurred while cloning **Emilia**. Please try again or contact support @SpiralTechDivision.")

@register(pattern="deleteclone")
async def delete_cloned(event):
    if IS_CLONE:
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
        deleted = await delete_clone(user_id)
        if deleted:
            await wait.edit(
                "**Clone deleted successfully!**\n\n"
                "Your clone bot has been **stopped** and removed from our servers.\n"
                "You can create a new clone immediately if needed."
            )
        else:
            await wait.edit("An error occurred while deleting your clone. Please try again or contact support.")
        
    except Exception as e:
        LOGGER.error(f"Error deleting clone for user {user_id}: {e}")
        await wait.edit("An error occurred while deleting your clone. Please try again or contact support.")


async def delete_clone_internal(user_id):
    """Internal function to delete a clone (used for expired tokens etc.)"""
    try:
        # Find and disconnect the specific client immediately
        if user_id in active_clone_clients:
            client_info = active_clone_clients[user_id]
            process = client_info['process']
            bot_username = client_info.get('bot_username', 'Unknown')
            
            # Terminate the process immediately
            process.terminate()
            await process.wait()
            
            for key in ('stdout_log', 'stderr_log'):
                fobj = client_info.get(key)
                try:
                    if fobj:
                        fobj.close()
                except Exception:
                    pass
            
            # Remove from active clients dictionary
            del active_clone_clients[user_id]
            
            LOGGER.info(f"Instantly disconnected clone client for user {user_id} (@{bot_username})")
        
        # Remove from database
        await clone_db.delete_many({"_id": user_id})
        
        LOGGER.info(f"Deleted the cloned bot for user {user_id} successfully.")
        
    except Exception as e:
        LOGGER.error(f"Error in delete_clone_internal for user {user_id}: {e}")


@register(pattern="setstartpic")
async def set_startpic(event):
    if not IS_CLONE:
        return await event.reply("This feature is only available in cloned bots. Learn more about cloning Emilia by using `/help Clone`.")

    me = await event.client.get_me()
    current_bot_id = me.id
    
    clone_info = await get_clone_info_by_bot_id(current_bot_id)
    if not clone_info:
        return await event.reply("Clone information not found. Please contact support.")
    
    user_id = clone_info.get("_id")
    if not user_id or event.sender_id != user_id:
        return await event.reply("You are not authorized to set the start picture for this bot.")

    reply_message = await event.get_reply_message()
    if reply_message and reply_message.media:
        # If replying to a media message, get the file ID
        file_id = reply_message.media.file_id
        
        await startpic.update_one(
            {"bot_id": current_bot_id}, 
            {"$set": {"file_id": file_id, "user_id": clone_info["_id"], "token": clone_info["token"]}}, 
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
        
        # Store using bot_id for better identification
        await startpic.update_one(
            {"bot_id": current_bot_id}, 
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
    if not event.reply_to_msg_id:
        return await event.reply("Please reply to a message to broadcast it!")
    
    if not IS_CLONE:
        return await event.reply("**Broadcast is only available on cloned bots**\n\nPlease use your cloned bot to broadcast messages.")
    
    me = await event.client.get_me()
    current_bot_id = me.id

    clone_info = await get_clone_info_by_bot_id(current_bot_id)
    if not clone_info:
        return await event.reply("Could not identify the clone owner!")
    
    clone_owner_id = clone_info["_id"]
    if event.sender_id != clone_owner_id:
        return await event.reply("You are not authorized to use this command.")

    reply = await event.get_reply_message()
    if not reply:
        return await event.reply("Please reply to a message to broadcast.")

    user_id = clone_info["_id"]
    client_data = active_clone_clients.get(user_id)

    if not client_data:
        return await event.reply("Could not retrieve clone client details. Please restart the bot or contact support.")

    bot_username = client_data.get('bot_username')
    
    async with TelegramClient(None, API_ID, API_HASH) as clone_client:
        await clone_client.start(bot_token=clone_info['token'])

        args = event.text.split(None, 1)
        if len(args) > 1:
            mode = args[1].lower()
            if mode == "-all":
                await targeted_user_broadcast(event, reply, clone_client, bot_username)
                await targeted_chat_broadcast(event, reply, clone_client, bot_username)
            elif mode == "-users":
                await targeted_user_broadcast(event, reply, clone_client, bot_username)
            elif mode == "-chats":
                await targeted_chat_broadcast(event, reply, clone_client, bot_username)
            else:
                await event.reply("Invalid flag. Use `/broadcast -all` or `/broadcast -users` or `/broadcast -chats`")
        else:
            await event.reply("Please provide a mode for broadcasting: `-all`, `-users`, or `-chats`.")

async def get_all_chats(client):
    """Yield chats where the bot is a member one by one."""
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            yield dialog.entity

async def targeted_user_broadcast(event, reply, clone_client, bot_username):
    """Broadcast to users who have started the bot"""
    user_count = 0
    try:
        # Get all dialogs for the specific clone client
        async for dialog in clone_client.iter_dialogs():
            # Only send to private chats (users)
            if dialog.is_user and not dialog.entity.bot:
                try:
                    await clone_client.forward_messages(dialog.id, reply)
                    user_count += 1
                except errors.FloodWaitError as e:
                    LOGGER.warning(f"FloodWait for {e.seconds} seconds when broadcasting to user {dialog.id}")
                    await sleep(e.seconds)
                    continue
                except Exception as e:
                    LOGGER.debug(f"Failed to broadcast to user {dialog.id}: {e}")
                    continue
        
        await event.reply(f"Broadcasted the message to {user_count} users successfully via @{bot_username}.")
    except Exception as e:
        LOGGER.error(f"Error in targeted_user_broadcast: {e}")
        await event.reply(f"Error occurred during user broadcast via @{bot_username}: {str(e)}")

async def targeted_chat_broadcast(event, reply, clone_client, bot_username):
    """Broadcast to chats where the bot is present"""
    chats = await get_all_chats(clone_client)
    failed = 0
    chat_count = 0
    for chat in chats:
        try:
            await clone_client.forward_messages(chat.id, reply)
            chat_count += 1
        except errors.FloodWaitError as e:
            failed += 1
            LOGGER.warning(f"FloodWait for {e.seconds} seconds when broadcasting to chat {chat.id}")
            await sleep(e.seconds)
            continue
        except Exception as e:
            failed += 1
            LOGGER.debug(f"Failed to broadcast to chat {chat.id}: {e}")
            continue
    
    success = chat_count > 0
    if success:
        await event.reply(f"Broadcasted the message to {chat_count} chats successfully via @{bot_username}.")
    else:
        await event.reply(f"Failed to broadcast the message to chats. Total failed: {failed}")

@auth(pattern="clonestatus")
async def clone_status(event):
    if not active_clone_clients:
        return await event.reply("No active clone clients running.")
    
    status_msg = "**🤖 Active Clone Clients Status**\n\n"
    
    for user_id, clone_info in active_clone_clients.items():
        bot_username = clone_info.get('bot_username', 'Unknown')
        bot_name = clone_info.get('bot_name', 'Unknown')
        status_msg += f"**User ID**: `{user_id}`\n"
        status_msg += f"**Bot**: @{bot_username} ({bot_name})\n"
        status_msg += f"**Status**: Online\n\n"
    
    status_msg += f"**Total Active Clones**: {len(active_clone_clients)}"
    
    await event.reply(status_msg)



async def shutdown_all_clones():
    """Gracefully shutdown all active clone clients on main bot shutdown"""
    if not active_clone_clients:
        return
        
    LOGGER.info(f"Shutting down {len(active_clone_clients)} active clone clients...")
    
    user_ids = list(active_clone_clients.keys())
    tasks = [stop_clone_client(uid) for uid in user_ids]
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    
    active_clone_clients.clear()
    LOGGER.info("All clone clients have been shut down gracefully.")


async def restart_clone_client(user_id):
    """Restart a specific clone client"""
    if user_id not in active_clone_clients:
        return False, "Clone not found"
    
    clone_data = active_clone_clients[user_id]
    token = clone_data['token']
    bot_id = clone_data['bot_id']
    
    await stop_clone_client(user_id)
    
    success, new_bot_username, new_bot_name = await create_clone_client(user_id, token, bot_id)
    
    if success:
        LOGGER.info(f"Successfully restarted clone client for user {user_id}")
        await clone_db.update_one(
            {"_id": user_id},
            {"$set": {
                "bot_username": new_bot_username,
                "bot_name": new_bot_name
            }},
            upsert=False
        )
        return True, "Restarted successfully"
    else:
        LOGGER.error(f"Failed to restart clone client for user {user_id}")
        return False, "Failed to restart"
