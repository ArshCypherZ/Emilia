__mod_name__ = "Example to use"

__hidden__ = True

__help__ = """
> Welomes and goodbyes can be customised in many ways - here are some examples!

**Examples**:
• Turn on welcomes:
-> `/welcome on`

• Disable welcomes:
-> `/welcome off`

• Turn on goodbyes (note: goodbye messages won't be sent in groups with over 50 members):
-> `/goodbye on`

• Set a simple custom welcome message:
-> `/setwelcome Hi there, welcome to the chat! Remember to be respectful and follow the rules.`

• Set a custom welcome message, using fillings to automatically:
>  - use the new user's name
>  - use the current group name
>  - create a button to the group rules
-> /setwelcome Hi {first}, welcome to {chatname}! Remember to be respectful and follow the rules. {rules}

• Automatically delete old welcome messages:
-> `/cleanwelcome on`

• Get the welcome message without any formatting:
-> `/welcome noformat`
"""
