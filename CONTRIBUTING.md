# Contributing

Thanks for helping make TRAVIS better for everyone building their own AI chief of staff.

- Keep all example data fictional (Jordan Hale / Northline Logistics). Never commit a real executive's profile, contacts, transcripts or keys.
- Every behavior change needs a unit test in `server/tests/` and, for call behavior, a scenario in `scripts/simulate_call.py`.
- Tool changes go in `scripts/build_voice_config.py` (the single source of truth); re-run it and commit the generated `voice/` files. CI fails if they drift.
- Prompt changes: explain the failure you saw (a transcript excerpt with details anonymized) and re-run `evals/red-team.md`.
- Before opening a PR:

```bash
pytest server/tests -q
python scripts/build_voice_config.py
python scripts/simulate_call.py all
```

See `docs/14-roadmap.md` for good first issues.
