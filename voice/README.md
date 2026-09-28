# Voice configuration (generated)

Do not edit these files by hand. Edit `scripts/build_voice_config.py` and `prompts/*.md`, then run:

```bash
python scripts/build_voice_config.py
python scripts/deploy_vapi.py --voice-id <id> --dry-run
```

- `vapi-assistant.json`: the assistant (model, voice, transcriber, timing, analysis plan). `{{PUBLIC_BASE_URL}}` is replaced at deploy time.
- `tools/*.json`: 12 function tools + `transfer_call` (server-resolved destination) + `end_call`.

Other platforms: see `docs/13-platform-notes.md`. The JSON-schema `parameters` blocks copy directly into Retell, Bland and ElevenLabs tool definitions.
