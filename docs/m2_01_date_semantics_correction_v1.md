# Source-date addendum v1 — action and alert dates only

This owner-authorized addendum supplements the M2-01 handbook for Defensoría action
and alert dates. Active scientific version: 0.3.1; benchmark version: 0.1.1.
It is a protocol instruction, not annotation-launch or human-gold authority.

- Copy the exact visible date string into `action_date_original` or `alert_date_original`.
- Record separately the source-supported precision in the corresponding
  `*_date_precision_original` slot, using the existing precision convention.
- Preserve spelling, punctuation, language and ordering. Do not normalize or parse.
- Do not invent a missing day, month, or precision. ISO-looking source text is copied
  because it is visible, not because the tool converted it.
- Parsed `action_date`/`alert_date` are later derivatives, never human form slots.
- For unreported, inapplicable or structurally unavailable dates retain the explicit
  state and no raw value. An absent date cannot support a confidently observed precision.
- Preserve source ambiguity and annotation uncertainty for adjudication. Illegible
  evidence needs later source-forensics review. Do not choose a date automatically.
- No numeric zero-date construct is approved. A source dash/blank is not zero.

No additional ontology, critical-field denominator or M3 threshold is changed.
