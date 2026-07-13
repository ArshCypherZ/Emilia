from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.data import HIDDEN_MOD


class EqInlineKeyboardButton(InlineKeyboardButton):
    def __eq__(self, other):
        return self.text == other.text

    def __lt__(self, other):
        return self.text < other.text

    def __gt__(self, other):
        return self.text > other.text


def paginate_modules(_page_n, module_dict, prefix, chat=None):
    if not chat:
        modules = sorted(
            [
                EqInlineKeyboardButton(
                    x.__mod_name__,
                    callback_data="{}_module({})".format(
                        prefix, x.__mod_name__.lower()
                    ),
                )
                for x in module_dict.values()
            ]
        )
    else:
        modules = sorted(
            [
                EqInlineKeyboardButton(
                    x.__mod_name__,
                    callback_data="{}_module({},{})".format(
                        prefix, chat, x.__mod_name__.lower()
                    ),
                )
                for x in module_dict.values()
            ]
        )

    visible = [m for m in modules if HIDDEN_MOD.get(m.text.lower()) is None]

    # Chunk to at most 3 columns x 8 rows per page and add a pager row.
    COLS, ROWS = 3, 8
    per_page = COLS * ROWS
    total_pages = max(1, (len(visible) + per_page - 1) // per_page)
    page_n = max(0, min(int(_page_n), total_pages - 1))

    start = page_n * per_page
    page_items = visible[start : start + per_page]

    pairs = [page_items[i : i + COLS] for i in range(0, len(page_items), COLS)]

    if total_pages > 1:
        prev_p = (page_n - 1) % total_pages
        next_p = (page_n + 1) % total_pages
        pairs.append(
            [
                EqInlineKeyboardButton(
                    "《", callback_data="{}_page({})".format(prefix, prev_p)
                ),
                EqInlineKeyboardButton(
                    "Back", callback_data="{}_start".format(prefix)
                ),
                EqInlineKeyboardButton(
                    "》", callback_data="{}_page({})".format(prefix, next_p)
                ),
            ]
        )

    return InlineKeyboardMarkup(pairs)


async def build_keyboard(buttons):
    keyb = []
    for btn in buttons:
        if btn.same_line and keyb:
            await keyb[-1].append([InlineKeyboardButton(btn.name, url=btn.url)])
        else:
            await keyb.append([InlineKeyboardButton(btn.name, url=btn.url)])

    return keyb


async def revert_buttons(buttons):
    res = ""
    for btn in buttons:
        if btn.same_line:
            res += "\n[{}](buttonurl://{}:same)".format(btn.name, btn.url)
        else:
            res += "\n[{}](buttonurl://{})".format(btn.name, btn.url)

    return res
