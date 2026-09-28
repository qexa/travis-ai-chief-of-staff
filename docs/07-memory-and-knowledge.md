# 07 · Memory and knowledge

TRAVIS knows three different kinds of things, stored three different ways.

| Kind | Example | Where | Who writes it | Who can read it |
|---|---|---|---|---|
| **Rules and people** | VIPs, team, hours, protected blocks | `config/<exec>.yaml` | You, at onboarding | Core (never the raw file to the model) |
| **Company knowledge** | Services, address, policies | `knowledge/<exec>/*.md` | You, at onboarding | Callers (public sections), exec (all) |
| **Memories** | "Cate's fund closes Oct 30", "Out until Monday" | `memories` table | Exec by text; TRAVIS on calls | See visibility |

## Memories

```
memories(subject, fact, source, visibility, created_at)
```

- `source`: `exec_sms` (the exec told TRAVIS), `call` (learned on a call), `onboarding`
- `visibility`:
  - `private`: only surfaces in the exec's text channel
  - `callers`: may be handed to the model on calls **with that verified caller** (via `lookup_caller.things_to_remember`)

Writing:
- Exec: "remember that I'm out Friday; tell anyone who calls I'll be back Monday" → the LLM engine saves with `visibility=callers`. The rule engine saves `private`.
- Calls: `note_about_caller(fact)` saves `private` by default. Promote to `callers` from the text channel if useful.

Reading:
- On calls, `lookup_caller` returns up to 3 `callers`-visible facts about the verified caller. Claimed/unverified callers get none.
- By text: "what do you know about Cate?" → `recall`.

Retention: add a nightly job to delete `call`-sourced memories older than your retention policy (e.g. 18 months) unless promoted. Document it in your privacy notice.

### Scaling memory

The keyword search in `db.search_memories` is fine for thousands of facts. Past that, add an embedding column and cosine search (pgvector), keep the same `recall` tool contract, and cap results at 5.

## Knowledge base

`knowledge.py` splits every markdown file on `## ` headings and scores sections with a small BM25-style ranking (heading matches count double). No vector DB, no embeddings, no cost; good up to a few hundred sections.

Authoring rules:
- One topic per `##` section. Short, factual, first sentence answers the likely question.
- Write it the way TRAVIS should say it ("Office hours are 8 to 6 Central, Monday to Friday.").
- Put `[CONFIDENTIAL]` or `[INTERNAL]` in a heading to hide the section from callers. It remains searchable by the exec by text.
- Don't put the executive's personal details here at all.

Templates in `knowledge/templates/`. Worked example in `knowledge/example/`.

When a caller asks something the KB doesn't cover, TRAVIS says he'll have the right person follow up and takes a message. Review "unanswered question" messages weekly and add sections; this is how TRAVIS "learns your entire business in minutes" and keeps learning.

### Using a platform knowledge base instead

Vapi, Retell and Votel.ai all offer hosted knowledge bases. They're fine for public company info. Keep confidential material out of them (you can't enforce section-level visibility), and keep `search_knowledge` if you need the exec-only view.

## Contacts (learned automatically)

Every caller who leaves a name and number becomes a `contacts` row with a tier. Next time they call, TRAVIS greets them by name. Promote a contact to VIP by adding them to the profile's `vips:`; demote a pest with `UPDATE contacts SET tier='vendor'` (a dashboard for this is on the roadmap).
