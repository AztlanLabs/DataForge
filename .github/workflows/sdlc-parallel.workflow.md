# SDLC Parallel Workflow

Run SDLC agents concurrently when tasks have no dependencies. This workflow identifies which agents can run simultaneously and which must wait.

## Prerequisites

Initialize the `.sdlc/` workspace first. The `.sdlc/` shared state handles concurrent reads. Write conflicts are prevented by file ownership rules defined in the shared memory skill.

## Parallel Execution Phases

### Phase 1: Planning (agents can run together)

```
┌─────────────────────────┐
│  sdlc-product-manager   │  → projectbrief.md, tasks
│  sdlc-software-architect│  → architecture.md, ADRs
│  sdlc-ux-ui-designer    │  → docs/ux/*.md
│  sdlc-db-architect      │  → contracts/db-schema.md
│  sdlc-cybersecurity-arch│  → contracts/security-requirements.md
└─────────────────────────┘
         │ GATE: architecture.md + all contracts defined
         ▼
```

**Why these can run together**: Each writes to different files. No write conflicts.

### Phase 2: Implementation (agents can run together)

```
┌─────────────────────────┐
│  sdlc-backend-engineer  │  → backend code, api-contracts.md
│  sdlc-frontend-engineer │  → frontend code
│  sdlc-fullstack-engineer│  → cross-cutting code
│  sdlc-db-developer      │  → migrations, stored procedures
│  sdlc-developer         │  → feature code
└─────────────────────────┘
         │ GATE: every implementation task's build + tests actually run and passing
         │       (per-agent Definition of Done), evidenced in progress.md —
         │       not merely marked COMPLETED
         ▼
```

**Dependency note**: Frontend ideally reads API contracts from Backend. If running truly in parallel, Frontend should use the contract specification from Phase 1 architecture, not wait for Backend implementation.

### Phase 3: Quality & Security (agents can run together)

```
┌─────────────────────────┐
│  sdlc-cybersecurity-dev │  → security patches, tests
│  sdlc-qa-tester         │  → test suites, quality reports
│  sdlc-responsible-ai    │  → review reports, ethical ADRs
└─────────────────────────┘
         │ GATE: quality gates passed with real, last-run pass/fail/coverage
         │       numbers in test-strategy.md/progress.md — not aspirational targets
         ▼
```

### Phase 4: Delivery (agents can run together)

```
┌─────────────────────────┐
│  sdlc-devops-engineer   │  → pipelines, IaC, monitoring
│  sdlc-technical-writer  │  → documentation
│  sdlc-scrum-master      │  → sprint report, retro
└─────────────────────────┘
```

## Concurrency Safety Rules

1. **File ownership**: Each agent writes only to its designated files (see shared memory skill).
2. **Append-only files**: `activeContext.md`, `progress.md`, and `memory.md` are safe for concurrent appends.
3. **Handoffs**: Agents create handoff files; consuming agents read them on next run.
4. **Conflict resolution**: If two agents need to modify the same file, run them sequentially instead.

## When to Use Parallel vs Sequential

| Scenario | Recommendation |
|---|---|
| Small project, one developer | Sequential — simpler |
| Large project, many features | Parallel Phase 1, then sequential implementation |
| Time-critical delivery | Maximum parallel execution |
| Learning/exploring | Sequential — easier to follow state changes |
