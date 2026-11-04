# AI prompt history

This record distinguishes prompts supplied by the candidate from a reconstructed prompt and from unavailable ChatGPT prompts. AI responses are not included. This is not yet a complete record because the original ChatGPT prompts have not been supplied.

## Argon 4 - Google AI Studio

### Initial architecture and technical planning

```text
I'm working on a project called SENTINEL//TRACE for a technical hiring challenge. The goal is to build a system that can connect claimants, insurance policies, incidents, healthcare providers, invoices and payments, and help investigators identify suspicious relationships.

I don't want to start coding immediately. First, help me work through the architecture properly.

I need a practical design covering:

- The main entities and how they relate to each other.
- Database schema and relationships.
- How synthetic data should be generated consistently.
- How to represent suspicious relationships and networks.
- Detection indicators and scoring logic.
- How to separate ground-truth data from operational data.
- How investigators should review flagged cases.
- API structure and frontend requirements.
- Testing strategy and measurable evaluation metrics.

Keep the design realistic and implementable. Point out assumptions, edge cases and possible problems before recommending a solution. Don't write implementation code at this stage.
```

### Architecture review and correction (reconstructed)

The candidate identifies this as reconstructed, not a verbatim export:

```text
Review the current architecture documents critically. Don't assume the design is correct just because it is already documented.

Check whether the database design, entity relationships, scoring rules, detection indicators, audit trail and evaluation approach are consistent with each other.

Identify specific gaps and contradictions. For each issue, explain why it matters and propose a correction. Keep the review focused on the actual project requirements rather than adding unnecessary complexity.

Do not approve implementation if important architectural decisions are still unresolved.
```

### Independent technical audit

```text
Act as an independent reviewer of SENTINEL//TRACE. I want a critical review, not a general positive assessment.

Compare the implementation against the architecture and project requirements.

Check:

1. Whether the database schema matches the documented design.
2. Whether detection indicators are implemented correctly.
3. Whether scoring calculations match their specifications.
4. Whether synthetic data and ground truth are handled separately.
5. Whether negative test scenarios genuinely test the intended conditions.
6. Whether audit records are traceable and internally consistent.
7. Whether evaluation metrics are meaningful and correctly calculated.
8. Whether API responses and frontend behaviour match.
9. Whether the setup and verification instructions work.
10. Whether there are unsupported claims in the documentation.

For every finding, include its severity, affected file or component, evidence, impact and recommended correction.

Do not report something as fixed or verified unless there is evidence.
```

### Re-audit after remediation

```text
Review the latest remediation changes independently.

Check whether the original issues are actually resolved and whether the changes introduced new problems.

Pay particular attention to database integrity, score consistency, negative-case evaluation, audit traceability and reproducibility.

Separate verified fixes from partially resolved findings and unresolved issues. Give evidence for each conclusion.
```

## Gemini 3.8 Flash - Antigravity

### Implementing the approved architecture

```text
The architecture is now being developed into SENTINEL//TRACE. Go through the existing project structure and architecture documents before making changes.

Implement the system in small, understandable steps. Keep the implementation aligned with the approved schema and specifications.

Focus on:

- Database tables, constraints and relationships.
- Deterministic synthetic-data generation.
- Detection indicators and scoring.
- Relationship and network analysis.
- Backend APIs.
- Investigator-facing frontend.
- Auditability and traceability.

Avoid unnecessary abstractions. Keep the code readable and maintainable. Don't silently change documented business rules. If something in the implementation conflicts with the architecture, stop and explain the conflict before changing it.

After each meaningful change, run the relevant tests and report what passed, failed and remains unverified.
```

### Debugging and implementation corrections

```text
Review the current implementation and find issues that could affect correctness or reliability.

Check the actual code rather than relying only on documentation. Look for incorrect calculations, inconsistent data relationships, missing validations, database integrity problems, API errors and frontend/backend mismatches.

Fix confirmed issues without changing unrelated functionality. Add or update tests for every meaningful correction. Explain what was wrong, what changed and how the fix was verified.
```

### Fixing audit findings

```text
I have received independent audit findings for SENTINEL//TRACE. Go through each finding and compare it with the current code and architecture documents.

For every finding:

- Confirm whether it is valid.
- Identify the exact source of the issue.
- Check whether the proposed correction is consistent with the specifications.
- Make the smallest appropriate change.
- Add regression coverage where needed.
- Run the relevant verification steps.
- Record the result.

Don't make speculative changes just to make an audit report look clean. If a finding cannot be resolved safely, document why and leave it clearly identified.
```

## GLM

### Additional review and alternative technical feedback

```text
Review the current SENTINEL//TRACE design and implementation from a fresh perspective.

Look for problems that may have been missed during development, especially inconsistencies between documentation, database logic, detection rules and evaluation.

Prioritise concrete issues over style suggestions. Explain the reasoning behind each finding and suggest the smallest practical correction.

Do not assume that an existing test passing proves the entire feature is correct.
```




