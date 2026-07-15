# The paper trail

Machine-readable records behind [records.html](../../records.html): what Colorado River
water actually trades for when boards vote, and who has formally said what about the
post-2026 rules. Every row carries a `doc_url` to the primary document and a verbatim
`quote` so you can check it yourself.

| File | Rows | What it is |
|---|---:|---|
| `price_observatory.csv` | 26 | Board-approved transactions with an explicit or derivable price per acre-foot (agreements, wholesale rates, incentive programs) |
| `evidence_ledger.csv` | 228 | All substantive Colorado River items harvested from basin water-agency board packets |
| `stance_ledger.csv` | 567 | Dated position statements: USBR post-2026 scoping letters, board-adopted stances, and federal docket comments |
| `usbr_letters.csv` | 412 | Formal position letters posted by the Bureau of Reclamation for post-2026 operations and related processes |

## Sources

Public board agendas and packets (Legistar, Granicus, CivicClerk, PrimeGov, and agency
own-sites), regulations.gov (API v4), and usbr.gov scoping/comment pages. Extraction is
AI-assisted (LLM fusion over fetched documents), then spot-checked. Each row includes a
`confidence` field where applicable. Treat rows as pointers to the primary document, not
as the document itself.

## Sanitization

Email addresses, phone numbers, and mailing addresses that appeared inside OCR'd
letterheads were removed. Letters submitted by private individuals (personal name, no
organization) are excluded. Organizations, tribes, agencies, and public officials acting
in office are public record and are retained.

## Refresh cadence

Rebuilt from the harvest pipeline roughly monthly while the post-2026 process is live.
Row counts and coverage per agency are in the site's records page. Some agencies are
dark (bot walls or no published packets); the records page says which.

## Independence

This is independent, open work by Steps Ventures. It is not affiliated with any water
agency, investor, or advocacy group. Corrections: mike@stepsventures.com.
