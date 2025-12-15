import orjson
import os


def get_user_list(config, key):
    with open("{}/Emilia/{}".format(os.getcwd(), config), "rb") as json_file:
        return orjson.loads(json_file.read())[key]

class Config(object):
    API_HASH = "45aabfac" # API_HASH from my.telegram.org
    API_ID = 62 # API_ID from my.telegram.org

    BOT_ID = 521 # BOT_ID
    BOT_USERNAME = "Elf_Robot" # BOT_USERNAME

    MONGO_DB_URL = "mongodb://username:password@localhost:27017/emi?directConnection=true&authSource=admin" # MongoDB URL from MongoDB Atlas

    SUPPORT_CHAT = "SpiralTechDivision" # Support Chat Username
    UPDATE_CHANNEL = "SpiralUpdates" # Update Channel Username
    START_PIC = "https://pic-bstarstatic.akamaized.net/ugc/9e98b6c8872450f3e8b19e0d0aca02deff02981f.jpg@1200w_630h_1e_1c_1f.webp" # Start Image
    DEV_USERS = [6040984893, 6461051572, 7107018652] # Dev Users
    TOKEN = "57375" # Bot Token from @BotFather
    CLONE_LIMIT = 50 # Number of clones your bot can make

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

    EVENT_LOGS = -10093 # Event Logs Chat ID
    OWNER_ID = 6040984893 # Owner ID
 
    TEMP_DOWNLOAD_DIRECTORY = "./" # Temporary Download Directory
    BOT_NAME = "Emilia" # Bot Name
    WALL_API = "6950f53" # Wall API from wall.alphacoders.com
    GROQ_API_KEY = "gsk_mm" # GROQ API Key from groq.com


class Production(Config):
    LOGGER = True


class Development(Config):
    LOGGER = True
