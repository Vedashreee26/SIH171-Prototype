# Privacy module limitations (MVP)

This is a **regex + field-hint** sanitizer, not a production PII engine.
It is designed for a hackathon demo: high precision on *obvious* patterns.

## What it does well

- Emails (`someone@example.com`)
- Many phone numbers (`+1 415-555-2671`, Indian 10-digit mobiles)
- Password fields (by `type` / label / key name), whole value replaced
- Card-like numbers that **pass the Luhn check**
- Grouped Aadhaar-like IDs, PAN-like IDs, SSN-like `###-##-####`
- Names only when the **field looks like a name field** *and* the value looks like `Jane Doe`

## What it will miss (false negatives)

- Names in a paragraph (`Contact Jane Doe`) without a name label
- Nicknames, single given names, ALL-CAPS names, non-Latin scripts
- Phone numbers written as words or unusual formats
- Card numbers that fail Luhn (invalid cards) or are split across elements
- Government IDs that are not PAN / grouped Aadhaar / US SSN-like
- PII inside images / screenshots (this module only sees structured text)
- Secrets that do not look like passwords (session cookies, JWT, API keys) unless the field name hints at `secret` / `password` / `pin`
- Obfuscated values (`u***@x.com`) and homoglyph tricks

## What it may over-redact (false positives)

- Phone regex can still catch some long numeric IDs with dashes
- A Luhn-valid number that is not a card (rare, but possible)
- A string that looks like PAN (`ABCDE1234F`) in non-ID text
- A two-word title-case phrase in a field labeled `Name` (e.g. a product name)

## Privacy guarantees (this module)

- No network calls
- No logging of original values
- No files written with raw PII
- Input is not mutated; a copy is returned

The Flask backend and extension must still **call this locally** and send only the output. This file cannot enforce that other modules obey the pipeline.
