import logging
import os
import sys
import json
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from motor import motor_asyncio
from pyrogram import Client
from telethon import TelegramClient

from Emilia.config import Development as Config

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record)

def _setup_emilia_logging():
    # If root has no handlers yet, configure it at INFO with console+file
    if not logging.getLogger().handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logging.basicConfig(
            level=logging.INFO,
            handlers=[
                handler,
                logging.FileHandler("log.txt"),
            ],
        )
    # Configure the package logger explicitly
    logger = logging.getLogger("Emilia")
    logger.setLevel(logging.INFO)

    # Ensure at least one console handler to stdout at INFO for this logger
    has_console = any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    if not has_console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(JSONFormatter())
        logger.addHandler(sh)

    # Avoid duplicate lines if root also has handlers
    logger.propagate = False
    return logger

LOGGER = _setup_emilia_logging()

TOKEN = os.environ.get("EMILIA_TOKEN", Config.TOKEN)
OWNER_ID = int(os.environ.get("EMILIA_OWNER_ID", Config.OWNER_ID))

SESSION_NAME = "emilia_main"

DEV_USERS = {int(x) for x in Config.DEV_USERS or []}
EVENT_LOGS = Config.EVENT_LOGS
API_ID = Config.API_ID
API_HASH = Config.API_HASH
MONGO_DB_URL = Config.MONGO_DB_URL
SUPPORT_CHAT = Config.SUPPORT_CHAT
BOT_USERNAME = Config.BOT_USERNAME
UPDATE_CHANNEL = Config.UPDATE_CHANNEL
START_PIC = Config.START_PIC
CLONE_LIMIT = Config.CLONE_LIMIT

TRIGGERS = ("/ !").split()
ANILIST_CLIENT = 10061
ANILIST_SECRET = "NTRAM29JYsTVMYphFkLd9meMoPByxB38aBGDWkyg"
ANILIST_REDIRECT_URL = "https://anilist.co/api/v2/oauth/pin"


DOWN_PATH = "Emilia/anime/downloads/"
HELP_DICT = dict()


HELP_DICT[
    "Group"
] = """
Group based commands:
/anisettings - Toggle stuff like whether to allow 18+ stuff in group or whether to notify about aired animes, etc and change UI
/anidisable - Disable use of a cmd in the group (Disable multiple cmds by adding space between them)
`/anidisable anime anilist me user`
/anienable - Enable use of a cmd in the group (Enable multiple cmds by adding space between them)
`/anienable anime anilist me user`
/anidisabled - List out disabled cmds
"""

HELP_DICT[
    "Additional"
] = """Use /anireverse cmd to get reverse search via tracemoepy API
__Note: This works best on uncropped anime pic,
when used on cropped media, you may get result but it might not be too reliable__
Use /schedule cmd to get scheduled animes based on weekdays
Use /watch cmd to get watch order of searched anime
Use /fillers cmd to get a list of fillers for an anime
Use /quote cmd to get a random quote
"""

HELP_DICT[
    "Anilist"
] = """
Below is the list of basic anilist cmds for info on anime, character, manga, etc.
/anime - Use this cmd to get info on specific anime using keywords (anime name) or Anilist ID
(Can lookup info on sequels and prequels)
/anilist - Use this cmd to choose between multiple animes with similar names related to searched query
(Doesn't includes buttons for prequel and sequel)
/character - Use this cmd to get info on character
/manga - Use this cmd to get info on manga
/airing - Use this cmd to get info on airing status of anime
/top - Use this cmd to lookup top animes of a genre/tag or from all animes
(To get a list of available tags or genres send /gettags or /getgenres
'/gettags nsfw' for nsfw tags)
/user - Use this cmd to get info on an anilist user
/browse - Use this cmd to get updates about latest animes
"""

HELP_DICT[
    "Oauth"
] = """
This includes advanced anilist features
Use /auth or !auth cmd to get details on how to authorize your Anilist account with bot
Authorising yourself unlocks advanced features of bot like:
- adding anime/character/manga to favourites
- viewing your anilist data related to anime/manga in your searches which includes score, status, and favourites
- unlock /flex, /ame, /activity and /favourites commands
- adding/updating anilist entry like completed or plan to watch/read
- deleting anilist entry
Use /flex or !flex cmd to get your anilist stats
Use /logout or !logout cmd to disconnect your Anilist account
Use /ame or !ame cmd to get your anilist recent activity
Can also use /activity or !activity
Use /favourites or !favourites cmd to get your anilist favourites
"""


TEMP_DOWNLOAD_DIRECTORY = Config.TEMP_DOWNLOAD_DIRECTORY
WALL_API = Config.WALL_API
BOT_ID = Config.BOT_ID
BOT_NAME = Config.BOT_NAME
GROQ_API_KEY = Config.GROQ_API_KEY

DEV_USERS.add(OWNER_ID)
DEV_USERS = list(DEV_USERS)

scheduler = AsyncIOScheduler()

LOGGER.info("[Emilia] Emilia Is Starting. | Spiral Tech Project | Licensed Under MIT.")
plugins = dict(root="Emilia/anime")
pyro_plugins = dict(root="Emilia/pyro")

mongo = motor_asyncio.AsyncIOMotorClient(MONGO_DB_URL, minPoolSize=10, maxPoolSize=100)
db = mongo["Emilia"]

import redis.asyncio as redis
redis_client = redis.from_url(Config.REDIS_URL, decode_responses=True)
db.redis_client = redis_client

# Initialize clients
pgram = Client(name=SESSION_NAME, api_id=API_ID, api_hash=API_HASH, bot_token=TOKEN, workers=32, plugins=pyro_plugins, sleep_threshold=0)
pgram.is_clone = False
pgram.owner_id = OWNER_ID

anibot = Client(name=f"{SESSION_NAME}_anibot", api_id=API_ID, api_hash=API_HASH, bot_token=TOKEN, sleep_threshold=0, plugins=plugins)
telethn = TelegramClient(f"{SESSION_NAME}_tele", API_ID, API_HASH).start(bot_token=TOKEN)
telethn.is_clone = False


async def create_indexes():
    # Helper to ensure a unique index, replacing a conflicting non-unique one if present
    async def ensure_unique(collection, keys, name=None):
        name = name or "_".join([f"{k}_{d}" for k, d in keys])
        try:
            info = await collection.index_information()
            if name in info and not info[name].get("unique"):
                await collection.drop_index(name)
        except Exception:
            pass
        try:
            await collection.create_index(keys, name=name, unique=True)
        except Exception:
            # If it already exists with desired options, ignore
            pass

    # Collections
    chatlevels = db.chatlevels
    users = db.users
    chats = db.chats
    flood_msgs = db.flood_msgs

    locks = db.locks
    blocklists = db.blocklists
    notes = db.notes
    filters = db.filters
    welcome = db.welcome
    
    warn_settings = db.warn_settings
    user_warnings = db.user_warnings

    afk = db.afk
    nsfw = db.nsfw
    pin = db.pin
    reports = db.reports
    disable = db.disable
    connection = db.connection
    user_info = db.user_info
    karma = db.karma
    nightmode = db.nightmode
    rules = db.rules

    feds = db.feds
    fbans = db.fbans
    fsubs = db.fsubs
    fadmins = db.fadmins
    logchannels = db.logchannels

    # Extra collections referenced elsewhere
    auth_users = db["AUTH_USERS"]
    chatbotto = db.chatbotto
    convodb = db.gemini_convos
    antichannel = db.antichannel
    vanitas = db.vanitas
    ai = db.ai

    # Anime-related singletons/collections
    disabled_cmds = db["DISABLED_CMDS"]
    connected_channels = db["CONNECTED_CHANNELS"]
    group_ui = db["GROUP_UI"]
    sfw_groups = db["SFW_GROUPS"]
    subsplease_groups = db["SUBSPLEASE_GROUPS"]
    mal_headlines_groups = db["MAL_HEADLINES_GROUPS"]

    approve_d = db["approve_d"]

    # Core/app data
    await chatlevels.create_index([("points", -1), ("user_id", 1), ("chat_id", 1)])
    # Common lookup by (user_id, chat_id)
    await chatlevels.create_index([("user_id", 1), ("chat_id", 1)])
    # Optimized per-chat leaderboard: filter by chat then sort by points
    await chatlevels.create_index([("chat_id", 1), ("points", -1)])
    # Enforce a single doc per (chat_id,user_id)
    await ensure_unique(chatlevels, [("chat_id", 1), ("user_id", 1)], name="uniq_chat_user")

    # Users and chats uniqueness
    await ensure_unique(users, [("user_id", 1)], name="user_id_1")
    await users.create_index([("username", 1)])
    await users.create_index([("chats.chat_id", 1)])

    await ensure_unique(chats, [("chat_id", 1)], name="chat_id_1")
    await chats.create_index([("first_found_date", 1)])
    await flood_msgs.create_index([("chat_id", 1), ("user_id", 1), ("msg_id", 1)])
    # TTL Index for flood_msgs (expire after 1 hour)
    await flood_msgs.create_index([("date", 1)], expireAfterSeconds=3600)

    # Features (single-doc-per-chat)
    await ensure_unique(locks, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(blocklists, [("chat_id", 1)], name="chat_id_1")
    # Efficient match/pull on nested array field
    await blocklists.create_index([("blocklist_text.blocklist_text", 1)])

    await ensure_unique(notes, [("chat_id", 1)], name="chat_id_1")
    await notes.create_index([("notes.note_name", 1)])
    # Compound multikey for efficient elemMatch lookups
    await notes.create_index([("chat_id", 1), ("notes.note_name", 1)])

    await ensure_unique(filters, [("chat_id", 1)], name="chat_id_1")
    await filters.create_index([("filters.filter_name", 1)])
    # Compound multikey for efficient elemMatch lookups
    await filters.create_index([("chat_id", 1), ("filters.filter_name", 1)])

    await ensure_unique(welcome, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(rules, [("chat_id", 1)], name="chat_id_1")

    # Warnings
    await ensure_unique(warn_settings, [("chat_id", 1)], name="chat_id_1")
    await user_warnings.create_index([("chat_id", 1), ("user_id", 1)])
    # Enforce uniqueness of warn id within a user in a chat
    await ensure_unique(user_warnings, [("chat_id", 1), ("user_id", 1), ("warn_id", 1)], name="uniq_warn_triplet")

    # Misc toggles/settings
    await afk.create_index([("user_id", 1)])
    await ensure_unique(nsfw, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(pin, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(reports, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(disable, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(connection, [("user_id", 1)], name="user_id_1")
    await ensure_unique(user_info, [("user_id", 1)], name="user_id_1")
    await karma.create_index([("chat_id_toggle", 1)])
    await ensure_unique(nightmode, [("chat_id", 1)], name="chat_id_1")

    # Federations
    # Ensure single fed per fed_id and per owner
    await ensure_unique(feds, [("fed_id", 1)], name="fed_id_1")
    await ensure_unique(feds, [("owner_id", 1)], name="owner_id_1")
    await feds.create_index([("chats", 1)])  # multikey for membership queries
    await feds.create_index([("fedadmins", 1)])
    # One fbans doc per fed
    await ensure_unique(fbans, [("fed_id", 1)], name="fed_id_1")
    # One fsubs doc per fed
    await ensure_unique(fsubs, [("fed_id", 1)], name="fed_id_1")
    # One fadmin profile per user
    await ensure_unique(fadmins, [("user_id", 1)], name="user_id_1")

    # Logs
    await ensure_unique(logchannels, [("chat_id", 1)], name="chat_id_1")

    # Third-party/auth & chatbot
    await ensure_unique(auth_users, [("id", 1)], name="id_1")
    await ensure_unique(chatbotto, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(convodb, [("user_id", 1)], name="user_id_1")
    await ensure_unique(antichannel, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(vanitas, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(ai, [("chat_id", 1)], name="chat_id_1")

    # Anime singletons
    await ensure_unique(disabled_cmds, [("_id", 1)], name="_id_1")
    await ensure_unique(connected_channels, [("_id", 1)], name="_id_1")
    await ensure_unique(group_ui, [("_id", 1)], name="_id_1")
    await ensure_unique(sfw_groups, [("id", 1)], name="id_1")
    await ensure_unique(subsplease_groups, [("_id", 1)], name="_id_1")
    await ensure_unique(mal_headlines_groups, [("_id", 1)], name="_id_1")

    # Approvals invariant: single record per (chat_id, user_id)
    await ensure_unique(approve_d, [("chat_id", 1), ("user_id", 1)], name="uniq_approve_chat_user")

    # Clone broadcast tracking via bot_ids array in users/chats
    await users.create_index([("bot_ids", 1)])
    await chats.create_index([("bot_ids", 1)])

    LOGGER.info("Database indexes created successfully.")