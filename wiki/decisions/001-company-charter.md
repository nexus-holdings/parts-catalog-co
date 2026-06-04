# ADR 001 — Company Charter

**Date:** 2026-06-04
**Status:** Accepted
**Approved by:** Board meeting `board-20260604-181658`

## Company

- **Name:** Parts Catalog Co
- **Slug:** `parts-catalog-co`
- **Mission:** Domain company owning the parts-catalog lookup service consumed by Gizmo Test Co.

## Team Structure

| Role | Type | Responsibilities |
|------|------|-----------------|
| Company Lead | Persistent | Mission ownership, stakeholder communication, wiki maintenance |
| Tech Lead | Persistent | Architecture decisions, code review, ticket decomposition |
| Execution Team | Dynamic (catalog) | Per-ticket, stateless; provisioned from agent catalog |

## Escalation Path

Execution agent → Tech Lead → Company Lead → COO → Board meeting

## Cross-Company Dependencies

Managed via the shared-modules catalog. No direct inter-company code coupling.
## Decision

Approved. Company provisioned and operational.
