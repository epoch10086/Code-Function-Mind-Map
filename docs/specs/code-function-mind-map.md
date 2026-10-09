# Approved implementation specification

Baseline: 15db67b4554234511abf7228e0c4de9963062eb2. Work on Epoch. Install skill locally; local commit only.

1. Self-contained skill `code-function-mind-map` with metadata, scripts and references. Python AST; TypeScript compiler + Vue SFC for JS/TS/JSX/TSX/Vue; Tree-sitter for Java/C/C++/Go. Dependencies pinned in independent runtime, never in target project. Builds offline and do not execute target code.
2. Resolve functions/methods/constructors, file/line/signature and calls using scope/imports/packages/explicit receiver types. Do not guess global same-name matches or ambiguous overloads/dynamic dispatch. Callback registration is separate; diagnostics retain uncertain calls.
3. One main XMind; modules auto-paginate, directory directly links all pages, then references directly link primary function topics. <=24 functions and <=40 visible calls including references per page. Cards about 300x82; 17pt text, 20pt headings; curve lanes >=32px. Full graph retained in nodes+edges JSON and Markdown. Calls may cycle; tree must not.
4. Visible selection: degree >=5, top 2 per file, forced entry/initialization/auth/route/start/stop. Long names wrap/truncate with full text in notes. Unobstructed same-page curves; cross-page or obstructed/long edges use short caller-labelled references.
5. Chinese file and key-function purposes from source docs plus agent reading. Annotation content hashes invalidate stale descriptions during offline updates. Never invent undocumented returns/errors/performance.
6. CLI build/update/validate/doctor; default source/docs/code-map, configurable output/groups/exclusions/display. Double-click Windows updater locates installed skill runtime. Generated README preserves update instructions.
7. Validate staging before replacing managed generated files, archive old snapshot, rollback on failure, preserve user files, lock concurrent builds.
8. Per-language fixtures; cross-file imports/aliases/methods/callbacks/recursion/ambiguity. Chinese/space paths, missing dependencies, syntax errors, add/change/delete source, repeated updates, rollback, read-only original-project regression. Validate IDs/links/fonts/geometry/canonical-to-visual parity. Record native client check independently.
9. Skill creator validation, installed skill build/update smoke. Standards and spec independent reviews. Repo contains source/tests/install docs, no runtime dependencies or generated user maps.
