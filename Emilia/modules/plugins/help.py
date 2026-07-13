import html
import re

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.errors import BadRequest
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

from Emilia import BOT_USERNAME, LOGGER, custom_filter
from Emilia.data import HELPABLE, SUB_MODE
from Emilia.helper.disable import disable
from Emilia.helper.pagination_buttons import paginate_modules
from Emilia.utils.decorators import *

HELP_TEXT = """
**Main** commands available:
• /help: PM's you this message.
• /help `module name`: PM's you info about that module.
"""


async def help_parser(client, chat_id, text, keyboard=None):
    if not keyboard:
        LOGGER.info("Helpable length when calling /help: {}".format(len(HELPABLE)))
        keyboard = paginate_modules(0, HELPABLE, "help")
    await client.send_message(chat_id, text, reply_markup=keyboard)


@Client.on_message(custom_filter.command(commands="help", disable=True))
@disable
@rate_limit(RATE_LIMIT_GENERAL)
async def help_command(client, message):
    module_name = None
    if len(message.text.split()) >= 2:
        module_name = message.text.split()[1].lower()

    if message.chat.type != ChatType.PRIVATE:
        button_text = "Click me here for help!"
        text = "Contact me in PM for help!"
        redirect_url = f"t.me/{BOT_USERNAME}?start=help_"

        if module_name is not None:
            try:
                module_name = HELPABLE[module_name].__mod_name__
                text = f"Help for `{module_name.capitalize()}` module!"
                button_text = "Click here!"
                redirect_url = f"t.me/{BOT_USERNAME}?start=help_{module_name.lower()}"
            except KeyError:
                pass

        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=button_text, url=redirect_url)]]
        )
        await message.reply(text, reply_markup=buttons)
    else:
        if module_name is not None:
            await module_page(client, module_name, message)
        else:
            await help_parser(client, message.chat.id, HELP_TEXT)


@Client.on_message(custom_filter.command("start"), group=9)
async def redirectHelp(client, message):
    if (
        len(message.text.split()) >= 2
        and message.text.split()[1].split("_")[0] == "help"
    ):
        if len(message.text.split()) >= 2:
            module_name = message.text.split()[1].split("_")[1]
            await module_page(client, module_name, message)
        else:
            await help_parser(client, message.chat.id, HELP_TEXT)


async def help_button_callback(_, __, callback_query):
    if re.match(r"help_", callback_query.data):
        return True


def _parent_module(module: str):
    """Find the HELPABLE module whose __sub_mod__ list contains this hidden
    submodule's display name, so "Back" can return one level up instead of
    always jumping to the top-level module list."""
    for name, mod in SUB_MODE.items():
        for sub_mod in getattr(mod, "__sub_mod__", []):
            if sub_mod.lower() == module:
                return name
    return None


@Client.on_callback_query(filters.create(help_button_callback))
async def help_button(client, callback_query):
    mod_match = re.match(r"help_module\((.+?)\)", callback_query.data)
    back_match = re.match(r"help_back(?:\((.*?)\))?$", callback_query.data)
    page_match = re.match(r"help_page\((\d+)\)", callback_query.data)
    noop_match = re.match(r"help_noop", callback_query.data)
    start_match = re.match(r"help_start", callback_query.data)

    if noop_match:
        return await callback_query.answer()

    if start_match:
        from Emilia.modules.plugins.start.start import build_start_message

        text, markup, _ = await build_start_message(client)
        try:
            await callback_query.message.edit(
                text=text,
                reply_markup=markup,
                link_preview_options=LinkPreviewOptions(is_disabled=False),
            )
        except BadRequest:
            pass
        return await callback_query.answer()

    if page_match:
        page = int(page_match.group(1))
        try:
            await callback_query.message.edit(
                text=HELP_TEXT,
                reply_markup=paginate_modules(page, HELPABLE, "help"),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except BadRequest:
            pass
        return await callback_query.answer()

    if mod_match:
        module = mod_match.group(1)
        text = f"**{HELPABLE[module].__mod_name__}**\n"
        text += HELPABLE[module].__help__
        buttons = []
        button = []
        try:
            for sub_mod in SUB_MODE[module].__sub_mod__:
                button.append(
                    InlineKeyboardButton(
                        text=sub_mod, callback_data=f"help_module({sub_mod.lower()})"
                    )
                )
                if len(button) >= 2:
                    buttons.append(button)
                    button = []
            if button:
                buttons.append(button)
        except KeyError:
            pass
        parent = _parent_module(module)
        back_data = f"help_back({parent})" if parent else "help_back"
        buttons.append([InlineKeyboardButton(text="Back ", callback_data=back_data)])
        try:
            await callback_query.message.edit(text=html.escape(text), reply_markup=InlineKeyboardMarkup(buttons), link_preview_options=LinkPreviewOptions(is_disabled=True))
        except BadRequest:
            pass
        return await callback_query.answer()

    elif back_match:
        parent = back_match.group(1)
        try:
            if parent:
                await module_page(client, parent, callback_query.message, edit=True)
            else:
                await callback_query.message.edit(
                    text=HELP_TEXT,
                    reply_markup=paginate_modules(0, HELPABLE, "help"),
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
        except BadRequest:
            pass
        return await callback_query.answer()


async def module_page(client, module: str, message, edit: bool = False):
    button = []
    buttons = []
    try:
        text = f"**{HELPABLE[module].__mod_name__}**\n"
        text += HELPABLE[module].__help__

        try:
            for sub_mod in SUB_MODE[module].__sub_mod__:
                button.append(
                    InlineKeyboardButton(
                        text=sub_mod, callback_data=f"help_module({sub_mod.lower()})"
                    )
                )
                if len(button) >= 2:
                    buttons.append(button)
                    button = []
            if button:
                buttons.append(button)
        except KeyError:
            pass

    except KeyError:
        if edit:
            await message.edit(
                text=HELP_TEXT,
                reply_markup=paginate_modules(0, HELPABLE, "help"),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        else:
            await help_parser(client, message.chat.id, HELP_TEXT)
        return

    parent = _parent_module(module)
    back_data = f"help_back({parent})" if parent else "help_back"
    buttons.append([InlineKeyboardButton(text="Back ", callback_data=back_data)])

    if edit:
        await message.edit(
            text=html.escape(text),
            reply_markup=InlineKeyboardMarkup(buttons),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    else:
        await message.reply(
            text=html.escape(text),
            reply_markup=InlineKeyboardMarkup(buttons),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
