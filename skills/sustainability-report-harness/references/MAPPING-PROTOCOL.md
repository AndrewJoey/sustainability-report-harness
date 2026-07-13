# Mapping Protocol

Use this protocol for standards, requirements, unified disclosures, and ledger relationships.

## Governance

- Record official source, version, effective dates, content hash, and review status.
- Mark AI-produced decomposition or mapping as draft until a qualified reviewer approves it.
- Keep project custom requirements distinct from official rules.
- Never auto-upgrade a project's locked version.

## Mapping integrity

- Decompose clauses into independently testable requirements.
- Preserve original clause text and stable requirement IDs.
- Represent identical, similar, containing, and unique relationships without discarding differences.
- Ensure every selected requirement appears in the union or an explicit reviewed exception.

## Standard package contract

- Keep an independent `clauses` inventory and link every `Requirement` back to exactly matching
  `clause_id` and `original_text`.
- Require every source clause to produce at least one independently testable Requirement.
- Hash the canonical clauses and requirements together. Reject altered or incomplete payloads.
- Require named rule review metadata for packages marked `reviewed` or `published`.
- Use `simulated` only for structural fixtures and retain the explicit non-official warning.

## Agent mapping plan

- Build unified disclosures only from the locked requirements.
- Give every requirement exactly one union destination; never omit or duplicate a requirement.
- Record one mapping row per requirement with `equivalent`, `overlapping`, `broader_than`,
  `narrower_than`, or `unique` and a non-empty difference note.
- Mark Agent-created mappings and evidence links `unreviewed`.
- Link only `client_evidence` to disclosure requirements. Keep peer references outside customer
  evidence coverage.
- Use `direct`, `supporting`, or `contradicting` for evidence relationships. Explain every
  contradicting relationship.
- Create an explicit gap for every requirement without direct or supporting customer evidence.

## Human-in-the-loop gate

- Stop in `awaiting_evidence_confirmation` after building the union.
- Ask the user to accept, reject, or edit mappings and evidence relationships.
- When the user requests regrouping, rebuild with `--replace`; preserve unchanged accepted or
  human-edited items and return changed items to `unreviewed`.
- Ask the user to classify every uncovered requirement as critical or noncritical and record notes.
- Do not enter outline generation while any mapping, evidence relationship, contradiction, or gap
  is unreviewed or rejected.
- Persist the reviewer, decision, notes, and Checkpoint approval so another Agent can continue.

## Current boundary

Only simulated fixtures are bundled. They test structure, source-clause completeness, mapping
types, evidence reuse, and review gates; they are not regulatory interpretations. Real use still
requires qualified reviewers and verified official source packages.
