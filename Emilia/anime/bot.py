import asyncio
import io
import os
import re
import subprocess
import sys
import traceback
from datetime import datetime

from Emilia.utils.async_http import get
from bson.objectid import ObjectId
from natsort import natsorted
from pyrogram import Client, enums, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChannelInvalid as ci
from pyrogram.errors import ChannelPrivate as cp
from pyrogram.errors import FloodWait as fw
from pyrogram.errors import PeerIdInvalid as pi
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from Emilia import BOT_USERNAME, DEV_USERS, HELP_DICT, LOGGER
from Emilia import TRIGGERS as trg
from Emilia import anibot, custom_filter
from Emilia.anime.anilist import auth_link_cmd, code_cmd, logout_cmd
from Emilia.utils.data_parser import get_additional_info, get_anime, get_recommendations
from Emilia.utils.db import get_collection
from Emilia.utils.helper import AUTH_USERS, check_user, clog, control_user, get_btns

USERS = get_collection("USERS")
GROUPS = get_collection("GROUPS")
SFW_GROUPS = get_collection("SFW_GROUPS")
DC = get_collection("DISABLED_CMDS")
AG = get_collection("AIRING_GROUPS")
HD_GRPS = get_collection("HEADLINES_GROUPS")
MAL_HD_GRPS = get_collection("MAL_HEADLINES_GROUPS")
SP_GRPS = get_collection("SUBSPLEASE_GROUPS")
CC = get_collection("CONNECTED_CHANNELS")
CHAT_DEV_USERS = ChatMemberStatus.OWNER
MEMBER = ChatMemberStatus.MEMBER
ADMINISTRATOR = ChatMemberStatus.ADMINISTRATOR

CMD = [
    "anime",
    "anilist",
    "character",
    "manga",
    "airing",
    "anihelp",
    "schedule",
    "fillers",
    "top",
    "anireverse",
    "watch",
    "anistart",
    "aniping",
    "flex",
    "ame",
    "activity",
    "user",
    "favourites",
    "gettags",
    "quotes",
    "getgenres",
    "aniconnect",
    "browse",
    "studio",
]


@Client.on_message(
    custom_filter.command(commands=["anienable", "anidisable"]), filters.group
)
@control_user
async def en_dis__able_cmd(client: Client, message: Message, mdata: dict):
    cmd = mdata["text"].split(" ", 1)
    gid = mdata["chat"]["id"]
    try:
        user = mdata["from_user"]["id"]
    except KeyError:
        user = mdata["sender_chat"]["id"]
    if (
        user in DEV_USERS
        or (await anibot.get_chat_member(gid, user)).status
        in [ADMINISTRATOR, CHAT_DEV_USERS]
        or user == gid
    ):
        if len(cmd) == 1:
            x = await message.reply_text("No command specified to be disabled!!!")
            await asyncio.sleep(5)
            await x.delete()
            return
        enable = False if "enable" not in cmd[0] else True
        if set(cmd[1].split()).issubset(CMD):
            find_gc = await DC.find_one({"_id": gid})
            if find_gc is None:
                if enable:
                    x = await message.reply_text("Command already enabled!!!")
                    await asyncio.sleep(5)
                    await x.delete()
                    return
                # Idempotent create of disabled command list
                await DC.update_one({"_id": gid}, {"$setOnInsert": {"cmd_list": cmd[1]}}, upsert=True)
                x = await message.reply_text("Command disabled!!!")
                await asyncio.sleep(5)
                await x.delete()
                return
            else:
                ocls: str = find_gc["cmd_list"]
                if set(cmd[1].split()).issubset(ocls.split()):
                    if enable:
                        if len(ocls.split()) == 1:
                            await DC.delete_one({"_id": gid})
                            x = await message.reply_text("Command enabled!!!")
                            await asyncio.sleep(5)
                            await x.delete()
                            return
                        ncls = ocls.split()
                        for i in cmd[1].split():
                            ncls.remove(i)
                        ncls = " ".join(ncls)
                    else:
                        x = await message.reply_text("Command already disabled!!!")
                        await asyncio.sleep(5)
                        await x.delete()
                        return
                else:
                    if enable:
                        x = await message.reply_text("Command already enabled!!!")
                        await asyncio.sleep(5)
                        await x.delete()
                        return
                    else:
                        lsncls = []
                        prencls = (ocls + " " + cmd[1]).replace("  ", " ")
                        for i in prencls.split():
                            if i not in lsncls:
                                lsncls.append(i)
                        ncls = " ".join(lsncls)
                await DC.update_one({"_id": gid}, {"$set": {"cmd_list": ncls}})
                x = await message.reply_text(
                    f"Command {'dis' if enable is False else 'en'}abled!!!"
                )
                await asyncio.sleep(5)
                await x.delete()
                return
        else:
            await message.reply_text("Hee, is that a command?!")


@Client.on_message(custom_filter.command(commands="anidisabled"), filters.group)
@control_user
async def list_disabled(client: Client, message: Message, mdata: dict):
    find_gc = await DC.find_one({"_id": mdata["chat"]["id"]})
    if find_gc is None:
        await message.reply_text("No commands disabled in this group!!!")
    else:
        lscmd = find_gc["cmd_list"].replace(" ", "\n")
        await message.reply_text(
            f"""List of commands disabled in **{mdata['chat']['title']}**

{lscmd}"""
        )


@Client.on_message(
    filters.user(DEV_USERS)
    & filters.command(["anidbcleanup", f"anidbcleanup{BOT_USERNAME}"], prefixes=trg)
)
@control_user
async def db_cleanup(client: Client, message: Message, mdata: dict):
    count = 0
    entries = ""
    st = datetime.now()
    x = await message.reply_text("Starting database cleanup in 5 seconds")
    et = datetime.now()
    pt = (et - st).microseconds / 1000
    await asyncio.sleep(5)
    await x.edit_text("Checking 1st collection!!!")
    async for i in GROUPS.find():
        await asyncio.sleep(2)
        try:
            await client.get_chat(i["_id"])
        except (cp, ci, pi):
            count += 1
            entries += str(await GROUPS.find_one(i)) + "\n\n"
            await GROUPS.find_one_and_delete(i)
            await SFW_GROUPS.find_one_and_delete({"id": i["_id"]})
            await DC.find_one_and_delete({"_id": i["_id"]})
            await AG.find_one_and_delete({"_id": i["_id"]})
            await HD_GRPS.find_one_and_delete({"_id": i["_id"]})
            await SP_GRPS.find_one_and_delete({"_id": i["_id"]})
        except fw:
            await asyncio.sleep(fw.x + 5)
    await asyncio.sleep(5)
    await x.edit_text("Checking 2nd collection!!!")
    async for i in AUTH_USERS.find():
        if i["id"] == "pending":
            count += 1
            entries += str(await AUTH_USERS.find_one({"_id": i["_id"]})) + "\n\n"
            await AUTH_USERS.find_one_and_delete({"_id": i["_id"]})
    async for i in AUTH_USERS.find():
        await asyncio.sleep(2)
        try:
            await client.get_users(i["id"])
        except pi:
            count += 1
            entries += str(await AUTH_USERS.find_one({"id": i["id"]})) + "\n\n"
            await AUTH_USERS.find_one_and_delete({"id": i["id"]})
        except fw:
            await asyncio.sleep(fw.x + 5)
    await asyncio.sleep(5)

    nosgrps = await GROUPS.estimated_document_count()
    nossgrps = await SFW_GROUPS.estimated_document_count()
    nosauus = await AUTH_USERS.estimated_document_count()
    if count == 0:
        msg = f"""Database seems to be accurate, no changes to be made!!!

**Groups:** `{nosgrps}`
**SFW Groups:** `{nossgrps}`
**Authorised Users:** `{nosauus}`
**Ping:** `{pt}`
"""
    else:
        msg = f"""{count} entries removed from database!!!

**New Data:**
    __Groups:__ `{nosgrps}`
    __SFW Groups:__ `{nossgrps}`
    __Authorised Users:__ `{nosauus}`

**Ping:** `{pt}`
"""
        if len(entries) > 4095:
            with open("entries.txt", "w+") as file:
                file.write(entries)
            return await x.reply_document("entries.txt")
        await x.reply_text(entries)
    await x.edit_text(msg)

@Client.on_message(custom_filter.command("anihelp"))
@control_user
async def help_(client: Client, message: Message, mdata: dict):
    gid = mdata['chat']['id']
    find_gc = await DC.find_one({'_id': gid})
    if find_gc is not None and 'anihelp' in find_gc['cmd_list'].split():
        return
    bot_us = (await client.get_me()).username
    try:
        id_ = mdata['from_user']['id']
    except KeyError:
        await client.send_message(
            gid,
            text="Click below button for bot help",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Help", url=f"https://t.me/{bot_us}/?start=anihelp")]])
        )
        return
    buttons = help_btns(id_)
    text='''This is a small guide on how to use me
    
**Basic Commands:**
Use /ping or !ping cmd to check if bot is online
Use /start or !start cmd to start bot in group or pm
Use /help or !help cmd to get interactive help on available bot cmds
Use /feedback cmd to contact bot owner'''
    if id_ in DEV_USERS:
        await client.send_message(gid, text=text, reply_markup=buttons)
        await client.send_message(
            gid,
            text="""Owners / Sudos can also use

- __/term__ `to run a cmd in terminal`
- __/eval__ `to run a python code like `__/eval print('UwU')__` `
- __/stats__ `to get stats on bot like no. of users, grps and authorised users`
- __/dbcleanup__ `to remove obsolete/useless entries in database`

Apart from above shown cmds"""
        )
    else:
        if gid==id_:
            await client.send_message(gid, text=text, reply_markup=buttons)
        else:
            await client.send_message(
                gid,
                text="Click below button for bot help",
                reply_markup=InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton(
                            "Help",
                            url=f"https://t.me/{BOT_USERNAME}/?start=anihelp"
                        )
                    ]]
                )
            )



@Client.on_message(custom_filter.command(commands=["aniconnect", "anidisconnect"]))
@control_user
async def connect_(client: Client, message: Message, mdata: dict):
    gid = mdata["chat"]["id"]
    find_gc = await DC.find_one({"_id": gid})
    if find_gc is not None and "connect" in find_gc["cmd_list"].split():
        return
    bot_us = (await client.get_me()).username
    try:
        id_ = mdata["from_user"]["id"]
    except KeyError:
        await client.send_message(
            gid,
            text="Go to bot pm to connect channel",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Bot PM", url=f"https://t.me/{bot_us}")]]
            ),
        )
        return
    if gid == id_:
        data = mdata["text"].split()
        try:
            channel = data[1]
        except BaseException:
            return await client.send_message(
                gid,
                text=(
                    "Please provide the channel id you wish to connect!!!"
                    + "\nExample: /aniconnect -100xxxxxxxxx"
                ),
            )
        if "-100" not in channel:
            return await client.send_message(
                gid, text="Please enter the full channel ID!!!"
            )
        if data[0] == "aniconnect":
            if await CC.find_one({"_id": str(channel)}):
                await client.send_message(
                    gid,
                    text=(
                        "Channel already connected"
                        + "\nIf someone else has access to it who doesn't own "
                        + "the channel, contact @SpiralTechDivision"
                    ),
                )
                return
            # Idempotent connect
            await CC.update_one({"_id": str(channel)}, {"$setOnInsert": {"usr": id_}}, upsert=True)
            await client.send_message(gid, text="Successfully connected the channel")
        else:
            k = await CC.find_one({"_id": str(channel)})
            if k and k["usr"] == id_:
                await CC.find_one_and_delete({"_id": str(channel)})
                await client.send_message(
                    gid, text="Successfully disconnected the channel"
                )
            else:
                await client.send_message(gid, text="Channel not connected")
    else:
        k = (await client.get_chat_member(gid, id_)).status
        if k == CHAT_DEV_USERS:
            if "aniconnect" in mdata["text"]:
                # Idempotent connect (group context)
                await CC.update_one({"_id": str(message.chat.id)}, {"$setOnInsert": {"usr": id_}}, upsert=True)
                await client.send_message(
                    gid, text="Successfully connected the channel"
                )
            else:
                await CC.find_one_and_delete({"_id": str(message.chat.id)})
                await client.send_message(
                    gid, text="Successfully disconnected the channel"
                )
            return
        await client.send_message(
            gid,
            text="Click below button for bot help",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Bot PM", url=f"https://t.me/{bot_us}")]]
            ),
        )


@Client.on_callback_query(filters.regex(pattern=r"helppp_(.*)"))
@check_user
async def help_dicc_parser(client: Client, cq: CallbackQuery, cdata: dict):
    await cq.answer()
    kek, qry, user = cdata["data"].split("_")
    text = HELP_DICT[qry]
    btn = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Back", callback_data=f"hlplist_{user}")]]
    )
    await cq.edit_message_text(text=text, reply_markup=btn)


@Client.on_callback_query(filters.regex(pattern=r"hlplist_(.*)"))
@check_user
async def help_list_parser(client: Client, cq: CallbackQuery, cdata: dict):
    await cq.answer()
    user = cdata["data"].split("_")[1]
    buttons = help_btns(user)
    text = """This is a small guide on how to use me

**Basic Commands:**
Use /start or !start cmd to start bot in group or pm
Use /help or !help cmd to get interactive help on available bot cmds
Use /anihelp for anime cmds
Use /feedback cmd to contact bot owner"""
    await cq.edit_message_text(text=text, reply_markup=buttons)


def help_btns(user):
    but_rc = []
    buttons = []
    hd_ = list(natsorted(HELP_DICT.keys()))
    for i in hd_:
        but_rc.append(InlineKeyboardButton(i, callback_data=f"helppp_{i}_{user}"))
        if len(but_rc) == 2:
            buttons.append(but_rc)
            but_rc = []
    if len(but_rc) != 0:
        buttons.append(but_rc)
    return InlineKeyboardMarkup(buttons)


@Client.on_message(
    filters.user(DEV_USERS)
    & filters.command(["anistats", f"anistats{BOT_USERNAME}"], prefixes=trg)
)
@control_user
async def stats_(client: Client, message: Message, mdata: dict):
    st = datetime.now()
    x = await message.reply_text("Collecting Stats!!!")
    et = datetime.now()
    pt = (et - st).microseconds / 1000
    nosus = await USERS.estimated_document_count()
    nosauus = await AUTH_USERS.estimated_document_count()
    nosgrps = await GROUPS.estimated_document_count()
    nossgrps = await SFW_GROUPS.estimated_document_count()
    nosmhdgrps = await MAL_HD_GRPS.estimated_document_count()
    s = await SP_GRPS.estimated_document_count()
    kk_response = await get("https://api.github.com/repos/lostb053/anibot")
    kk = kk_response.json()
    await x.edit_text(
        f"""
Stats:-

**Users:** {nosus}
**Authorised Users:** {nosauus}
**Groups:** {nosgrps}
**Subsplease Groups:** {s}
**MAL Headline Groups:** {nosmhdgrps}
**SFW Groups:** {nossgrps}
**Stargazers:** {kk.get("stargazers_count")}
**Forks:** {kk.get("forks")}
**Ping:** `{pt} ms`
"""
    )


@Client.on_message(
    filters.private
    & filters.command(["feedback", f"feedback{BOT_USERNAME}"], prefixes=trg)
)
@control_user
async def feed_(client: Client, message: Message, mdata: dict):
    owner = (await client.get_users(DEV_USERS[0])).username
    await client.send_message(
        mdata["chat"]["id"],
        f"For issues or queries please contact "
        + f"@{owner} or join @SpiralTechDivision",
    )


###### credits to @NotThatMF on tg since he gave me the code for it ######


@Client.on_message(
    filters.command(["anieval", f"anieval{BOT_USERNAME}"], prefixes=trg)
    & filters.user(DEV_USERS)
)
@control_user
async def eval_(client: Client, message: Message, mdata: dict):
    status_message = await message.reply_text("Processing ...")
    cmd = " "
    try:
        cmd = message.text.split(" ", maxsplit=1)[1]
    except IndexError:
        await message.reply_text("Give me something to evaluate.")
        return await status_message.delete()
    reply_to_ = message
    if message.reply_to_message:
        reply_to_ = message.reply_to_message
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()
    stdout, stderr, exc = None, None, None
    try:
        await aexec(cmd, client, message)
    except Exception:
        exc = traceback.format_exc()
    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    evaluation = ""
    if exc:
        evaluation = exc
    elif stderr:
        evaluation = stderr
    elif stdout:
        evaluation = stdout
    else:
        evaluation = "Success"
    final_output = "<b>EVAL</b>: "
    final_output += f"<code>{cmd}</code>\n\n"
    final_output += "<b>OUTPUT</b>:\n"
    final_output += f"<code>{evaluation.strip()}</code> \n"
    if len(final_output) > 4096:
        with io.BytesIO(str.encode(final_output)) as out_file:
            out_file.name = "eval.txt"
            await reply_to_.reply_document(
                document=out_file, caption=cmd[:1000], disable_notification=True
            )
    else:
        await reply_to_.reply_text(final_output)
    await status_message.delete()


async def aexec(code, client, message):
    exec(
        "async def __aexec(client, message): "
        + "".join(f"\n {l_}" for l_ in code.split("\n"))
    )
    return await locals()["__aexec"](client, message)


@Client.on_message(
    filters.user(DEV_USERS)
    & filters.command(["term", f"term{BOT_USERNAME}"], prefixes=trg)
)
@control_user
async def terminal(client: Client, message: Message, mdata: dict):
    if len(message.text.split()) == 1:
        await message.reply_text("Usage: `/term echo owo`")
        return
    args = message.text.split(None, 1)
    teks = args[1]
    if "\n" in teks:
        code = teks.split("\n")
        output = ""
        for x in code:
            shell = re.split(""" (?=(?:[^'"]|'[^']*'|"[^"]*")*$)""", x)
            try:
                # Use async subprocess instead of blocking subprocess.Popen
                process = await asyncio.create_subprocess_exec(
                    *shell, 
                    stdout=asyncio.subprocess.PIPE, 
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                if stderr:
                    raise Exception(stderr.decode())
            except Exception as err:
                LOGGER.error(err)
                await message.reply_text(
                    """
**Error:**
```{}```
""".format(
                        err
                    ),
                    parse_mode=enums.ParseMode.MARKDOWN,
                )
            output += "**{}**\n".format(code)
            output += stdout.decode("utf-8").rstrip()
            output += "\n"
    else:
        shell = re.split(""" (?=(?:[^'"]|'[^']*'|"[^"]*")*$)""", teks)
        for a in range(len(shell)):
            shell[a] = shell[a].replace('"', "")
        try:
            # Use async subprocess instead of blocking subprocess.Popen
            process = await asyncio.create_subprocess_exec(
                *shell, 
                stdout=asyncio.subprocess.PIPE, 
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            if stderr:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                errors = traceback.format_exception(
                    etype=exc_type, value=exc_obj, tb=exc_tb
                )
                await message.reply_text(
                    """**Error:**\n```{}```""".format("".join(errors)),
                    parse_mode=enums.ParseMode.MARKDOWN,
                )
                return
        except Exception:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            errors = traceback.format_exception(
                etype=exc_type, value=exc_obj, tb=exc_tb
            )
            await message.reply_text(
                """**Error:**\n```{}```""".format("".join(errors)),
                parse_mode=enums.ParseMode.MARKDOWN,
            )
            return
        output = stdout.decode("utf-8").rstrip()
    if str(output) == "\n":
        output = None
    if output:
        if len(output) > 4096:
            filename = "output.txt"
            with open(filename, "w+") as file:
                file.write(output)
            await client.send_document(
                message.chat.id,
                filename,
                reply_to_message_id=message.id,
                caption="`Output file`",
            )
            os.remove(filename)
            return
        await message.reply_text(
            f"**Output:**\n```{output}```", parse_mode=enums.ParseMode.MARKDOWN
        )
    else:
        await message.reply_text("**Output:**\n`No Output`")
