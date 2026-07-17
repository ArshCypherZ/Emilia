import urllib.parse
from pyrogram.enums import ParseMode
from pyrogram.types import LinkPreviewOptions

from Emilia import LOGGER
from Emilia.custom_filter import register
from Emilia.helper.disable import disable
from Emilia.utils.async_http import get
from Emilia.utils.decorators import *


def get_weather_emoji(desc: str) -> str:
    desc = desc.lower()
    if "sunny" in desc or "clear" in desc:
        return "☀️"
    if "cloudy" in desc or "overcast" in desc or "partly cloudy" in desc:
        return "☁️"
    if "rain" in desc or "drizzle" in desc or "shower" in desc or "patchy rain" in desc:
        return "🌧️"
    if "snow" in desc or "flurry" in desc or "ice" in desc or "sleet" in desc:
        return "❄️"
    if "thunder" in desc or "storm" in desc:
        return "⛈️"
    if "fog" in desc or "mist" in desc or "haze" in desc:
        return "🌫️"
    return "🌡️"


@usage("/weather [city]")
@example("/weather Tokyo")
@description("Get the current weather conditions for a city.")
@register(pattern="weather", disable=True)
@disable
@exception
@rate_limit(RATE_LIMIT_GENERAL)
async def weather(client, message):
    try:
        query = message.text.split(None, 1)[1].strip()
    except IndexError:
        return await usage_string(message, weather)

    if not query:
        return await usage_string(message, weather)

    status_msg = await message.reply_text(f"Fetching weather for `{query}`...")

    try:
        # Fetch weather from wttr.in in JSON format
        url = f"https://wttr.in/{urllib.parse.quote(query)}?format=j1"
        response = await get(url, timeout=10)
        
        if response.status_code != 200:
            await status_msg.edit_text("Could not fetch weather data. Please make sure the city name is correct.")
            return

        data = response.json()
        if not data or "current_condition" not in data:
            await status_msg.edit_text("Could not find weather details for that location.")
            return

        cond = data["current_condition"][0]
        temp = cond.get("temp_C", "N/A")
        feels_like = cond.get("FeelsLikeC", "N/A")
        humidity = cond.get("humidity", "N/A")
        wind = cond.get("windspeedKmph", "N/A")
        
        desc = "N/A"
        if "weatherDesc" in cond and cond["weatherDesc"]:
            desc = cond["weatherDesc"][0].get("value", "N/A")

        area = "Unknown Location"
        country = ""
        if "nearest_area" in data and data["nearest_area"]:
            area_info = data["nearest_area"][0]
            if "areaName" in area_info and area_info["areaName"]:
                area = area_info["areaName"][0].get("value", "Unknown Area")
            if "country" in area_info and area_info["country"]:
                country = f", {area_info['country'][0].get('value', '')}"

        emoji = get_weather_emoji(desc)
        
        result_text = (
            f"⚡ **Weather report for {area}{country}**\n\n"
            f"{emoji} **Condition:** `{desc}`\n"
            f"🌡️ **Temperature:** `{temp}°C` (Feels like `{feels_like}°C`)\n"
            f"💧 **Humidity:** `{humidity}%`\n"
            f"💨 **Wind Speed:** `{wind} km/h`"
        )
        
        await status_msg.edit_text(
            result_text,
            parse_mode=ParseMode.MARKDOWN,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
    except Exception as e:
        LOGGER.error(f"Error in weather command: {e}")
        await status_msg.edit_text("An error occurred while fetching weather details.")
