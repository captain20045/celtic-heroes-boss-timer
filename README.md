# Celtic Heroes Discord Boss Timer

A simple Discord slash-command bot for tracking Celtic Heroes boss respawn windows.

## Commands

- `/setchannel` - use the current channel for boss alerts
- `/setrole @Role` - role to ping for boss alerts
- `/setboss boss min_hours max_hours` - add/update respawn window
- `/removeboss boss` - remove boss
- `/kill boss` - record a kill and start timer
- `/clear boss` - clear a timer
- `/bosses` - show all bosses/timers
- `/bosslist` - alias of `/bosses`, with countdown / DUE display
- `/nextboss` - show the next upcoming spawn window

## Setup

1. Install Python 3.11+.
2. Create a Discord application/bot in the Discord Developer Portal.
3. Invite the bot with scopes:
   - bot
   - applications.commands
4. Give the bot permissions:
   - View Channels
   - Send Messages
   - Embed Links
5. Install dependencies:

   pip install -r requirements.txt

6. Set your token.

Windows PowerShell:
   $env:DISCORD_TOKEN="YOUR_BOT_TOKEN"

Windows CMD:
   set DISCORD_TOKEN=YOUR_BOT_TOKEN

Git Bash:
   export DISCORD_TOKEN="YOUR_BOT_TOKEN"

7. Run:

   python bot.py

## First Discord setup

In your server:

1. `/setchannel`
2. Optional: `/setrole @Boss`
3. Configure actual boss windows, for example:
   `/setboss boss:Gelebron min_hours:32 max_hours:60`
4. After a kill:
   `/kill boss:Gelebron`

IMPORTANT:
Respawn values can change during Celtic Heroes events/patches.
Use `/setboss` whenever the game's current timers change.


## Boss list display logic

For a boss with a 35-60 minute spawn window:

- Immediately after kill: `Boss — 35m`
- 30 minutes later: `Boss — 5m`
- At 35 minutes: `Boss — (DUE) 25m left`
- At 45 minutes: `Boss — (DUE) 15m left`
- After 60 minutes: `Boss — (OVERDUE)`

The countdown before DUE is based on the minimum respawn time.
Once DUE starts, the countdown is based on the maximum respawn time.
