# Source-discrepancy reconnaissance notes for M2

These are read-only observations from report 269. They are not parser fixes, canonical
values, or benchmark gold. M2 must independently capture page-level evidence and decide
whether each item is a `SOURCE_INCONSISTENCY`, another discrepancy class, or an apparent
reading error.

## Alert totals

The alert narrative states that 58 alerts were recorded, with a 51/2/5 breakdown. The
following `Cuadro N.° 1` reports 34 alerts, with a 28/2/4 breakdown. Preserve both
published values and their exact pages/sections if benchmarked; never reconcile one total
to the other automatically.

## Case timing

In the July 2026 report, case code `1514-0726` contains the text `Ingresó como caso
nuevo: Agosto 2026`. The wording conflicts with the report month and code suffix. Preserve
the source wording and route the temporal conflict to M2 review; do not change August to
July in a parser or identity key.

## Identity metadata reminder

Reports 260–269 carry the stale embedded PDF `/Title` value `RCS N° 126`. It is a
diagnostic source property only and cannot be sole evidence for report number or reference
month. Visible document evidence and/or official landing/download metadata are required;
disagreements remain discrepancies.
