import orjson
import os


def get_user_list(config, key):
    with open("{}/Emilia/{}".format(os.getcwd(), config), "rb") as json_file:
        return orjson.loads(json_file.read())[key]

class Config(object):
    API_HASH = "5170ded206641d73215baf40175a6924" # API_HASH from my.telegram.org
    API_ID = "30422005" # API_ID from my.telegram.org

    BOT_ID = 8928905291 # BOT_ID
    BOT_USERNAME = "sayaqtbot" # BOT_USERNAME

    MONGO_DB_URL = "mongodb+srv://parkerxc:parkerxc@parker.j4ra02c.mongodb.net/?appName=parker" # MongoDB URL from MongoDB Atlas

    SUPPORT_CHAT = "SayaProject" # Support Chat Username
    UPDATE_CHANNEL = "SayaProject" # Update Channel Username
    START_PIC = "https://files.catbox.moe/t9st49.jpg" # Start Image
    DEV_USERS = [6264372980,1329546526] # Dev Users
    TOKEN = "8928905291:AAG9eyF5AkQ1F0iJdoUDSP8jc33_txnMF4A" # Bot Token from @BotFather
    CLONE_LIMIT = 0 # Number of clones your bot can make

    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

    EVENT_LOGS = -1003802701610 # Event Logs Chat ID
    OWNER_ID = 5940554521 # Owner ID
 
    TEMP_DOWNLOAD_DIRECTORY = "./" # Temporary Download Directory
    BOT_NAME = "sayaqtbot" # Bot Name
    WALL_API = "6950f53" # Wall API from wall.alphacoders.com
    GROQ_API_KEY = "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" # GROQ API Key from groq.com


class Production(Config):
    LOGGER = True


class Development(Config):
    LOGGER = True

