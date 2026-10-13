# Production ingest pipeline

## Entry condition

Accept a paper only when the user identifies it by Zotero item, `zotero_key`, a Zotero URI, collection plus an unambiguous item, or another resolvable explicit reference. This workflow does not discover papers.

## Stages

1. **State inspection** — inspect existing Note, Fulltext, Knowledge source coverage, sidecars, prior log entries, and Note conformance to the active Vault template or bundled fallback without writing.
2. **Identity resolution** — use `zotero-data-fetcher` to resolve parent `zotero_key`, PDF `pdf_key`, and a currently usable attachment reference or path. A conflict becomes `MANUAL_REVIEW_REQUIRED`.
3. **Fulltext gate** — reuse a valid formal Fulltext first; otherwise use `zotero-fulltext-archiver` with a converter actually available in the current environment.
4. **Analytical Note gate** — reuse a valid formal Note only if its identity, source links, and structure conform to the canonical template; otherwise use `zotero-analytical-writer` in create or same-path template-repair mode after sufficient source material is available.
5. **Personal association** — reuse or create the same-paper free-form page in `Notes/`, with corresponding AI properties and Zotero/AI/Fulltext navigation. Preserve existing personal prose and independent property values using the package linking helper.
6. **Links and indexes** — require reciprocal paths and matching parent/PDF identities in the correct library scope; validate image links and refresh the four literature indexes. Index only formal AI Notes, never personal pages or Fulltext copies.
7. **Knowledge decision** — call `research-vault-knowledge-maintainer` only with the completed AI Note and evidence state. It decides whether existing Knowledge is strengthened, conditioned, bounded, challenged, newly supported, or unchanged. Personal ideas remain separate from scientific source coverage.
8. **Final validation and log** — validate Note-template conformance, quotation/page evidence, three-layer reciprocal links, and images; run the package Knowledge validator and report content checks, then append the human-readable log event only if the applicable contract passes. Record a deferred technical status when PDF/image access remains unavailable.

## Delegation map

| Stage | Owner | Must not be duplicated here |
| --- | --- | --- |
| Zotero identity/PDF lookup | `zotero-data-fetcher` | Zotero database queries and attachment discovery |
| PDF to formal Fulltext | `zotero-fulltext-archiver` | Converter installation, machine-specific runners and image migration code |
| Structured paper understanding | `zotero-analytical-writer` | Note template and writing logic |
| Cross-paper synthesis | `research-vault-knowledge-maintainer` | Frozen schema, templates, claims and gaps |
| Later user questions | `research-vault-literature-retrieval` | Ingest execution |
