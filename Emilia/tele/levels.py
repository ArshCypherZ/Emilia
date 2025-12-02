import datetime as ds
import time
import asyncio

from telethon import Button, events

import Emilia.strings as strings
from Emilia import LOGGER, db, telethn
from Emilia.custom_filter import callbackquery, register
from Emilia.functions.admins import get_time, is_admin
from Emilia.utils.decorators import *
from Emilia.utils.cache import SimpleCache

users_collection = db.chatlevels
first_name = db.first_name
level = db.onofflevel

ranks = [
    {"name": "Elf", "min_points": 0},
    {"name": "Oni", "min_points": 500},
    {"name": "Giant", "min_points": 1000},
    {"name": "Evil Eye", "min_points": 10000},
    {"name": "Werewolf", "min_points": 50000},
    {"name": "DragonKin", "min_points": 100000},
]

levels = 1000

# Lightweight in-memory caches and buffers
_level_cache = SimpleCache(default_ttl=120)  # per-chat toggle
_name_cache = SimpleCache(default_ttl=300)   # per-user first_name
_points_buffer = {}
_lastmsg_buffer = {}
_buffer_flush_inflight = False
_last_flush = 0.0
_MIN_FLUSH_INTERVAL = 1.0  # seconds
_MAX_BUFFER_OPS = 200

# Track if periodic flusher has been started to avoid duplicates
_periodic_flush_started = False

async def _get_level_on(chat_id: int) -> bool:
    key = f"lvl:{chat_id}"
    val = await _level_cache.get(key)
    if val is not None:
        return val
    doc = await level.find_one({"chat_id": chat_id})
    exists = doc is not None and not doc.get("disabled", False)
    await _level_cache.set(key, exists, ttl=120)
    return exists

async def _get_first_name(user_id: int) -> str:
    key = f"name:{user_id}"
    val = await _name_cache.get(key)
    if val is not None:
        return val
    doc = await first_name.find_one({"user_id": user_id})
    name = (doc or {}).get("first_name", "Unknown")
    await _name_cache.set(key, name, ttl=300)
    return name

async def _flush_points_and_lastmsg():
    global _points_buffer, _lastmsg_buffer, _buffer_flush_inflight, _last_flush
    if _buffer_flush_inflight:
        return
    _buffer_flush_inflight = True
    try:
        # Merge increments and lastmsg into a single update per (user_id, chat_id)
        merged = {}
        for (user_id, chat_id), inc in list(_points_buffer.items()):
            if not inc:
                continue
            key = (user_id, chat_id)
            entry = merged.setdefault(key, {"inc": 0, "set": {}})
            entry["inc"] += inc
        for (user_id, chat_id), ts in list(_lastmsg_buffer.items()):
            key = (user_id, chat_id)
            entry = merged.setdefault(key, {"inc": 0, "set": {}})
            entry["set"]["last_message_time"] = ts

        if merged:
            updates = []
            for (user_id, chat_id), spec in merged.items():
                update_doc = {}
                if spec["inc"]:
                    update_doc["$inc"] = {"points": spec["inc"]}
                if spec["set"]:
                    update_doc["$set"] = spec["set"]
                updates.append({
                    "q": {"user_id": user_id, "chat_id": chat_id},
                    "u": update_doc,
                    "upsert": True,
                    "multi": False,
                })
            try:
                # Use Motor's db.command to issue a single update command with many ops
                await db.command("update", users_collection.name, updates=updates, ordered=False)
            except Exception as e:
                LOGGER.error(f"levels flush command error: {e}")
        _points_buffer.clear()
        _lastmsg_buffer.clear()
        _last_flush = time.time()
    except Exception as e:
        LOGGER.error(f"levels flush error: {e}")
    finally:
        _buffer_flush_inflight = False

async def _schedule_flush(force: bool = False):
    try:
        total_ops = len(_points_buffer) + len(_lastmsg_buffer)
        if not force:
            if total_ops < _MAX_BUFFER_OPS and (time.time() - _last_flush) < _MIN_FLUSH_INTERVAL:
                return
        asyncio.create_task(_flush_points_and_lastmsg())
    except Exception:
        pass

async def flush_levels_buffers_now():
    """Public helper to force-flush buffers now."""
    await _flush_points_and_lastmsg()

async def start_levels_flush_task(interval_seconds: float = 5.0):
    """
    Start a periodic task that flushes level buffers at a low frequency.
    Safe to call multiple times; only starts once per process.
    """
    global _periodic_flush_started
    if _periodic_flush_started:
        return
    _periodic_flush_started = True

    async def _run():
        while True:
            try:
                await asyncio.sleep(max(1.0, float(interval_seconds)))
                await _flush_points_and_lastmsg()
            except Exception as e:
                try:
                    LOGGER.error(f"levels periodic flush error: {e}")
                except Exception:
                    pass

    asyncio.create_task(_run())

async def get_rank(points):
    for rank in ranks[::-1]:
        if points >= rank["min_points"]:
            return rank["name"]
    return "Gay"


async def read_last_collection_time_today(user_id, chat_id):
    try:
        user = await users_collection.find_one({"user_id": user_id, "chat_id": chat_id})
        collection_time = user.get("last_date")
    except Exception as e:
        LOGGER.error(f"Error reading last collection time: {e}")
        collection_time = None

    return ds.datetime.fromtimestamp(collection_time) if collection_time else None


async def can_collect_coins(user_id, chat_id):
    last_collection_time = await read_last_collection_time_today(user_id, chat_id)
    if last_collection_time is None:
        return (True, True)
    current_time = ds.datetime.now()
    time_since_last_collection = current_time - last_collection_time
    return (
        time_since_last_collection.total_seconds() >= 24 * 60 * 60,
        24 * 60 * 60 - time_since_last_collection.total_seconds(),
    )


async def increase_points(user_id, chat_id, points):
    # Ensure user exists in first_name collection for referencing later
    await first_name.update_one({"user_id": user_id}, {"$setOnInsert": {"user_id": user_id}}, upsert=True)

    # Targeted upsert without prior read; unique index exists on (chat_id,user_id)
    await users_collection.update_one(
        {"user_id": user_id, "chat_id": chat_id}, {"$inc": {"points": points}}, upsert=True
    )


async def get_leaderboard(chat_id):
    # Use Mongo sort + limit
    cursor = users_collection.find({"chat_id": chat_id}, {"_id": 0, "user_id": 1, "points": 1}).sort("points", -1).limit(10)
    return await cursor.to_list(length=10)


async def get_user_stats(user_id, chat_id):
    user_data = await users_collection.find_one(
        {"user_id": user_id, "chat_id": chat_id}, {"_id": 0, "points": 1}
    )
    if not user_data:
        return None
    points = user_data.get("points", 0)
    first_name1 = await _get_first_name(user_id)
    level_val = min(points // 10, levels)
    rank = await get_rank(points)
    return {"points": points, "first_name": first_name1, "level": level_val, "rank": rank}


async def is_flooding(user_id, chat_id):
    # use projected fields only
    user_data = await users_collection.find_one(
        {"user_id": user_id, "chat_id": chat_id}, {"_id": 0, "last_message_time": 1}
    )
    if user_data and "last_message_time" in user_data:
        current_time = time.time()
        last_message_time = user_data["last_message_time"]
        return (current_time - last_message_time) < 5
    return False


@register(pattern="leaderboard")
async def _leaderboard(event):
    if not event.is_group:
        return await event.reply("Leaderboard is only for group chats.")
    if not await _get_level_on(event.chat_id):
        return await event.reply(
            "Levelling system is not active in this chat. To turn it on use `/level on`"
        )
    chat_id = event.chat_id
    leaderboard = await get_leaderboard(chat_id)
    lmao = ""

    if leaderboard:
        lmao += "🏆 **Leaderboard** for this chat:\n\n"
        for idx, user in enumerate(leaderboard, start=1):
            points = user.get("points", 0)
            user_id = user.get("user_id")
            first_name1 = await _get_first_name(user_id)
            lmao += (
                f"{idx}. [{first_name1}](tg://user?id={user_id}) --> {points} points\n"
            )
        lmao += "\nUse /register to setup your names."
    else:
        lmao += (
            "No data for this chat. Try /register to register yourself in bot first!"
        )
    await event.reply(
        lmao, buttons=Button.inline("Global Leaderboard", data="gleaderboard_")
    )


@callbackquery(pattern="gleaderboard_")
async def gleaderboard(event):
    cursor = users_collection.find({}, {"_id": 0, "user_id": 1, "points": 1}).sort("points", -1).limit(10)
    sorted_players = await cursor.to_list(length=None)

    # Fetch the first_name for each user using cache
    for player in sorted_players:
        if "user_id" not in player:
            continue
        user_id = player["user_id"]
        player["first_name"] = await _get_first_name(user_id)

    gae = "🏆 **Global Leaderboard** 🏆\n\n"
    for rank, player in enumerate(sorted_players, start=1):
        name = player.get("first_name", "Unknown")
        points = player.get("points", 0)
        gae += f"{rank}. [{name}](tg://user?id={player.get('user_id', 'N/A')}) --> {points} points\n"

    await event.edit(gae)


@register(pattern="daily")
async def _daily(event):
    if not event.is_group:
        return await event.reply(
            "You can only claim your daily bonus of 100 points inside a group chat!"
        )
    if not await _get_level_on(event.chat_id):
        return await event.reply(
            "Levelling system is not active in this chat. To turn it on use `/level on`"
        )
    try:
        stats = await get_user_stats(event.sender_id, event.chat_id)
    except KeyError:
        stats = None
    if not stats:
        return await event.reply("Use /register to register yourself in bot first!")
    points = stats["points"]
    x, y = await can_collect_coins(event.sender_id, event.chat_id)
    if x is True:
        await users_collection.update_one(
            {"user_id": event.sender_id, "chat_id": event.chat_id},
            {"$set": {"points": points + 100}},
            upsert=True,
        )
        await users_collection.update_one(
            {"user_id": event.sender_id, "chat_id": event.chat_id},
            {"$set": {"last_date": ds.datetime.now().timestamp()}},
            upsert=True,
        )
        new_points = points + 100
        return await event.reply(
            f"Successfully claimed daily 100 points!\n**Current points**: {new_points}"
        )
    await event.reply(
        "You can claim your daily 100 points in around`{0}`".format((await get_time(y)))
    )


async def write_last_collection_time_weekly(user_id, chat_id, time):
    await users_collection.update_one(
        {"user_id": user_id, "chat_id": chat_id},
        {"$set": {"last_collection_weekly": time}},
        upsert=True,
    )


async def read_last_collection_time_weekly(user_id, chat_id):
    user = await users_collection.find_one({"user_id": user_id, "chat_id": chat_id})
    try:
        collection_time = user["last_collection_weekly"]
    except BaseException:
        collection_time = None
    if (collection_time):
        return ds.datetime.fromtimestamp(collection_time)
    else:
        return None


async def can_collect(user_id, chat_id):
    last_collection_time = await read_last_collection_time_weekly(user_id, chat_id)
    if last_collection_time is None:
        return (True, True)
    current_time = ds.datetime.now()
    time_since_last_collection = current_time - last_collection_time
    return (
        time_since_last_collection.total_seconds() >= 7 * 24 * 60 * 60,
        7 * 24 * 60 * 60 - time_since_last_collection.total_seconds(),
    )


@register(pattern="weekly")
async def _daily(event):
    if not event.is_group:
        return await event.reply(
            "You can only claim your daily bonus of 500 points inside a group chat!"
        )
    if not await _get_level_on(event.chat_id):
        return await event.reply(
            "Levelling system is not active in this chat. To turn it on use `/level on`"
        )
    try:
        stats = await get_user_stats(event.sender_id, event.chat_id)
    except KeyError:
        stats = None
    if not stats:
        return await event.reply("Use /register to register yourself in bot first!")
    points = stats["points"]
    x, y = await can_collect(event.sender_id, event.chat_id)
    if x is True:
        await users_collection.update_one(
            {"user_id": event.sender_id, "chat_id": event.chat_id},
            {"$set": {"points": points + 500}},
            upsert=True,
        )
        await write_last_collection_time_weekly(
            event.sender_id, event.chat_id, ds.datetime.now().timestamp()
        )
        new_points = points + 500
        return await event.reply(
            f"Successfully claimed weekly 500 points!\n**Current points**: {new_points}"
        )
    await event.reply(
        "You can claim your weekly 500 points in around`{0}`".format(
            (await get_time(y))
        )
    )


@register(pattern="rank")
async def userstats(event):
    if not event.is_group:
        return await event.reply(
            "You can only see your rank inside a specific group chat."
        )
    if not await _get_level_on(event.chat_id):
        return await event.reply(
            "Levelling system is not active in this chat. To turn it on use `/level on`"
        )
    user_id = event.sender_id
    chat_id = event.chat_id

    try:
        stats = await get_user_stats(user_id, chat_id)
    except KeyError:
        stats = None
    "https://api.akuari.my.id/canvas/rank?avatar=https://camo.githubusercontent.com/1ad4c22d443bd0a2f7fed1eebd75f8bd2f4c7616c8e8dc31f4797135896d525b/68747470733a2f2f692e6962622e636f2f31526d524c39642f494d472d32303231313130342d3130353230392d3438382e6a7067&username=Ari&needxp=939505&bg=https://telegra.ph/file/c8b84fff99a1914b4207d.png&level=284&currxp=23284&rank=https://i.ibb.co/Wn9cvnv/FABLED.png"
    if stats:
        response = f"**{stats['first_name']}'s Stats**:\n\n**Points Gained**: {stats['points']}\n**Level**: {stats['level']}\n**Rank**: {stats['rank']}"

    else:
        response = "Use /register to register your name first."

    await event.reply(response)


@register(pattern="register")
async def register_(event):
    if not event.is_group:
        return await event.reply(
            "Please register inside a group, each group will have it's seperate rankings."
        )
    if not await _get_level_on(event.chat_id):
        return await event.reply(
            "Levelling system is not active in this chat. To turn it on use `/level on`"
        )

    try:
        args: str = event.text.split(None, 1)[1]
    except IndexError:
        return await event.reply(
            "Use it like: /register PussySlayer69\n**Note**: You cannot change your name once it is registered."
        )

    if len(args) > 20:
        return await event.reply("Name too long, please try a shorter one")

    present = await first_name.find_one({"user_id": event.sender_id})
    if present and "first_name" in present:
        return await event.reply(
            "You are already registered. Please use /rank to see your user stats."
        )

    meow = await first_name.find_one({"first_name": args})
    if meow:
        return await event.reply(
            f"{args} has already been used by someone else. Please try some other name!"
        )

    # Idempotent set of first_name for the user
    await first_name.update_one(
        {"user_id": event.sender_id}, {"$set": {"first_name": args}}, upsert=True
    )
    return await event.reply(
        f"Successfully registered as {args}!\nUse /rank to see your stats."
    )


@register(pattern="rankings")
@exception
async def userstats(event):
    if not event.is_private:
        return await event.reply("Please use this command in my private chat.")
    response = """
The ranking system consists of multiple ranks, each with a name and a minimum number of points required to unlock that rank.

Here is a breakdown of each rank and its corresponding minimum points:

1. Rank: Elf
   - Minimum Points: 0
   - Description: The starting rank of the game. All players begin at this level.

2. Rank: Oni
   - Minimum Points: 500
   - Description: Players need to accumulate at least 500 points to unlock this rank. It represents a slightly higher level of achievement compared to the starting rank.

3. Rank: Giant
   - Minimum Points: 1000
   - Description: Players must reach a minimum of 1000 points to unlock this rank. It signifies progress and advancement in the game.

4. Rank: Evil Eye
   - Minimum Points: 10000
   - Description: Once players accumulate a minimum of 10000 points, they unlock this rank. It represents a significant achievement in the game and indicates a higher level of skill or dedication.

5. Rank: Werewolf
   - Minimum Points: 50000
   - Description: Upon reaching a minimum of 50000 points, players unlock the Werewolf rank. This rank signifies substantial progress and demonstrates a notable level of mastery in the game.

6. Rank: DragonKin
   - Minimum Points: 100000
   - Description: The highest rank in the game. Players need to accumulate a minimum of 100000 points to unlock this rank. It symbolizes exceptional skill and represents an elite level within the game.

Players start as Elves and can progress through the ranks by earning points. As they accumulate the required points, they unlock higher ranks, indicating their progression and growth within the game.

As the chat level game will get popular, we will add more levels and exciting features to it. Please contribute suggestions at @SpiralTechDivision
"""
    await event.reply(response)


@telethn.on(events.NewMessage)
async def handle_message(event):
    if not event.is_group:
        return
    if not event.text:
        return
    user_id = event.sender_id
    chat_id = event.chat_id

    if user_id == 5737513498:
        return

    if event.from_id:
        if not await _get_level_on(event.chat_id):
            return
        if not (await is_flooding(user_id, chat_id)):
            # buffer point inc and lastmsg update
            _points_buffer[(user_id, chat_id)] = _points_buffer.get((user_id, chat_id), 0) + 1
            _lastmsg_buffer[(user_id, chat_id)] = time.time()
            await _schedule_flush()
            # rank up check requires fresh points; read projected doc once
            user_data = await users_collection.find_one(
                {"user_id": user_id, "chat_id": chat_id}, {"_id": 0, "points": 1}
            )
            if user_data:
                pts = user_data.get("points", 0)
                for r in ranks[::-1]:
                    if pts == r["min_points"]:
                        name = r["name"]
                        await event.reply(
                            f"Congratulations on reaching new rank {name}\nCheck /rank to know your stats."
                        )
                        break
        else:
            pass


ON_ARG = ["on", "yes", "true", 1, "enable"]
OFF_ARG = ["off", "no", "false", 0, "disable"]


@usage("/level [on/off]")
@example("/level on")
@description(
    "Enables levelling system inside a chat. It counts user's message and calculates level of each individual upon that basis."
)
@register(pattern="level")
@logging
@exception
async def levelonoff(event):
    if not event.is_group:
        await event.reply(strings.is_pvt)
    if not await is_admin(event, event.sender_id):
        return

    key = f"lvl:{event.chat_id}"
    check = event.text.split()
    try:
        if check[1] in ON_ARG:
            doc = await level.find_one({"chat_id": event.chat_id})
            if doc and not doc.get("disabled", False):
                return await event.reply(
                    "Level System is already enabled in this chat."
                )
            # Enable by unsetting disabled flag, or upsert if not present
            await level.update_one({"chat_id": event.chat_id}, {"$set": {"chat_id": event.chat_id}, "$unset": {"disabled": ""}}, upsert=True)
            await _level_cache.set(key, True, ttl=120)
            await event.reply("Level System Enabled.")
            return "LEVEL_ON", None, None
        elif check[1] in OFF_ARG:
            doc = await level.find_one({"chat_id": event.chat_id})
            if not doc or doc.get("disabled", False):
                return await event.reply(
                    "Level System is already disabled in this chat."
                )
            # Instead of deleting, just mark as disabled
            await level.update_one({"chat_id": event.chat_id}, {"$set": {"disabled": True}}, upsert=True)
            await _level_cache.set(key, False, ttl=120)
            await event.reply("Level System Disabled.")
            return "LEVEL_OFF", None, None
        else:
            await event.reply("Invalid Argument.")
            return
    except IndexError:
        doc = await level.find_one({"chat_id": event.chat_id})
        if doc and not doc.get("disabled", False):
            await event.reply("Level System in enabled in this chat.")
        else:
            await event.reply("Level System in disabled in this chat.")