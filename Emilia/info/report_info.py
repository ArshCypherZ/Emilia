from Emilia import BOT_NAME

__mod_name__ = "Reports"

__help__ = f"""
> We're all busy people who don't have time to monitor our groups 24/7. But how do you react if someone in your group is spamming?

> Presenting reports; if someone in your group thinks someone needs reporting, they now have an easy way to call all admins.

**User commands**:

• `/report` — Reply to a message to report it for admins to review.
• @admins: Same as /report

**Admin commands**:
• `/reports <yes/no/on/off>` — Enable/disable user reports.

To report a user, simply reply to his message with @admin or /report; {BOT_NAME} will then reply with a message stating that admins have been notified. This message tags all the chat admins; same as if they had been @'ed.

**Note** that the report commands do not work when admins use them; or when used to report an admin. {BOT_NAME} assumes that admins don't need to report, or be reported!
"""
