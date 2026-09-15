# Bleed-style Discord Bot — Version 1.1

Original implementation inspired by the requested feature set. It does not use Bleed's source code or branding.

## V1.1 additions

### Ticket DM reminders
The bot now actually sends reminders automatically.

- Only reminds when STAFF is waiting for the USER to respond.
- A staff message starts the reminder timer.
- A user message cancels/resets the staff-waiting state.
- If the user does not reply for the configured interval, the bot DMs them.
- Reminder interval is configurable from 5 minutes to 7 days.
- Reminder text is customizable.
- DMs are sent once per interval, not every worker tick.
- Opening and closing tickets can also DM the ticket owner.
- Staff can claim a ticket; the claim is optionally communicated by DM when reminders are enabled.

### Ticket variables

Use these in ticket messages:

- `{server}`
- `{server_id}`
- `{channel}`
- `{channel_name}`
- `{user}`
- `{username}`
- `{user_id}`
- `{staff}`
- `{staff_name}`

## Commands

### Welcome

```text
/welcome enable
/welcome disable
/welcome message text:Welcome {user} to {server}! You are member #{member_count}.
/welcome preview
```

### Tickets

```text
/tickets setup
/tickets category category:#Tickets
/tickets reminders enabled:true minutes:120
/tickets reminder-message text:🎫 Your ticket in {server} is still waiting for staff: {channel}
/tickets reminder-preview
```

The ticket panel has **Open Ticket**. Ticket channels have **Claim** and **Close Ticket**.

## Run

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your bot token.

For quick command syncing during development:

```env
TEST_GUILD_ID=YOUR_SERVER_ID
```

Then:

```bash
python bot.py
```

## Discord Developer Portal

Enable **Server Members Intent**. Message Content Intent is enabled in the code because ticket activity tracking uses message events.

Give the bot the permissions needed for your chosen moderation/ticket features. Never expose the bot token.


## Ticket reminder behavior

The reminder flow is:

```text
User opens ticket
    ↓
Staff sends a message
    ↓
Bot waits the configured interval
    ↓
User has not replied
    ↓
Bot DMs the user
```

A user reply stops that reminder cycle. The next staff reply starts a new cycle.

Example with a 24-hour interval:

```text
Monday 2:00 PM — User opens ticket
Monday 2:10 PM — Staff: "How can we help?"
Tuesday 2:10 PM — User hasn't replied
Tuesday 2:10 PM — Bot DMs user with reminder
Tuesday 3:00 PM — User replies
                  ↓
             reminder stops
```
