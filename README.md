# Nova 4.2.1 — Conversation Polish

This release fixes the edge cases found during live testing.

## Improvements

- `memory` now works as a built-in command
- `memory identity` and `memory preferences` filter the inspector
- Incomplete thoughts receive clarifying prompts
- Color values are normalized
- “the color purple as well” becomes `Purple`
- Response capitalization and punctuation are corrected
- Existing Nova 4.1 and 4.2 memories remain compatible

## Start

```bash
chmod +x start_nova.command
./start_nova.command
```

## Recommended test

```text
My name
Actually call me Rick
What is it?
My favorite color is Amber but I do like the color purple as well
What color do I like?
memory
memory preferences
history
```

Expected color response:

```text
Nova: Your favorite color is Amber. You also like Purple.
```
