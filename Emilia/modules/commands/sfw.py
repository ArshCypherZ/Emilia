# DONE: SFW

import io

from pyrogram.types import ReplyParameters

from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get
from Emilia.utils.decorators import exception

url_nekos = "https://nekos.best/api/v2/"

_HEADERS = {"User-Agent": "Emilia/1.0 (https://github.com/ArshCypherZ/Emilia)"}


@exception
async def send_media(client, message, img):
    reply_id = message.reply_to_message.id if message.reply_to_message else message.id
    lower = str(img).lower().split("?")[0]
    # Download the media ourselves; passing the raw URL makes Telegram fetch it
    # server-side, which fails with WEBPAGE_CURL_FAILED on some hosts.
    resp = await get(img, headers=_HEADERS)
    data = resp.content
    if not data:
        return
    ext = lower.rsplit(".", 1)[-1] if "." in lower else "jpg"
    buf = io.BytesIO(data)
    buf.name = f"emilia.{ext}"
    if lower.endswith(".gif"):
        return await client.send_animation(
            message.chat.id, buf, reply_parameters=ReplyParameters(message_id=reply_id)
        )
    if lower.endswith((".mp4", ".webm")):
        return await client.send_video(
            message.chat.id, buf, reply_parameters=ReplyParameters(message_id=reply_id)
        )
    return await client.send_photo(
        message.chat.id, buf, reply_parameters=ReplyParameters(message_id=reply_id)
    )


async def nekos_best(client, message, category):
    result = await get(f"{url_nekos}{category}", headers=_HEADERS)
    try:
        result_json = result.json() or {}
    except Exception:
        return
    results = result_json.get("results") or []
    if not results:
        return
    img = results[0]["url"]
    await send_media(client, message, img)


def _register_nekos(pattern, category):
    @register(pattern=pattern, disable=True)
    @disable
    async def handler(client, message):
        await nekos_best(client, message, category)

    return handler


# nekos.best PNG endpoints
waifu = _register_nekos("waifu", "waifu")
neko = _register_nekos("neko", "neko")
husbando = _register_nekos("husbando", "husbando")
kitsune = _register_nekos("kitsune", "kitsune")

# nekos.best GIF endpoints
hug = _register_nekos("hug", "hug")
kiss = _register_nekos("kiss", "kiss")
pat = _register_nekos("pat", "pat")
cuddle = _register_nekos("cuddle", "cuddle")
cry = _register_nekos("cry", "cry")
poke = _register_nekos("poke", "poke")
slap = _register_nekos("slap", "slap")
kickgif = _register_nekos("kicks", "kick")
happy = _register_nekos("happy", "happy")
wink = _register_nekos("wink", "wink")
dance = _register_nekos("dance", "dance")
bite = _register_nekos("bite", "bite")
feed = _register_nekos("feed", "feed")
nom = _register_nekos("nom", "nom")
handhold = _register_nekos("handhold", "handhold")
highfive = _register_nekos("highfive", "highfive")
bonk = _register_nekos("bonk", "bonk")
yeet = _register_nekos("yeet", "yeet")
blush = _register_nekos("blush", "blush")
smile = _register_nekos("smile", "smile")
wave = _register_nekos("wave", "wave")
smug = _register_nekos("smug", "smug")
tickle = _register_nekos("tickle", "tickle")
glomp = _register_nekos("glomp", "hug")
killgif = _register_nekos("kill", "punch")
bully = _register_nekos("bully", "baka")
awoo = _register_nekos("awoo", "wag")
lick = _register_nekos("lick", "nom")

# extra nekos.best endpoints not previously exposed
lurk = _register_nekos("lurk", "lurk")
shoot = _register_nekos("shoot", "shoot")
sleep = _register_nekos("sleep", "sleep")
clap = _register_nekos("clap", "clap")
shrug = _register_nekos("shrug", "shrug")
stare = _register_nekos("stare", "stare")
confused = _register_nekos("confused", "confused")
sip = _register_nekos("sip", "sip")
think = _register_nekos("think", "think")
wag = _register_nekos("wag", "wag")
teehee = _register_nekos("teehee", "teehee")
shocked = _register_nekos("shocked", "shocked")
bleh = _register_nekos("bleh", "bleh")
bored = _register_nekos("bored", "bored")
yawn = _register_nekos("yawn", "yawn")
facepalm = _register_nekos("facepalm", "facepalm")
kabedon = _register_nekos("kabedon", "kabedon")
baka = _register_nekos("baka", "baka")
angry = _register_nekos("angry", "angry")
spin = _register_nekos("spin", "spin")
shake = _register_nekos("shake", "shake")
run = _register_nekos("run", "run")
nod = _register_nekos("nod", "nod")
nope = _register_nekos("nope", "nope")
punch = _register_nekos("punch", "punch")
handshake = _register_nekos("handshake", "handshake")
lappillow = _register_nekos("lappillow", "lappillow")
pout = _register_nekos("pout", "pout")
blowkiss = _register_nekos("blowkiss", "blowkiss")
salute = _register_nekos("salute", "salute")
thumbsup = _register_nekos("thumbsup", "thumbsup")
laugh = _register_nekos("laugh", "laugh")
tableflip = _register_nekos("tableflip", "tableflip")
nod2 = _register_nekos("ngif", "nod")
cringe = _register_nekos("cringe", "shocked")
