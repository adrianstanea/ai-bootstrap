# Requirement diagram (`requirementDiagram`)

Contents: Skeleton · Elements · Relationships · Pitfalls · Checklist

Use requirement diagrams for traceability: requirements, the elements that satisfy them, and the tests that verify them. They follow SysML requirement semantics.

## Skeleton

```mermaid
requirementDiagram
    accTitle: Latency requirement traceability
    accDescr: The pipeline satisfies the latency requirement, verified by a latency test.

    requirement latency_req {
        id: REQ-12
        text: "Sample-to-publish latency under 2 ms"
        risk: high
        verifymethod: test
    }
    functionalRequirement config_req {
        id: REQ-13
        text: "Configuration loaded from YAML descriptor"
        risk: low
        verifymethod: inspection
    }
    element pipeline {
        type: "software component"
        docref: "docs/pipeline.md"
    }
    element latency_test {
        type: "test"
    }

    pipeline - satisfies -> latency_req
    latency_test - verifies -> latency_req
    config_req - derives -> latency_req
```

## Elements

- Requirement types: `requirement`, `functionalRequirement`, `interfaceRequirement`, `performanceRequirement`, `physicalRequirement`, `designConstraint`.
- Fields: `id`, `text`, `risk: low|medium|high`, `verifymethod: analysis|inspection|test|demonstration`.
- `element name { type: "…", docref: "…" }` for implementations, tests, and documents.

## Relationships

`source - type -> destination`, where type is one of `contains`, `copies`, `derives`, `satisfies`, `verifies`, `refines`, `traces`.

## Pitfalls

- Quote `text` and `type` values that contain spaces or punctuation.
- IDs in the `id:` field are free text, but element names must be identifier-like (no spaces).
- More than about 10 requirements gets unreadable. Use a traceability table and keep the diagram for a focused subset.

## Checklist

- [ ] Correct requirement subtype and verify method
- [ ] Each requirement has a `satisfies` and a `verifies` link (or a stated gap)
- [ ] Quoted text values; identifier-like names
