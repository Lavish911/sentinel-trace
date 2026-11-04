# AI assistance and transparency disclosure

SENTINEL//TRACE was developed with AI assistance. The purpose of this document is to provide a transparent, accountable record of how AI tools were utilized, how the implementation was verified, and how the candidate maintained complete technical ownership of the solution.

## Prompt record

The prompts submitted during the project's development are recorded in [`docs/AI_PROMPT_HISTORY.md`](docs/AI_PROMPT_HISTORY.md). That file includes the prompts supplied for:

- **Argon 4 in Google AI Studio** — architecture planning, adversarial threat modeling, and independent audit review;
- **Gemini 3.8 Flash in Antigravity** — incremental implementation, test suite development, and debugging; and
- **GLM** — secondary independent architectural review.

One Argon architecture-review prompt is labelled **reconstructed** because it was summarized from session notes rather than exported verbatim.

## Tool scope and attribution

Four AI tools were used during the design and development of this project:

- **Argon 4 (Google AI Studio)** — architecture planning, adversarial threat modeling, and independent audit review; recorded in the prompt history;
- **Gemini 3.8 Flash (Antigravity)** — incremental implementation, test suite development, and debugging; recorded in the prompt history;
- **GLM** — secondary independent architectural review; recorded in the prompt history; and
- **ChatGPT** — used for architecture and implementation discussions. The original ChatGPT prompts could not be recovered from the session history, so they are not reproduced in `docs/AI_PROMPT_HISTORY.md`. This is a disclosed limitation of the prompt record, not an omission of tool use.

One Argon architecture-review prompt is labelled **reconstructed** because it was summarized from session notes rather than exported verbatim.

AI assistance was utilized during development for planning, code generation, and test creation; the running application does not invoke any external AI provider or model API at runtime. All scoring, indicator derivation, and fraud detection logic runs entirely locally on deterministic Python algorithms and SQLite triggers.

## Candidate ownership and validation

The candidate (`Lavish911`) maintained continuous editorial and technical authority over the entire repository:

- Every database table, STRICT constraint, and SQLite trigger was verified against `ARCH-ST-010.3`.
- All 15 fraud indicator formulas, scoring weights, and 6 benign context dampening rules were verified against the operational specification.
- Test suites (66 backend pytest tests, 20 database acceptance checks, 8 transaction atomicity tests, and 8 P0 hardening tests) were run and validated locally by the candidate.
- The candidate understands the design, code, and limitations, and is prepared to explain and defend every component.

## Verification boundary

The repository documents source code, expected checks, and historical artifacts. A test result is only valid for the specific commit evaluated. Full instructions and verification commands are documented in [`docs/VERIFICATION.md`](docs/VERIFICATION.md).
