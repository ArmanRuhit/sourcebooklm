**1. Product definition (the "what and why")**
- **PRD (Product Requirements Document)**: problem statement, target users, goals and non-goals, user stories, functional and non-functional requirements, success metrics, and open questions.
- **BRD (Business Requirements Document)**: only if business stakeholders are involved; covers business goals, ROI, constraints, and compliance needs.
- **User stories / use cases**: "As a X, I want Y so that Z", each with acceptance criteria.

**2. Technical definition (the "how")**
- **SRS (Software Requirements Specification)**: formal, detailed functional and non-functional requirements. Use it when you need precision (e.g. latency, throughput, availability targets).
- **Technical design document (TDD) / RFC**: proposed solution, alternatives considered, trade-offs, risks, and rollout plan.
- **Architecture document (HLD, high-level design)**: components, boundaries, communication patterns, deployment view, and diagrams (context, container, sequence).
- **Low-level design (LLD)**: class/module design, key algorithms, state machines, error handling.

**3. Interface and data specs**
- **API specification**: OpenAPI/Swagger, gRPC proto files, or event/message schemas.
- **Data model / database design**: ERD, DDL, indexing and retention strategy.
- **Integration spec**: for external systems, covering protocol details, message flows, and failure and retry behavior.

**4. Quality and operations**
- **Test plan / strategy**: scope, test levels, test data, and acceptance criteria.
- **NFR document**: performance, security, scalability, and reliability targets.
- **Security / threat model**: if the system handles sensitive data or money.
- **Deployment and runbook**: environments, CI/CD, monitoring, and rollback.

**5. Planning**
- **Project plan / roadmap**: milestones, dependencies, and timeline.
- **Task breakdown**: epics, tickets, and implementation order. This is especially useful for AI, since small scoped tasks work better than one huge request.

**Minimum viable set**

For most projects, you don't need all of this. These four cover most of the value:

1. **PRD**: what and why
2. **Technical design doc**: architecture, data model, API contracts, key decisions
3. **Task breakdown**: ordered, scoped work items with acceptance criteria
4. **CLAUDE.md**: conventions and commands, as the AI's entry point

**Tips**
- Keep each doc as short as possible; AI performs best with precise, unambiguous requirements rather than long prose.
- State non-goals explicitly. They prevent scope creep from AI-generated extras.
- Record decisions and their reasons so the AI doesn't reverse them.
- Link docs to each other (PRD → design → tasks) so nothing contradicts.

