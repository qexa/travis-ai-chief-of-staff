# Prompts

| File | Used by | Purpose |
|---|---|---|
| `travis-system-prompt.md` | Voice assistant (`voice/vapi-assistant.json` is generated from it) | TRAVIS on the phone |
| `exec-command-channel.md` | `server/travis/commands.py` (LLM engine) | TRAVIS by text with the executive |
| `end-of-call-analysis.md` | Voice platform post-call analysis | Summary, structured data, pass/fail rubric |
| `persona-and-voice.md` | You | Character sheet, voice selection and tuning |

The optional LLM briefing prompt is in `docs/06-morning-briefing.md`.

Variables in `{{double_braces}}` are filled per call by Travis Core (`assistant_variables()` in `server/travis/main.py`).
