from pyrogram import errors

# All new user-facing copy goes here. Future i18n will key off these names.

# repeated literals (deduplicated from tele/ and pyro/)
YES_NO_ON_OFF = "Your input was not recognised as one of: yes/no/on/off"
YES_NO_ON_OFF_RETRY = (
    "To change this setting, try this command again followed by one of yes/no/on/off"
)
NO_SUCH_FED = "This FedID does not refer to an existing federation."
NOT_IN_ANY_FED = "This chat isn't in any federations."
INVALID_FEDID = "This isn't a valid FedID format!"
NSFW_NOT_ACTIVE = "NSFW is not activated"
LEVELS_NOT_ACTIVE = (
    "Levelling system is not active in this chat. To turn it on use `/level on`"
)
GROUP_ONLY_CMD = "This command is made to be used in group chats, not in pm!"
NOT_FOR_YOU = "This action is not intended for you."

# admin
CAN_CHANGE_INFO = "You need to be admin and should have can_change_info permission to perform this task."
NOT_ADMIN = "You need to be an admin to perform this task."
NOT_OWNER = "You need to be owner of this chat to perform this task."
ON_ADMIN = "You cannot perform this command on admins."
OFF_ADMIN = "You cannot perform this command on non-admins."
CAN_BAN = "You need to be admin and should have ban_right to perform this task."
CAN_PROMOTE = (
    "You need to be admin and should have promote_user right to perform this task."
)
CAN_PIN = "You need to be admin and should have pin_message right to perform this task."
CAN_DELETE = (
    "You need to be admin and should have delete_message right to perform this task."
)
NOT_TOPIC = (
    "You need to be admin and should have manage_topics right to perform this task."
)
NOT_FORUM = "This only works in topics-enabled groups."

# bot
botban = (
    "You need to make me admin with ban_users right so that i can perform this command!"
)
botpromote = "You need to make me admin with promote_users right so that i can perform this command!"
botinfo = "You need to make me admin with can_change_info right so that i can perform this command!"

# private
is_pvt = "Group only command."

# errors
index = "Please provide me some term or reply with some text to perform this command correctly."
nouser = "No user found."
invalid = "Invalid username/id given."
media = "Reply with some media/photo to perform this command."
imedia = "Invalid file/media provided"

# requests
REQ_NO_QUERY = "Please provide the name of the content you want to search or request.\nExample: `/req Interstellar`"
REQ_CHANNEL_NOT_SET = "No request channel is configured to queue requests."
REQ_DISABLED = "The content request system is currently disabled in this chat."
REQ_NOT_CONFIGURED = "> **Not Configured**\n• Admins must configure search channels via `/addchannel <id>` and request channel via `/setreq <id>`."
REQ_LIMIT_EXCEEDED = "> **Daily Request Limit Reached**\n• You have reached your limit of **{}** requests for today in this chat."
REQ_ADMIN_ONLY = "You must be an administrator to perform this command."



# exceptions
error_messages = {
    errors.ChatSendPlainForbidden: "I don't have permission to send text messages in this chat.",
    errors.ChatAdminRequired: "You need to make me an admin with appropriate rights so that I can perform this command!",
    errors.AdminsTooMuch: "Already too many admins.",
    errors.AdminRankInvalid: "Title too large or invalid title provided.",
    errors.BotChannelsNa: "This user was promoted by someone else, so I cannot change admin privileges.",
    errors.AdminRankEmojiNotAllowed: "Emojis are not allowed in the admin's title.",
    errors.PhotoCropSizeSmall: "The image is too small.",
    errors.ImageProcessFailed: "Failed to process the image.",
    errors.ChatAboutNotModified: "The about text should be different than the current one.",
    errors.ChatAboutTooLong: "The about text is too long. Please provide a shorter one.",
    errors.ChatSendMediaForbidden: "I am not allowed to send media in this chat. Please make me an admin to do so.",
    errors.ChatSendGifsForbidden: "I am not allowed to send gifs in this chat. Please make me an admin to do so.",
    errors.ChatSendStickersForbidden: "I am not allowed to send stickers in this chat. Please make me an admin to do so.",
    errors.ChatNotModified: "The chat title provided is the same as the current one.",
    errors.TopicDeleted: "The topic is already deleted.",
    errors.ChannelInvalid: "I can't access that chat. Make sure I'm a member of it and try again.",
}
