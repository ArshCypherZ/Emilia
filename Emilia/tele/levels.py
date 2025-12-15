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
from Emilia.utils.rank_card import generate_rank_card_sync
import functools
import math

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

# Configurable constants
XP_BASE = 50
XP_MULTIPLIER = 1.3
MAX_LEVEL = 1000
_event_multiplier = 1.0

# Helper functions for dynamic XP
def get_level_from_xp(xp):
    if xp <= 0: return 1
    # formula: lvl = (xp/base)^(1/mult)
    return int(((xp / XP_BASE) ** (1 / XP_MULTIPLIER)) + 0.01) + 1

def get_xp_for_level(level, prestige_level=0):
    if level <= 1: return 0
    return int(XP_BASE * ((level - 1) ** XP_MULTIPLIER))

def get_progress_bar(current, total, length=10):
    if total <= 0:
        percent = 1.0
    else:
        percent = min(1.0, current / total)
    filled = int(length * percent)
    return "█" * filled + "░" * (length - filled) + f" {int(percent * 100)}%"


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


async def get_leaderboard(chat_id, limit=10, skip=0):
    # Use Mongo sort + limit
    cursor = users_collection.find({"chat_id": chat_id}, {"_id": 0, "user_id": 1, "points": 1}).sort("points", -1).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def get_user_stats(user_id, chat_id):
    user_data = await users_collection.find_one(
        {"user_id": user_id, "chat_id": chat_id}
    )
    if not user_data:
        return None
    points = user_data.get("points", 0)
    first_name1 = await _get_first_name(user_id)
    
    # Dynamic Level Calculation
    level_val = get_level_from_xp(points)
    
    # XP Stats
    next_level_xp_total = get_xp_for_level(level_val + 1)
    current_level_xp_start = get_xp_for_level(level_val)
    
    xp_in_level = points - current_level_xp_start
    xp_needed_level = next_level_xp_total - current_level_xp_start
    
    if xp_needed_level > 0:
        progress = xp_in_level / xp_needed_level
    else:
        progress = 1.0

    rank = await get_rank(points)
    
    return {
        "points": points,
        "first_name": first_name1,
        "level": level_val,
        "rank": rank,
        "xp_in_level": xp_in_level,
        "xp_needed_level": xp_needed_level,
        "next_level_xp_total": next_level_xp_total,
        "progress": progress,
        "last_date": user_data.get("last_date", 0),
        "streak": user_data.get("streak", 0),
        "prestige": user_data.get("prestige", 0),
        "reputation": user_data.get("reputation", 0)
    }

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

@register(pattern="prestige")
async def prestige_handler(event):
    if not event.is_group: return
    if not await _get_level_on(event.chat_id): return
    
    stats = await get_user_stats(event.sender_id, event.chat_id)
    if not stats: return await event.reply("Register first!")
    
    # Requirement: Max Rank (DragonKin) approx 100k points
    if stats["points"] < 100000:
        return await event.reply("You need to reach **DragonKin** rank (100,000 XP) to prestige!")
    new_prestige = stats["prestige"] + 1
    await users_collection.update_one(
        {"user_id": event.sender_id, "chat_id": event.chat_id},
        {
            "$set": {"points": 0, "prestige": new_prestige}
        }
    )
    
    await event.reply(
        f"🚨 **PRESTIGE ADVANCEMENT** 🚨\n\n"
        f"User: {stats['first_name']}\n"
        f"Prestige Level: **{new_prestige}** 💎\n"
        f"XP has been reset. Your XP Multiplier has increased!"
    )

@register(pattern="thanks|rep")
async def reputation_handler(event):
    if not event.is_group: return
    if not await _get_level_on(event.chat_id): return
    if not event.reply_to_msg_id:
        return await event.reply("Reply to a user to give reputation!")
        
    reply_msg = await event.get_reply_message()
    if reply_msg.sender_id == event.sender_id:
        return await event.reply("You can't give rep to yourself, narcissist!")
    if reply_msg.sender_id == 5737513498: # Ignoring bot
         return
    
    # We need a 'last_rep_given' field in user document
    giver_data = await users_collection.find_one(
        {"user_id": event.sender_id, "chat_id": event.chat_id},
        {"last_rep_given": 1}
    )
    
    now_ts = time.time()
    last_rep = giver_data.get("last_rep_given", 0) if giver_data else 0
    
    if (now_ts - last_rep) < 86400:
        remaining = 86400 - (now_ts - last_rep)
        return await event.reply(f"You can give rep again in `{await get_time(remaining)}`")
        
    # Give Rep
    await users_collection.update_one(
        {"user_id": reply_msg.sender_id, "chat_id": event.chat_id},
        {"$inc": {"reputation": 1}},
        upsert=True
    )
    
    await users_collection.update_one(
        {"user_id": event.sender_id, "chat_id": event.chat_id},
        {"$set": {"last_rep_given": now_ts}},
        upsert=True
    )
    
    await event.reply(f"**+1 Reputation** to {reply_msg.sender.first_name}! 👍")

@register(pattern="levelset")
async def levelset_handler(event):
    if not await is_admin(event, event.sender_id): return
    
    args = event.text.split()
    if len(args) < 3:
        return await event.reply("Usage: `/levelset event [multiplier]`")
        
    cmd = args[1].lower()
    if cmd == "event":
        try:
            mult = float(args[2])
            global _event_multiplier
            _event_multiplier = mult
            await event.reply(f"Global Event Multiplier set to **{mult}x**! 🎉")
        except ValueError:
            await event.reply("Invalid number.")


@register(pattern="leaderboard")
async def _leaderboard(event):
    if not event.is_group:
        return await event.reply("Leaderboard is only for group chats.")
    if not await _get_level_on(event.chat_id):
        return await event.reply(
            "Levelling system is not active in this chat. To turn it on use `/level on`"
        )
    chat_id = event.chat_id
    # Default page 0
    leaderboard = await get_leaderboard(chat_id, limit=10, skip=0)
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
        
        # Buttons
        buttons = [
            Button.inline("Global Leaderboard", data="gleaderboard_"),
            Button.inline("Next ➡️", data="chatlb_10")
        ]
    else:
        lmao += (
            "No data for this chat. Try /register to register yourself in bot first!"
        )
        buttons = Button.inline("Global Leaderboard", data="gleaderboard_")
        
    await event.reply(lmao, buttons=buttons)


@callbackquery(pattern=r"chatlb_(\d+)")
async def chat_lb_callback(event):
    offset = int(event.pattern_match.group(1))
    chat_id = event.chat_id
    leaderboard = await get_leaderboard(chat_id, limit=10, skip=offset)
    
    if not leaderboard:
        return await event.answer("No more rankings!", alert=True)
        
    lmao = "🏆 **Leaderboard** for this chat:\n\n"
    for idx, user in enumerate(leaderboard, start=offset + 1):
        points = user.get("points", 0)
        user_id = user.get("user_id")
        first_name1 = await _get_first_name(user_id)
        lmao += (
            f"{idx}. [{first_name1}](tg://user?id={user_id}) --> {points} points\n"
        )
            
    buttons = []
    if offset >= 10:
        buttons.append(Button.inline("⬅️ Prev", data=f"chatlb_{offset - 10}"))
    buttons.append(Button.inline("Next ➡️", data=f"chatlb_{offset + 10}"))
    await event.edit(lmao, buttons=buttons)


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
        # Streak Logic
        now_ts = ds.datetime.now().timestamp()
        last_ts = stats.get("last_date") or 0
        current_streak = stats.get("streak", 0)
        
        # If last collection was within 48 hours (24h cooldown + 24h grace), increment streak
        # But allow for gap? The cooldown is 24h.
        # If they collect exactly after 24h, diff is 24h.
        # If they wait 2 days, diff is 48h+ -> reset.
        if 0 < (now_ts - last_ts) < (48 * 3600):
            current_streak += 1
        else:
            current_streak = 1
            
        base_points = 100
        streak_bonus = min(current_streak * 10, 100) # Max 100 bonus
        total_daily = base_points + streak_bonus
        
        await users_collection.update_one(
            {"user_id": event.sender_id, "chat_id": event.chat_id},
            {
                "$inc": {"points": total_daily},
                "$set": {
                    "last_date": now_ts,
                    "streak": current_streak
                }
            },
            upsert=True,
        )
        new_points = points + total_daily
        return await event.reply(
            f"💰 **Daily Reward Claimed!**\n"
            f"Computed Streak: **{current_streak}** 🔥\n"
            f"Bonus: +{streak_bonus} XP\n"
            f"Total Received: +{total_daily} XP\n"
            f"**Current Points**: {new_points}"
        )
    await event.reply(
        "You can claim your daily points in `{0}`".format((await get_time(y)))
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

    if stats:
        # Generate Visual Rank Card
        reply_msg = await event.reply("Generatin Rank Card...")
        try:
            loop = asyncio.get_running_loop()
            
            # Download profile photo
            try:
                pfp = await event.client.download_profile_photo(user_id, file=bytes)
            except Exception:
                pfp = None
                
            rank_image = await loop.run_in_executor(
                None,
                functools.partial(
                    generate_rank_card_sync,
                    firstname=stats['first_name'],
                    avatar_bytes=pfp,
                    current_xp=stats['points'],
                    total_xp=stats['next_level_xp_total'],
                    level=stats['level'],
                    rank_name=stats['rank']
                )
            )
            rank_image.name = "rank.png"
            
            # Text fallback with progress bar
            bar = get_progress_bar(stats['xp_in_level'], stats['xp_needed_level'])
            
            # Cooler, minimalist design
            caption = (
                f"**{stats['first_name']}**  •  {stats['rank']}\n"
                f"Level {stats['level']}   `{bar}`\n"
                f"XP: {stats['points']} / {stats['next_level_xp_total']}\n"
            )
            
            await event.reply(file=rank_image, message=caption)
            await reply_msg.delete()
        except Exception as e:
            LOGGER.error(f"Rank generation failed: {e}")
            await reply_msg.edit(
                f"**{stats['first_name']}'s Stats**:\n\n"
                f"**Points**: {stats['points']}\n"
                f"**Level**: {stats['level']}\n"
                f"**Rank**: {stats['rank']}"
            )

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
            
        # Anti-Abuse Checks
        if len(event.text) < 3:
            return # Too short
            
        if not (await is_flooding(user_id, chat_id)):
            # XP Gain Logic with Event and Prestige Multiplier
            global _event_multiplier
            
            user_doc = await users_collection.find_one(
                {"user_id": user_id, "chat_id": chat_id}, {"prestige": 1}
            )
            prestige = user_doc.get("prestige", 0) if user_doc else 0
            
            # Multiplier: 1 + (0.1 * prestige)
            final_mult = _event_multiplier * (1 + (0.1 * prestige))
            points_inc = final_mult
            
            # buffer point inc and lastmsg update
            _points_buffer[(user_id, chat_id)] = _points_buffer.get((user_id, chat_id), 0) + points_inc
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
