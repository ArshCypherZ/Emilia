# DONE: Emilia strings

import random

from telethon import events

from Emilia import telethn

OWO = [
    "Emilia is always here for my Senpai >w<",
    "You called for me? :p",
    "*bites*",
    "nya~ i am here!!!",
    "*listens*",
    "I came only for you <3",
    "Want me to pat you? You sneaky lil fox!",
    "Yes, I am Emilia",
    "Nobody calls me by my name, I am supreme :p",
    "Well well, I came, now what?",
    "nya nya nyaaaaa",
    "What? Want a kiss? huhhhhh!!",
    "Yeah yeah, I know I am underage... so?",
    ".......",
    "Are you... are you Senpai?",
    "Ah~ I might fall for you <3",
    'Allow me the privilege of distorting your life :")',
    "Do you have a name, or can I call you mine??",
    "Time for some more fun strings!",
    "I bring memes and virtual cookies with me!",
    "Do you believe in love at first chat?",
    "If I were a cat, I'd purr for you.",
    "Roses are red, violets are blue, I'm here for you!",
    "Can I borrow a kiss? I promise I'll give it back.",
    "I'm like a Ctrl+C, I copy your heart.",
    "I'm not a photographer, but I can definitely picture us together.",
    "Are you a keyboard? Because you're just my type.",
    "Do you have a map? I just got lost in your messages.",
    "I'm not a bot, but I'm programmed to make you smile.",
    "If looks could GIF, you'd be a looping masterpiece.",
    "I must be a snowflake, because I've fallen for you.",
    "Are you Wi-Fi? Because I'm feeling a connection.",
    "You must be made of copper and tellurium because you're Cu-Te!",
    "Is your name Google? Because you have everything I've been searching for.",
    "Is your name Wi-Fi? Because I'm feeling a strong connection.",
    "If you were a fruit, you'd be a fineapple.",
    "Are you a campfire? Because you're hot and I want s'more.",
    "If you were a vegetable, you'd be a cute-cumber!",
    "Are you a magician? Whenever I look at you, everyone else disappears.",
    "You must be a parking ticket, because you've got 'Fine' written all over you.",
    "Are you a bank loan? Because you have my interest.",
    "Is your name Chapstick? Because you're da balm!",
    "Do you have a name or can I call you mine?",
    "I'm not a photographer, but I can definitely picture us together.",
    "Can I follow you home? My parents always told me to follow my dreams.",
    "If you were a vegetable, you'd be a cute-cumber!",
    "Are you a campfire? Because you're hot and I want s'more.",
    "Are you French? Because Eiffel for you.",
    "Do you have a sunburn, or are you always this hot?",
    "Is your name Google? Because you have everything I've been searching for.",
    "Are you Australian? Because when I look at you, I feel like I'm down under.",
    "Do you have a name or can I call you mine?",
    "Do you believe in fate? Because I think we were destined to meet.",
    "Is your name Wi-Fi? Because I'm really feeling a connection.",
    "Do you have a pencil? Cause I want to erase your past and write our future.",
    "Are you a keyboard? Because you're my type!",
    "If you were a cat, you'd purr-fect.",
    "If kisses were snowflakes, I'd send you a blizzard.",
    "Are you made of copper and tellurium? Because you're Cu-Te.",
    "Do you have a map? I keep getting lost in your eyes.",
    "Are you a campfire? Because you're hot and I want s'more.",
    "Do you believe in love at first chat?",
    "Are you a bank loan? Because you have my interest!",
    "Is your name Chapstick? Because you're da balm!",
    "I must be a snowflake, because I've fallen for you.",
    "Are you Wi-Fi? Because I'm feeling a connection.",
    "You must be made of copper and tellurium because you're Cu-Te!",
]


@telethn.on(events.NewMessage(pattern="(?i)Emilia$"))
async def Emi_(m: events.NewMessage):
    if getattr(m.client, "is_clone", False):
        return
    uwu = random.choice(OWO)
    await m.reply(uwu)