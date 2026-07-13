import json
import logging
import os
import queue
import sys
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

import orjson
import redis.asyncio as redis
import uvloop
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from motor import motor_asyncio
from pymongo.errors import DuplicateKeyError
from pyrogram import Client

from Emilia.config import Development as Config
from Emilia.utils.ads import install_ad_hooks
from Emilia.utils.trace import TRACE_ID

# Must run before any event loop is created (clients, schedulers, motor).
# Sole entry point for the whole process tree — every client/scheduler
# inherits uvloop.
uvloop.install()


# trace.py has no Emilia deps; import at module top so JSONFormatter never does a
# lazy import from inside the QueueListener thread (that deadlocks the import lock
# during startup while the main thread is importing Emilia.utils.*).


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        # Structured payload attached via logger.<level>(msg, extra={"emilia":
        # {...}})
        emilia_extra = getattr(record, "emilia", None)
        if isinstance(emilia_extra, dict):
            log_record.update(emilia_extra)
        # Correlate any log emitted while handling an update (cache/flush errors)
        # with the update, via the per-update ContextVar.
        if "trace" not in log_record:
            try:
                tid = TRACE_ID.get()
                if tid is not None:
                    log_record["trace"] = tid
            except Exception:
                pass
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return orjson.dumps(log_record, default=str).decode()


_log_listener = None


def _setup_emilia_logging():
    """Route all logging through a QueueListener so file/stdout I/O happens off
    the event-loop thread. Both handlers use the JSON formatter and the file is
    size-rotated. The `Emilia` logger propagates into this single pipeline so
    its records reach log.txt (previously they never did)."""
    global _log_listener

    log_queue = queue.SimpleQueue()
    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setFormatter(JSONFormatter())
    file_h = RotatingFileHandler("log.txt", maxBytes=20_000_000, backupCount=3)
    file_h.setFormatter(JSONFormatter())

    _log_listener = QueueListener(
        log_queue, stdout_h, file_h, respect_handler_level=True
    )
    _log_listener.start()

    qh = QueueHandler(log_queue)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [qh]

    logger = logging.getLogger("Emilia")
    logger.setLevel(logging.INFO)
    logger.propagate = True  # single pipeline; no private handlers
    logger.handlers = []
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
CLONES_PER_USER = Config.CLONES_PER_USER
CLONE_PREMIUM_ENABLED = Config.CLONE_PREMIUM_ENABLED
CLONE_PREMIUM_STARS = Config.CLONE_PREMIUM_STARS

TRIGGERS = ("/", "!")
ANILIST_CLIENT = Config.ANILIST_CLIENT
ANILIST_SECRET = Config.ANILIST_SECRET
ANILIST_REDIRECT_URL = Config.ANILIST_REDIRECT_URL


DOWN_PATH = "Emilia/anime/downloads/"
HELP_DICT = dict()


HELP_DICT["Group"] = """
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

HELP_DICT["Anilist"] = """
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

HELP_DICT["Oauth"] = """
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
CARTESIA_API_KEY = Config.CARTESIA_API_KEY

DEV_USERS.add(OWNER_ID)
DEV_USERS = list(DEV_USERS)

scheduler = AsyncIOScheduler()

LOGGER.info("[Emilia] Emilia Is Starting. | Spiral Tech Project | Licensed Under MIT.")
# Smart-plugin loading recurses (Path(root).rglob("*.py")), so the anime
# handlers under Emilia/modules/plugins/anime/ AND the modules/commands/
# tree (register/auth/callbackquery/InlineQuery attach via func.handlers,
# see custom_filter.py) both load as part of this same tree.
pyro_plugins = dict(root="Emilia/modules")

mongo = motor_asyncio.AsyncIOMotorClient(
    MONGO_DB_URL,
    minPoolSize=10,
    maxPoolSize=100,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=20000,
    retryWrites=True,
)
db = mongo["Emilia"]

redis_client = redis.from_url(
    Config.REDIS_URL,
    password=Config.REDIS_PASSWORD,
    decode_responses=True,
    health_check_interval=30,
    socket_connect_timeout=5,
    socket_timeout=10,
)
# deprecated alias; prefer `from Emilia import redis_client`
db.redis_client = redis_client

# Attach the metrics log handler now that redis_client exists (metrics.py imports
# it). It counts WARNING/ERROR/CRITICAL records into Redis for /devstats. Runs on
# the QueueListener thread, so it uses a sync redis client internally.
try:
    from Emilia.utils.metrics import MetricsLogHandler

    if _log_listener is not None:
        _log_listener.handlers = _log_listener.handlers + (MetricsLogHandler(),)
except Exception:
    LOGGER.warning("failed to attach metrics log handler", exc_info=True)

# Initialize client
pgram = Client(
    name=SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=TOKEN,
    workers=32,
    plugins=pyro_plugins,
    sleep_threshold=10,
)
pgram.is_clone = False
pgram.owner_id = OWNER_ID

install_ad_hooks()


async def create_indexes():
    # Counters that only ever grow; when two docs collide on the same key
    # (e.g. a race before the unique index existed), merging must sum these
    # instead of picking one arbitrarily and silently dropping progress.
    ADDITIVE_FIELDS = {"points", "reputation"}

    async def _merge_duplicates(collection, keys):
        """Collapse documents that collide on `keys` into one, so a unique index
        can be built. Additive counters are summed, other numeric fields take the
        max (streaks/prestige/timestamps), and everything else keeps whatever
        value is already on the most complete document."""
        key_fields = [k for k, _ in keys]
        pipeline = [
            {
                "$group": {
                    "_id": {f: f"${f}" for f in key_fields},
                    "ids": {"$push": "$_id"},
                    "count": {"$sum": 1},
                }
            },
            {"$match": {"count": {"$gt": 1}}},
        ]
        async for group in collection.aggregate(pipeline, allowDiskUse=True):
            docs = await collection.find({"_id": {"$in": group["ids"]}}).to_list(
                length=None
            )
            if len(docs) < 2:
                continue
            base = max(docs, key=len)
            merged = {}
            for doc in docs:
                for field, value in doc.items():
                    if field == "_id":
                        continue
                    if field in ADDITIVE_FIELDS and isinstance(value, (int, float)):
                        merged[field] = merged.get(field, 0) + value
                    elif isinstance(value, (int, float)) and isinstance(
                        merged.get(field, value), (int, float)
                    ):
                        merged[field] = max(merged.get(field, value), value)
                    else:
                        merged.setdefault(field, value)
            await collection.update_one({"_id": base["_id"]}, {"$set": merged})
            drop_ids = [d["_id"] for d in docs if d["_id"] != base["_id"]]
            await collection.delete_many({"_id": {"$in": drop_ids}})
            LOGGER.info(
                f"Merged {len(drop_ids)} duplicate doc(s) on {collection.name} for {group['_id']}"
            )

    # Helper to ensure a unique index, replacing a conflicting non-unique one
    # if present
    async def ensure_unique(collection, keys, name=None):
        name = name or "_".join([f"{k}_{d}" for k, d in keys])
        try:
            info = await collection.index_information()
            if name in info and not info[name].get("unique"):
                await collection.drop_index(name)
        except Exception as e:
            LOGGER.warning(f"Index {name} on {collection.name}: {e}")
        try:
            await collection.create_index(keys, name=name, unique=True)
        except DuplicateKeyError:
            # Existing duplicate documents (from races before this index existed)
            # block the build; merge them into one doc each, then retry once.
            try:
                await _merge_duplicates(collection, keys)
                await collection.create_index(keys, name=name, unique=True)
            except Exception as e:
                LOGGER.warning(f"Index {name} on {collection.name}: {e}")
        except Exception as e:
            LOGGER.warning(f"Index {name} on {collection.name}: {e}")

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
    admincache = db.admincache

    # Extra collections referenced elsewhere
    auth_users = db["AUTH_USERS"]
    chatbotto = db.chatbotto
    convodb = db.gemini_convos
    antichannel = db.antichannel
    vanitas = db.vanitas
    ai = db.ai
    ad_footers = db.ad_footers
    bot2bot_settings = db.bot2bot_settings
    bot2bot_pending = db.bot2bot_pending

    # Anime-related singletons/collections
    db["DISABLED_CMDS"]
    db["CONNECTED_CHANNELS"]
    db["GROUP_UI"]
    sfw_groups = db["SFW_GROUPS"]
    db["SUBSPLEASE_GROUPS"]
    db["MAL_HEADLINES_GROUPS"]

    approve_d = db["approve_d"]

    # Core/app data
    await chatlevels.create_index([("points", -1), ("user_id", 1), ("chat_id", 1)])
    # Common lookup by (user_id, chat_id)
    await chatlevels.create_index([("user_id", 1), ("chat_id", 1)])
    # Optimized per-chat leaderboard: filter by chat then sort by points
    await chatlevels.create_index([("chat_id", 1), ("points", -1)])
    # Enforce a single doc per (chat_id,user_id)
    await ensure_unique(
        chatlevels, [("chat_id", 1), ("user_id", 1)], name="uniq_chat_user"
    )

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

    # admincache: hot lookup by (chat_id, user_id) in functions/admins.py
    await ensure_unique(admincache, [("chat_id", 1), ("user_id", 1)])
    # Self-delete stale admin-cache entries (lazy TTL model, B4)
    await admincache.create_index([("last_updated", 1)], expireAfterSeconds=86400)
    # Enforce uniqueness of warn id within a user in a chat
    await ensure_unique(
        user_warnings,
        [("chat_id", 1), ("user_id", 1), ("warn_id", 1)],
        name="uniq_warn_triplet",
    )

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
    await ad_footers.create_index([("created_at", 1)], expireAfterSeconds=3888000)
    await ensure_unique(bot2bot_settings, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(bot2bot_pending, [("token", 1)], name="token_1")
    await bot2bot_pending.create_index([("expires_at", 1)], expireAfterSeconds=0)

    # Anime singletons. These are keyed by _id, which MongoDB already indexes
    # uniquely by default — asking for a second unique index on _id fails with
    # "the field 'unique' is not valid for an _id index specification" (code 197),
    # so there's nothing to create here. `sfw_groups` keys on a plain `id` field
    # instead, so it still needs an explicit unique index.
    await ensure_unique(sfw_groups, [("id", 1)], name="id_1")

    # Approvals invariant: single record per (chat_id, user_id)
    await ensure_unique(
        approve_d, [("chat_id", 1), ("user_id", 1)], name="uniq_approve_chat_user"
    )

    # Clone broadcast tracking via bot_ids array in users/chats
    await users.create_index([("bot_ids", 1)])
    await chats.create_index([("bot_ids", 1)])

    # Hot-path collections that previously had no index (B1)
    onofflevel = db.onofflevel  # tele/levels.py per-message level check
    firstname = db.first_name  # leaderboards / rank cards
    # clone lookups; docs keyed by _id (=user_id, auto-indexed)
    clone = db.clone
    dnd = db.dnd  # new-member events in tele/bans.py
    await ensure_unique(onofflevel, [("chat_id", 1)], name="chat_id_1")
    await ensure_unique(firstname, [("user_id", 1)], name="user_id_1")
    await ensure_unique(clone, [("token", 1)], name="token_1")
    await clone.create_index([("bot_id", 1)])
    await clone.create_index([("owner_id", 1)])
    await ensure_unique(dnd, [("chat_id", 1)], name="chat_id_1")
    # quietfed flag is stored on the feds collection keyed by chat_id
    # (federations.py)
    await feds.create_index([("chat_id", 1)])

    LOGGER.info("Database indexes created successfully.")
