# Application Domain

The `app` package contains the Contract Lifecycle Management core. It is organized using domain-driven design and does not depend on the web UI, extraction agents, or MCP transport.

## Contents

- `contract_lifecycle/domain/`: aggregates, entities, value objects, domain services, events, repositories, and invariants.
- `contract_lifecycle/application/`: commands and application services coordinating transactions and authorization.
- `contract_lifecycle/infrastructure/sqlite/`: SQLite repositories, document blob storage, event persistence, and mappers.
- `contract_lifecycle/tests/`: domain/application smoke tests.

The domain model is documented in [contract-lifecycle-ddd.md](contract-lifecycle-ddd.md).
