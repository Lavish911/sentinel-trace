# AI assistance and transparency disclosure

SENTINEL//TRACE was developed with AI assistance. The purpose of this document is to make that assistance clear, not to present it as a substitute for the candidate's understanding or verification.

## Prompt record

The available prompts are recorded verbatim in [`docs/AI_PROMPT_HISTORY.md`](docs/AI_PROMPT_HISTORY.md). That file includes prompts supplied for:

- Argon 4 in Google AI Studio - architecture planning, independent audit, and remediation re-audit;
- Gemini 3.8 Flash in Antigravity - implementation, debugging, and remediation work; and
- GLM - an additional independent review.

One Argon architecture-review prompt is labelled **reconstructed** because it was not supplied as an original export. It is not presented as verbatim text.

## How AI was used

The recorded prompts asked for architecture planning, critical review, implementation support, debugging, audit remediation, and documentation review. AI assistance was used during development; it is not evidence that the running application uses any AI provider or external model API.

## What is still missing

ChatGPT was also used for architecture and implementation discussions, repository and documentation review, debugging guidance, and preparation of audit/remediation prompts. The original ChatGPT prompts have not been recovered, so they are not recreated in this repository.

Before submission, the candidate should:

- add any recoverable original ChatGPT prompts;
- confirm whether any tool other than Argon 4, Gemini 3.8 Flash/Antigravity, GLM, and ChatGPT was used; and
- review the repository's setup, limitations, and verification notes so they can explain the project directly.

## Verification boundary

The repository documents source code, expected checks, and historical artifacts. A test result should only be described as current when it has been rerun for the commit being submitted. The exact commands and evidence expectations are in [`docs/VERIFICATION.md`](docs/VERIFICATION.md).
