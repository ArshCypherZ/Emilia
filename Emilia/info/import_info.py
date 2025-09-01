__mod_name__ = "Import/Export"

__help__ = """
Some people just want to see the world burn. Others, just want to have a way of grouping their chat data in one place so they can export their configuration to other chats!

Emilia allows you to import/export settings for chat, so you can quickly set up other chats using a preexisting template. Instead of setting the same settings over and over again in different chats, you can use this feature to copy the general configuration across groups.
The generated file is in standard JSON format, so if there are any settings you don't want to import to your other chats, just open the file and edit it before importing.
Exporting settings can be done by any administrator, but for security reasons, importing can only be done by the group creator.

The following modules will have their data exported:
• blocklists
• disable
• filters
• welcome
• locks
• notes
• rules
• warnings

**Chat owner commands**:
• /export: Generate a file containing all your chat data.
• /import: Import the settings in the replied to data file.
• /chatreset: Reset all the chat settings. This means removing all settings.

**Examples**:
• To export only specific categories, use:
-> `/export notes filters`

• Or, to import only specific categories from a file, use:
-> `/import rules welcome`


**Note**: To avoid abuse, this command is heavily rate limited; this is to make sure that people importing/exporting data don't slow down the bot.

"""
