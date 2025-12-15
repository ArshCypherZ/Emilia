from Emilia import BOT_NAME

__mod_name__ = "Rankings"

__sub_mod__ = ["Karma"]

__help__ = f"""
**Leveling System**

The Leveling System rewards active participation in group chats. Users earn Experience Points (XP) by chatting, which unlocks new Ranks and features.

**Core Commands:**
• `/register [name]` - Create your profile to start earning XP.
• `/rank` - View your Rank Card, current stats, and progress.
• `/leaderboard` - Display the top users in the current chat.
• `/daily` - Claim your daily XP bonus. Consecutive claims build a **Streak Bonus**.
• `/weekly` - Claim your weekly XP bonus (available every 7 days).
• `/rankings` - View detailed information about Ranks and requirements.

**Advanced Features:**
• **Prestige**: Upon reaching the maximum rank, use `/prestige` to reset your level in exchange for a **Prestige Badge** and a permanent **XP Multiplier**.
• **Reputation**: Reply to a helpful user with `/thanks` or `+rep` to increase their Reputation score. Use `/info` to view a user's Reputation.
• **Events**: Administrators may activate global XP multipliers during special events.

**Admin:**
• `/level [on/off]` - Enable or disable the leveling system in the current chat.

Note: You can link your Leveling profile with the Karma system using `/karma`.
"""
