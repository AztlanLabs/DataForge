# SDLC Sequential Workflow

Run SDLC agents one at a time. The user controls the pace. Each agent picks up where the previous one left off using the `.sdlc/` shared state.

## Prerequisites

Initialize the `.sdlc/` workspace first. Either:

- Run the **SDLC Orchestrator** agent and ask it to initialize the workspace.
- Ask **any** SDLC agent: "Initialize the SDLC workspace."

## Recommended Execution Order

Run agents in this order. Skip any role that isn't needed for your project.

### Phase 1: Planning

| Step | Agent | What It Does | Produces |
|---|---|---|---|
| 1 | **sdlc-product-manager** | Refines requirements, creates user stories | `projectbrief.md`, `tasks/*.md` |
| 2 | **sdlc-software-architect** | Defines architecture, creates ADRs | `architecture.md`, `systemPatterns.md`, `decisions/*.md` |
| 3 | **sdlc-ux-ui-designer** | Creates user flows and design specs | `docs/ux/*.md`, handoffs to frontend |
| 4 | **sdlc-db-architect** | Designs data model and schema | `contracts/db-schema.md`, `decisions/*.md` |
| 5 | **sdlc-cybersecurity-architect** | Defines security requirements | `contracts/security-requirements.md` |

### Phase 2: Implementation

| Step | Agent | What It Does | Produces |
|---|---|---|---|
| 6 | **sdlc-backend-engineer** | Implements APIs and services | `contracts/api-contracts.md`, backend code |
| 7 | **sdlc-frontend-engineer** | Implements UI components | Frontend code, component docs |
| 8 | **sdlc-fullstack-engineer** | Implements cross-cutting features | Full-stack code |
| 9 | **sdlc-db-developer** | Implements migrations and queries | SQL migrations, stored procedures |
| 10 | **sdlc-developer** | Implements remaining features | Application code |

### Phase 3: Quality & Security

| Step | Agent | What It Does | Produces |
|---|---|---|---|
| 11 | **sdlc-cybersecurity-developer** | Implements security controls, reviews code | Security patches, test suites |
| 12 | **sdlc-qa-tester** | Writes tests, validates quality gates | `contracts/test-strategy.md`, test suites |
| 13 | **sdlc-responsible-ai** | Reviews for bias, accessibility, ethics | Review reports, ethical ADRs |

### Phase 4: Delivery

| Step | Agent | What It Does | Produces |
|---|---|---|---|
| 14 | **sdlc-devops-engineer** | Configures CI/CD, IaC, monitoring | Pipeline configs, Dockerfiles, IaC modules |
| 15 | **sdlc-technical-writer** | Writes documentation | README, API docs, guides |
| 16 | **sdlc-scrum-master** | Facilitates retrospective, plans next sprint | Sprint reports, improvement actions |

## How to Use

1. Start at Step 1 (or whichever step makes sense for your project).
2. Run the agent for that step.
3. The agent reads `.sdlc/` state, does its work, and writes results back. For implementer roles (Steps 6–12, 14), this means: real code/tests/IaC written to the project's source tree, an actual build/test/validation run, and only then a pointer + result recorded in `.sdlc/progress.md`/`memory.md` — see each agent's "Definition of Done" section.
4. Move to the next step only once that Definition of Done is satisfied (or explicitly documented as blocked).
5. Repeat until all needed steps are complete.

## Customization

- **Skip roles**: If you don't need a DB Architect, skip Step 4.
- **Reorder**: If backend needs to come before UX, swap Steps 3 and 6.
- **Repeat**: Run any agent again if requirements change.
- **Add agents**: Insert additional agents at any point.
