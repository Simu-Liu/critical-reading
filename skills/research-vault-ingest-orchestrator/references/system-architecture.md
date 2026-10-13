# ResearchVault production architecture

```text
Zotero parent item (zotero_key)
  + PDF attachment (pdf_key)
        |
        v
fulltext/<collection>/<zotero_key>.md
  - original-language MinerU archive
  - image assets and reciprocal note link
        |
        v
vault/<collection>/<paper>.md
  - Chinese structured single-paper Analytical Note
  - Zotero identity and fulltext_path
        |------------------------> Notes/<paper> — 我的思考.md
        |                           - user-authored free-form thoughts
        |                           - AI/Fulltext/Zotero navigation
        |
        v
knowledge/
  - Chinese human-facing derived synthesis
knowledge/.meta/
  - claims, gaps, indexes and machine traceability
```

`knowledge` is a navigation and synthesis layer, not primary scientific evidence. Evidence must remain traceable as Knowledge → Analytical Note → Fulltext → optional original PDF.

| Layer | Responsibility | Stable identity |
| --- | --- | --- |
| Zotero | Parent metadata and attached source PDF | `zotero_key`, `pdf_key` |
| `fulltext` | Verbatim source archive and images | `zotero_key`, `pdf_key` |
| `vault` | Structured single-paper interpretation | `zotero_key` |
| `Notes` | User's free-form ideas; not paper evidence | Same parent key and library scope |
| `knowledge` | Cross-paper Chinese synthesis and navigation | source Note links |
| `knowledge/.meta` | Claims, gaps and machine-only traceability | claim/gap IDs plus Note-derived identity |
