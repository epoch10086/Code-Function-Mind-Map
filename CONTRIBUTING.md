# Development contracts

- Use parsed syntax and scope/import/package evidence for resolved calls. Never use a global unique-name match to invent a call. Diagnostics preserve unresolved expressions and source locations.
- Call edges and callback registrations are separate. Source is read-only; never import/execute target Python or run target build/install scripts.
- Skill dependencies are pinned and isolated. Generate/update must not access the network.
- Keep graph extraction independent of visible filtering. Canonical nodes+edges contain all extracted functions/calls; renderers select a subset documented in navigation.
- Write generated files only to the dedicated output, validate before replacement, preserve unowned files, archive previous managed files, and rollback on replacement failure.
- Actual native-client verification is independent of ZIP/JSON/geometry checks. Do not claim XMind rendering passed when it was not opened.
- Add tests for externally observable resolution, output consistency or update recovery. Keep fixtures small and never commit runtime environments or user generated graphs.
