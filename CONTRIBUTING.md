# Contributing to MPR Collector

Contributions, bug reports, and suggestions are welcome.

## Reporting a problem

When reporting a bug, please include:

- Windows version
- Python version
- What you expected to happen
- What actually happened
- Steps to reproduce the problem

Do not include private experiment data, saved folder paths, presets, credentials, or other sensitive files.

## Making a change

1. Create a branch from `main`.
2. Make the smallest change needed.
3. Run the test suite:

    python -m unittest discover -s tests -v

4. Confirm that MPR Collector still launches and that the affected workflow works as expected.
5. Open a pull request describing what changed and why.

## Code guidelines

- Keep the application dependency-free where practical.
- Preserve source-file safety: source experiment files must never be moved, renamed, or deleted.
- Avoid storing user paths, presets, experimental data, or credentials in the repository.
- Add or update tests when behavior changes.
- Keep changes focused rather than combining unrelated refactors.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.