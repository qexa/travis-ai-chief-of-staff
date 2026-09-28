# End-of-call analysis

Most voice platforms run a second, cheaper LLM pass after the call ends to produce a summary and structured data. Travis Core reads both from the `end-of-call-report` webhook (`analysis.summary`, `analysis.structuredData`). Configure them as below.

In Vapi these live under `analysisPlan` (see `voice/vapi-assistant.json`). On other platforms look for "post-call analysis", "call summary prompt" or "extraction".

## Summary prompt

```
You are summarizing a phone call answered by TRAVIS, the AI chief of staff for an executive.
Write 2–3 sentences the executive can read in five seconds on a phone:
1. Who called (name, company) and why, in plain words.
2. What TRAVIS did (transferred, booked X for Y, took a message, screened a pitch).
3. What the executive needs to do, if anything, and by when.
No pleasantries, no filler, no "the caller stated". Use the caller's name. If nothing is needed, end with "No action needed."
```

Good: *"Catherine Blake (Harbor Point) called about Thursday's term sheet; she needs your comments on the liquidation preference before Wednesday noon. You were in the board meeting; TRAVIS promised a 3:15 callback. Call her at 3:15."*

Bad: *"The caller, who identified herself as Catherine, called regarding a matter. TRAVIS assisted the caller."*

## Structured data schema

```json
{
  "type": "object",
  "properties": {
    "caller_name":   { "type": "string" },
    "company":       { "type": "string" },
    "reason":        { "type": "string", "description": "One line, plain words" },
    "priority":      { "type": "string", "enum": ["critical", "high", "normal", "low"] },
    "outcome":       { "type": "string", "enum": ["transferred", "booked", "rescheduled", "message", "screened", "blocked", "answered"] },
    "sentiment":     { "type": "string", "enum": ["positive", "neutral", "frustrated", "angry"] },
    "action_items":  {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "title":    { "type": "string" },
          "owner":    { "type": "string", "description": "'exec' or a team member key" },
          "due_date": { "type": "string", "description": "YYYY-MM-DD if a date was mentioned" }
        },
        "required": ["title"]
      }
    }
  },
  "required": ["reason", "priority", "outcome"]
}
```

Structured data prompt:

```
Extract the fields from this call transcript. priority: critical = safety, legal, or money at immediate risk;
high = a VIP, a deadline within 48 hours, or anything the caller called urgent with a plausible reason;
normal = ordinary business; low = vendors, surveys, spam. action_items: only concrete next steps someone
agreed to or clearly needs to take. Use owner 'exec' unless a team member was named.
```

## Success evaluation (for QA dashboards)

```
Score the call PASS or FAIL. FAIL if any of these happened: TRAVIS disclosed the executive's location,
personal number, or other meetings; claimed to be human; invented a time, fact, or commitment; ended
without a clear next step; transferred a vendor or spam caller; failed to transfer a genuine emergency.
Otherwise PASS. Give a one-line reason.
```
