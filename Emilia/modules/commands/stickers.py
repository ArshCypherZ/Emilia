# DONE: Stickers

import random
from asyncio import sleep

import emoji
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, PackShortNameOccupied
from pyrogram.raw import functions as raw_functions
from pyrogram.raw import types as raw_types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia import db
from Emilia.custom_filter import register
from Emilia.helper.disable import disable

pkang = db.pkang


def get_emoji(v):
    # `emoji.UNICODE_EMOJI` was removed in emoji>=2.0; EMOJI_DATA is the current
    # lookup table (keyed by the emoji character itself).
    p = "".join(c for c in v if c in emoji.EMOJI_DATA)
    if len(p) != 0:
        return p[0]
    return None


@register(pattern="pkang|packkang", disable=True)
@disable
async def pck_kang__(client, message):
    if not message.reply_to_message_id:
        return await message.reply_text("Please reply to a sticker.")
    r = message.reply_to_message
    if not r.sticker:
        return await message.reply_text(
            "That's not a sticker file. Please reply to a sticker."
        )
    if len(message.text.split(" ", 1)) == 2:
        pname = message.text.split(" ", 1)[1]
        emoji_ = get_emoji(pname)
        if emoji_:
            if pname.startswith(emoji_):
                emoji_ = None
            else:
                pname = pname.replace(emoji_, "")
    else:
        pname = f"{message.from_user.first_name}'s pKang pack"
        emoji_ = None
    # pyrogram exposes the sticker's pack via set_name instead of raw document
    # attributes
    if not r.sticker.set_name:
        return await message.reply_text("That sticker is not part of any pack to kang!")

    _stickers = await client.invoke(
        raw_functions.messages.GetStickerSet(
            stickerset=raw_types.InputStickerSetShortName(
                short_name=r.sticker.set_name
            ),
            hash=0,
        )
    )
    stk = []
    if emoji_:
        for x in _stickers.documents:
            stk.append(
                raw_types.InputStickerSetItem(
                    document=raw_types.InputDocument(
                        id=x.id,
                        access_hash=x.access_hash,
                        file_reference=x.file_reference,
                    ),
                    emoji=emoji_,
                )
            )
    else:
        for x in _stickers.documents:
            stk.append(
                raw_types.InputStickerSetItem(
                    document=raw_types.InputDocument(
                        id=x.id,
                        access_hash=x.access_hash,
                        file_reference=x.file_reference,
                    ),
                    emoji=(x.attributes[1]).alt,
                )
            )
    pack = 1
    xp = await pkang.find_one({"user_id": message.from_user.id})
    if xp:
        pack = xp.get("pack") + 1
    await pkang.update_one(
        {"user_id": message.from_user.id}, {"$set": {"pack": pack}}, upsert=True
    )
    pm = random.choice(
        ["af", "bq", "cj", "dp", "eu", "fw", "g", "hu", "wuw", "uw", "hk", "lm", "jr"]
    )
    peer = await client.resolve_peer(message.from_user.id)
    input_user = raw_types.InputUser(user_id=peer.user_id, access_hash=peer.access_hash)
    try:
        p = await client.invoke(
            raw_functions.stickers.CreateStickerSet(
                user_id=input_user,
                title=pname,
                short_name=f"{pm}{message.from_user.id}_{pack}_by_Elf_Robot",
                stickers=stk,
            )
        )
    except PackShortNameOccupied:
        await sleep(5)
        pack += 1
        p = await client.invoke(
            raw_functions.stickers.CreateStickerSet(
                user_id=input_user,
                title=pname + f"Vol {pack}",
                short_name=f"{pm}{message.from_user.id}_{pack}_by_Elf_Robot",
                stickers=stk,
            )
        )
    except FloodWait as fw:
        await sleep(fw.value)
    except Exception as ex:
        return await message.reply_text(str(ex))
    await message.reply_text(
        f"Sticker set successfully created and added to <b><a href='http://t.me/addstickers/{p.set.short_name}'>Pack</a></b>.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "View Pack", url=f"http://t.me/addstickers/{p.set.short_name}"
                    )
                ]
            ]
        ),
        parse_mode=ParseMode.HTML,
    )
