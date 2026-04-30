# Contributing

Thanks for your interest in improving this project.

## Development Setup

1. Fork and clone the repository.
2. Install dependencies:

```bash
uv sync
```

3. Run checks locally:

```bash
uv run ruff check
uv run pytest
```

## Branching And Pull Requests

1. Create a focused branch from `develop`.
2. Keep changes small and scoped to one concern when possible.
3. Add or update tests for behavior changes.
4. Update documentation when user-facing behavior changes.
5. Open a pull request with:
   - What changed
   - Why it changed
   - How it was tested

## Reporting Issues

When opening an issue, include:

- Expected behavior
- Actual behavior
- Reproduction steps
- Environment details (OS, Python version, Docker usage)
- Relevant logs or screenshots

## Style And Quality

- Follow existing code style and naming patterns.
- Keep APIs backward compatible unless a breaking change is intentional and documented.
- Prefer clear, maintainable code over clever shortcuts.

## Security

Do not open public issues for sensitive vulnerabilities.
Please contact the maintainers privately for responsible disclosure.