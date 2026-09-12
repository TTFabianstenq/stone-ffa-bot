# Stone FFA Bot

Official Discord bot for the **Stone FFA** Minecraft server.

A production-ready moderation, ticketing, logging, and utility bot built with **discord.py** and Python 3.10+.

## Features

### Moderation
- `/ban`, `/unban`, `/kick`
- `/timeout`, `/untimeout`
- `/warn`, `/warnings` (persistent SQLite storage)
- `/clear`, `/slowmode`, `/lock`, `/unlock`
- Role hierarchy protection
- Permission checks and clear error messages
- All actions logged to a configurable log channel

### Tickets
- Button-based ticket creation panel (`/ticketpanel`)
- Private ticket channels under a configurable category
- Claim / Close / Delete controls
- Transcript generation
- Limit on open tickets per user
- Persistent views (buttons survive bot restarts)

### Logging
- Member join / leave
- Bans / unbans
- Timeouts
- Message deletions and edits
- Ticket lifecycle events

### Utility
- `/ping`, `/serverinfo`, `/userinfo`, `/avatar`
- `/botinfo`, `/help`

## Requirements

- Python 3.10 or higher
- A Discord bot application with Server Members Intent and Message Content Intent enabled

## Installation

```bash
git clone https://github.com/TTFabianstenq/stone-ffa-bot.git
cd stone-ffa-bot
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set DISCORD_TOKEN and the channel/role IDs
python bot.py
```

## Configuration

All secrets and IDs go in `.env` (never commit this file).

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Bot token from Developer Portal |
| `GUILD_ID` | Recommended | Your server ID (instant command sync) |
| `LOG_CHANNEL_ID` | Recommended | Channel for logs |
| `STAFF_ROLE_ID` | Recommended | Staff role |
| `ADMIN_ROLE_ID` | Optional | Admin role |
| `TICKET_CATEGORY_ID` | Recommended | Category for ticket channels |
| `TRANSCRIPT_CHANNEL_ID` | Recommended | Channel for transcripts |
| `MAX_TICKETS_PER_USER` | Optional | Default 1 |
| `BOT_ACTIVITY` | Optional | Status text |
| `DATABASE_PATH` | Optional | Default `data/stone_ffa.db` |

## Discord Developer Portal Setup

1. Create an application at https://discord.com/developers/applications
2. Add a bot and copy the token
3. Enable **Server Members Intent** and **Message Content Intent**
4. Invite with scopes `bot` + `applications.commands` and the permissions listed in the README (Ban, Kick, Moderate Members, Manage Channels, Manage Messages, etc.)

## Security

- Never commit `.env`
- Never share your bot token
- Hierarchy checks prevent lower staff from moderating higher roles

## License

Provided for the Stone FFA community.
