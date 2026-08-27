# Data dictionary overview

- `report`: report/source-version identity, number, provisional reference period, publication metadata, original/canonical filename, byte size, SHA-256, pages, native-text/source/regime status, supersession.
- `report_month`: source aggregate metric/value/unit and provenance.
- `case`, `case_name`, `case_month`: identity, every observed original name, original/normalized stock and phase, separate transitions, monthly facts, provenance.
- `location`, `case_location`: source location text, multiplicity, normalized geography, UBIGEO/crosswalk/match metadata.
- `actor`, `case_actor`: original and normalized actor/type/role plus association provenance.
- `demand`, `case_demand`: original demand/theme/competent entity, normalized derivatives, and association provenance.
- `protest_event`, `case_protest_link`: events remain distinct from cases and link only through explicit evidence.
- `violence_event`: event description/date and independently nullable casualty totals/components.
- `dialogue_event`, `agreement`, `dp_action`, `alert`: source-preserving process/event records.
- `case_relationship`: source and normalized relationship descriptions, effective period, confidence, provenance.
- `provenance`: object/field, report/hash/page/section/table/bbox/span/text, method/extractor/parser/schema/model/prompt/confidence/review.
- `discrepancy`: conflicting values/evidence/classification/status without overwriting sources.
- `manual_review`, `adjudication`: queued ambiguity and append-only, versioned reviewer decisions.
