# Homing developer docs

Start with [PLAN.md](PLAN.md) for what we're building and why. These docs cover how it's built.

| # | Doc | Read it when you're… |
|---|---|---|
| — | [PLAN.md](PLAN.md) | deciding *what* to build, or checking whether something is in scope |
| 01 | [Architecture](01-architecture.md) | getting the big picture: services, flows, vocabulary |
| 02 | [Data model](02-data-model.md) | touching the database or adding a field |
| 03 | [Agents](03-agents.md) | working on any of the four questions, or on Ask and Audit |
| 04 | [Ingestion](04-ingestion.md) | reading a new kind of save, or the WhatsApp import |
| 05 | [Verification](05-verification.md) | working on quotes, dates, eligibility, or labels |
| 06 | [Models](06-models.md) | calling Meta's models, writing prompts, controlling cost |
| 07 | [API](07-api.md) | adding or changing an endpoint |
| 08 | [Frontend](08-frontend.md) | building screens and components |
| 09 | [Security and privacy](09-security-privacy.md) | handling user data, secrets, uploads, or auth |
| 10 | [Deployment and operations](10-deployment-ops.md) | deploying, configuring, or fixing production |
| 11 | [Testing and evals](11-testing-evals.md) | writing tests, or measuring accuracy |
| 12 | [Dev workflow](12-dev-workflow.md) | setting up locally, following conventions, or committing |
| 13 | [Brand](13-brand.md) | choosing colours, type, the logo, or wording |
| 14 | [Build slices](14-build-slices.md) | deciding what to build next, and checking whether a piece is done |
| — | [Decisions (ADRs)](adr/) | asking "why did we do it this way?" |

## Rules for these docs

- **The code follows the docs.** If you change behaviour, update the doc in the same commit.
- **One name per thing.** Use the vocabulary in [01-architecture.md](01-architecture.md#vocabulary), in code and in the UI.
- **Decisions get an ADR.** Anything we'd argue about twice goes in `adr/`.
- **Mark guesses.** Anything not yet confirmed is marked **(confirm)**. Remove the mark once it's checked.
