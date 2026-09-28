# 08 · Executive command channel ("Ask TRAVIS anything")

> "Tap, talk or text. Give me instructions however it suits you."

The executive texts TRAVIS's number. Travis Core answers. Only numbers in `executive.command_numbers` are treated as commands; everyone else's text becomes a message for the exec.

## Two engines

| | LLM engine | Rule engine |
|---|---|---|
| When | `ANTHROPIC_API_KEY` set | No key, or the LLM call fails |
| Understands | Anything | ~10 command shapes |
| How | Tool-use loop (max 8 steps) over exec tools + booking/knowledge tools, prompt in `prompts/exec-command-channel.md` | Regexes in `commands.py` |
| Context | Last 12 turns of plain-text history | None |

The rule engine guarantees the channel never goes dark, even with no LLM.

## Commands (rule engine) and example LLM requests

| Text | Result |
|---|---|
| `brief` / `status` | Today's briefing, on demand |
| `schedule`, `schedule tomorrow`, `schedule fri` | The day's calendar |
| `who called`, `who called about the lease` | Recent calls/messages matching |
| `move my 10am to thursday` | First valid Thursday slot |
| `move my 3:30 to friday at 11` | Exactly Friday 11 if valid |
| `block tomorrow 2-4pm` | Hold on the calendar |
| `remember that Cate's fund closes Oct 30` | Memory saved |
| `what do you know about cate` | Memories recalled |
| `done tom` | Tom's messages marked handled |
| LLM: "Book Priya for 45 minutes next week, mornings only, and tell her it's about Q4 capacity" | `check_availability` → `book_meeting` |
| LLM: "Who's waiting on me and what do they want?" | `who_called` → summary |
| LLM: "Cancel the 3:30." | Asks for PIN → `cancel_meeting` |
| LLM: "Have Marcus follow up with Apex about the August invoice by Friday" | `create_followup(owner=cfo_office)` → Marcus gets a text |

## Security

- **Sender allowlist**: `command_numbers`. SMS sender IDs can be spoofed, so:
- **PIN for destructive actions**: cancellations (and anything you add that sends messages to third parties or deletes data) require `command_pin`.
- **Twilio signature validation** on `/sms/inbound` so nobody can POST fake texts to your server.
- **No outbound messaging to arbitrary people** from this channel in the reference build. If you add "text Priya that I'm running late", require a confirmation reply first ("Send to Priya Nair +1…? Reply YES").

## Adding voice commands for the exec

On the roadmap: when the caller ID is a command number, the voice assistant switches to exec mode (read messages, today's schedule, move a meeting). Implementation sketch: in `assistant-request`, detect the exec's number and return a different assistant (or `assistantOverrides` with a different system prompt and the exec tool set). Protect it with a spoken PIN, since caller ID is spoofable.

## Web / app chat

`POST /exec/command {"text": "..."}` (admin token) is the same channel as JSON. A dashboard or mobile shortcut (iOS Shortcuts "Get contents of URL") can use it directly.
