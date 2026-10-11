---
name: recheck-after-submit
description: "Recheck the project after submitting or completing code changes. Use after implementation to run pylint, ESLint, Vite build, and pytest, then fix failures."
---

# Recheck After Submit

Run this workflow after implementing code changes and before reporting the work as complete.

## Procedure

1. Inspect the repository scripts and tracked files to identify the project's existing ESLint and Vite build commands.
2. Run `pylint $(git ls-files '*.py')` for tracked Python files.
3. Run the project's ESLint command and Vite production build.
4. Run the relevant `pytest` suite, expanding to all tests when practical.
5. Fix failures caused by the changes, then rerun the checks that failed. Do not report success for checks that were skipped or failed; state any unavailable checks explicitly.
