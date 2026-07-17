import io
import re
from dataclasses import dataclass

from pyrogram import Client, enums
from pyrogram.types import LinkPreviewOptions

from Emilia import BOT_USERNAME, LOGGER, custom_filter
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get
from Emilia.utils.decorators import *

LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
REQUEST_HEADERS = {
    "User-Agent": f"EmiliaBot/1.0 TelegramBot @{BOT_USERNAME}",
    "Accept": "application/json,*/*;q=0.8",
}
MAX_TEXT_MESSAGE = 3800


@dataclass
class LyricsResult:
    title: str
    artist: str
    lyrics: str
    source: str
    url: str | None = None


def _strip_synced_timestamps(text: str) -> str:
    return re.sub(
        r"^\s*\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]\s*", "", text, flags=re.MULTILINE
    )


def _clean_lyrics(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n?\s*\d*Embed\s*$", "", text, flags=re.IGNORECASE)
    text = text.replace("You might also like", "")
    lines = [line.strip() for line in text.split("\n")]

    cleaned_lines = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                cleaned_lines.append("")
            blank = True
            continue
        cleaned_lines.append(line)
        blank = False

    return "\n".join(cleaned_lines).strip()


def _select_lrclib_result(results: list[dict]) -> dict | None:
    for result in results:
        if result.get("instrumental"):
            continue
        if result.get("plainLyrics") or result.get("syncedLyrics"):
            return result
    return None


async def _fetch_from_lrclib(query: str) -> LyricsResult | None:
    response = await get(
        LRCLIB_SEARCH_URL,
        params={"q": query},
        headers=REQUEST_HEADERS,
        timeout=12,
    )
    if response.status_code != 200:
        return None

    try:
        data = response.json()
    except Exception:
        return None

    if not isinstance(data, list):
        return None

    result = _select_lrclib_result(data)
    if not result:
        return None

    lyrics = result.get("plainLyrics") or _strip_synced_timestamps(
        result.get("syncedLyrics") or ""
    )
    lyrics = _clean_lyrics(lyrics)
    if not lyrics:
        return None

    return LyricsResult(
        title=result.get("trackName") or result.get("name") or query,
        artist=result.get("artistName") or "Unknown Artist",
        lyrics=lyrics,
        source="LRCLIB",
    )


async def _fetch_lyrics(query: str) -> LyricsResult | None:
    return await _fetch_from_lrclib(query)


def _safe_filename(title: str, artist: str) -> str:
    value = f"{artist} - {title}"
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value).strip(" ._-")
    return (value[:80] or "lyrics") + ".txt"


async def _send_lyrics(message, result: LyricsResult):
    header = f"Lyrics: {result.artist} - {result.title}\nSource: {result.source}"
    if result.url:
        header += f"\n{result.url}"

    body = f"{header}\n\n{result.lyrics}"
    if len(body) <= MAX_TEXT_MESSAGE:
        return await message.reply_text(
            body,
            parse_mode=enums.ParseMode.DISABLED,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    preview = body[:MAX_TEXT_MESSAGE].rsplit("\n", 1)[0]
    await message.reply_text(
        f"{preview}\n\nFull lyrics attached as a text file.",
        parse_mode=enums.ParseMode.DISABLED,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )

    lyrics_file = io.BytesIO(body.encode("utf-8"))
    lyrics_file.name = _safe_filename(result.title, result.artist)
    await message.reply_document(
        document=lyrics_file,
        caption=f"Lyrics: {result.artist} - {result.title}",
        parse_mode=enums.ParseMode.DISABLED,
    )


@usage("/lyrics [song name]")
@example("/lyrics The Chain Fleetwood Mac")
@description("Fetches lyrics for the requested song.")
@Client.on_message(custom_filter.command(commands="lyrics", disable=True))
@rate_limit(RATE_LIMIT_GENERAL)
@disable
async def lyrics(_, message):
    query = " ".join(getattr(message, "command", [])[1:]).strip()
    if not query:
        return await usage_string(message, lyrics)

    status = await message.reply_text("Searching lyrics...")
    try:
        result = await _fetch_lyrics(query)
        if not result:
            return await status.edit_text(
                "I could not find lyrics for that. Try `artist - song title`."
            )

        await status.delete()
        await _send_lyrics(message, result)
    except Exception:
        LOGGER.exception("Unexpected error while fetching lyrics")
        await status.edit_text("I could not fetch lyrics right now.")
