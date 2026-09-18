# Repository instructions

## Project map

- Python 3.14+ workspace managed with uv.
- `src/ewa/`: CLI application; `library/src/library/`: reusable primitives; `plugins/epub/src/epub/`: EPUB workflows.
- For EPUB work, read [EPUB_SPECIFICATION.md](library/EPUB_SPECIFICATION.md) for design contracts and [EPUB_TODO.md](library/EPUB_TODO.md) for implementation order.

## Working conventions

- Prefer simple, concrete APIs, few abstractions, and self-explanatory code. Omit docstrings or keep them very short when names and implementation make the purpose clear.
- Use docstrings to explain non-obvious reasons, constraints, or side effects. Add short examples for obscure transformations, such as why a particular link needs rewriting; do not narrate obvious code.
- Implement the requested migration step as a small reviewable change. Keep existing callers working; do not start later stages implicitly.
- Inspect the current checkout and existing edits before changing files. Preserve unrelated work; do not modify other worktrees or commit/merge unless requested.
- When asked to transfer changes to another checkout, check for overlapping edits and copy only the reviewed changes.
- Use synthetic EPUBs and temporary databases for migration tests. Real-book validation uses copies; preserve originals and existing analytics.
- Preserve persisted numeric reason codes. Do not silently change recipe scaffolding that deletes output or leaves original movement disabled.

## Validation

Run from the repository root, choosing paths relevant to the change:

```text
uv run ruff format <changed-python-files>
uv run pytest <focused-test-paths> -q -p no:cacheprovider -o log_cli=false
git diff --check
```

- Run focused lint/type checks when relevant. Existing unrelated Ruff/ty findings do not justify broad cleanup.
- Documentation-only edits need link, ordering, and diff checks; no Python tests are required.
- Report what changed, what was checked, and any limits of the validation.

## Documentation ownership

- `AGENTS.md`: durable contributor instructions and commands.
- `library/EPUB_SPECIFICATION.md`: EPUB responsibilities, contracts, rationale, and open design decisions. Distinguish current behavior from agreed but unimplemented behavior.
- `library/EPUB_TODO.md`: actionable work and completion status in execution order. Insert prerequisites before dependent steps and update numbering and references; do not append them out of order.
- Keep unscheduled work in a separate backlog after the ordered migration. Keep completed items as history.
- Update the owning document when a decision changes. Link to contracts instead of repeating design discussions or conversation history in TODOs.
- Treat the specification as a reference, not required user reading. Keep change explanations self-contained and concise; add documentation only when it resolves a concrete ambiguity or preserves a useful constraint.
