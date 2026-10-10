# Spec: AI Chat Command Execution

## Objective

Allow an AI chat provider to run commands in the selected project and use their
output to continue its response. Persist one permission mode per user, shared
across that user's providers:

- `manual`: show every proposed command and wait for **Run** or **Cancel**.
- `risky`: run commands recognized as read-only; ask before running commands
  that may change state.
- `allow_all`: run proposed commands without asking.

When approval is needed, the chat shows the exact command and its permission
decision. On approval, execute it in the project directory, return its result
to the provider, and continue the response. Cancellation must not execute it.
This is for commands requested by AI chat only; it does not replace the
interactive terminal.

## Assumptions

1. A stored permission belongs to the signed-in user and is shared across all
   their configured providers; it does not change another user's permission.
2. In `risky` mode, only commands positively identified by a conservative
   read-only policy run automatically. Compound, unknown, or unclassifiable
   commands require approval.
3. Commands run with the selected project as their working directory. This
   feature does not claim to sandbox operating-system access outside that
   directory.
4. Existing chat turns remain streamed and resumable; command execution and
   approval state are scoped to the active turn.

## Tech Stack

- API: Python 3.12+, FastAPI, SQLAlchemy, Pydantic, pytest, Ruff.
- Web: React 19, TypeScript, Vite, ESLint.
- AI providers: the existing provider adapter/tool-call interface for OpenAI,
  Anthropic, and Gemini.
- Preferences: the existing per-user `user_settings` key/value storage.
- Command execution: a bounded non-interactive subprocess runner scoped to the
  selected project's working directory (not an OS-level sandbox).

## Commands

```bash
# Focused API tests
.venv/bin/pytest tests/test_ai_chat_commands.py tests/test_ai_chat.py tests/test_ai_provider_adapters.py

# API lint
.venv/bin/ruff check app/modules/ai_chat tests/test_ai_chat.py

# Frontend build/type-check
npm run build --prefix web

# Frontend lint
npm run lint --prefix web
```

## Project Structure

- `app/modules/ai_chat/` — provider-independent chat tool definitions,
  execution, streaming, and HTTP routes.
- `app/modules/ai_providers/` — shared tool-call contract and provider
  adapters.
- `app/modules/terminal/` — existing authenticated interactive terminal and
  project-scoped process facilities.
- `app/core/user_settings.py` — generic per-user preference persistence.
- `web/src/components/ide/ChatPanel.tsx` — chat UI, command approval controls,
  and stream event handling.
- `web/src/lib/chatStream.ts` — typed chat stream events and NDJSON parsing.
- `web/src/lib/api.ts` — API request helpers and typed chat/settings contracts.
- `web/src/i18n/` — localized UI strings.
- `tests/test_ai_chat.py` — provider-independent API/tool/stream tests.
- `tests/test_terminal.py` — existing terminal behavior tests.
- `docs/specs/` — feature specifications.
- `README.md` — user-facing AI chat capabilities and permission modes.

## Code Style

Follow existing typed Python services and discriminated TypeScript stream-event
unions. For example, chat stream events are narrowed by `type`:

```ts
if (streamEvent.type === 'text_delta') {
  appendAssistantText(streamEvent.text)
}
```

Python APIs use typed parameters/returns, small service functions, explicit
validation, and `ErrorCode`/`api_error` for reported failures. Frontend labels
and errors use `react-i18next`; follow existing component and API-helper
patterns. Do not use silent defaults for invalid permission values or command
execution failures.

## Testing Strategy

- Unit-test permission validation, persistence, and read-only/risky
  classification, including compound, malformed, and unknown commands.
- API-test reading/updating a user's mode, authentication/CSRF behavior, and
  isolation between users.
- Test every provider can receive the command tool and process tool results
  without regressing existing file tools and proposals.
- Test `manual` approval and cancellation, `risky` auto-run versus approval,
  and `allow_all` execution; verify rejected/cancelled commands never execute.
- Test command working directory, exit status, bounded output/runtime, and
  failures. Verify command output is returned to the model and its final answer
  is streamed and persisted.
- Build and lint the frontend to validate the approval UX, localization, and
  event typing.

## Boundaries

- Always:
  - Apply user permission consistently across all providers and subsequent
    chats.
  - Validate tool arguments and run approved commands only in the authorized
    project context.
  - Require explicit approval for all commands in `manual` mode and for
    commands not confidently recognized as read-only in `risky` mode.
  - Bound execution time and output, surface failures, and preserve existing
    chat/file-tool behavior.
  - Never treat cancellation, timeout, malformed tool calls, or approval
    transport failures as success.
- Ask first:
  - Adding dependencies, changing CI, or introducing a database migration.
  - Expanding execution beyond the project working directory or adding
    provider-specific permission modes.
- Never:
  - Expose provider credentials in chat events or command output.
  - Execute a command after cancellation or without the required approval.
  - Claim the project working directory is an OS-level security sandbox.

## Success Criteria

1. A user can read and persist exactly one of `manual`, `risky`, and
   `allow_all`; invalid values are rejected.
2. Changing the mode takes effect for every AI provider for that user and
   remains in effect after reload/sign-in.
3. OpenAI, Anthropic, and Gemini can request command execution through the
   existing provider tool-call mechanism.
4. `manual` displays the exact proposed command with **Run** and **Cancel**;
   no command starts before **Run**. Cancelled requests do not execute.
5. In `risky`, only positively recognized read-only commands execute without
   approval; every other command waits for user approval.
6. In `allow_all`, valid proposed commands run without an approval prompt.
7. Commands run relative to the selected project, their bounded result
   (including exit status) is passed back to the provider, and the final AI
   response streams and persists as before.
8. Existing provider selection, conversation history, project-file tools, and
   proposed-change review continue to work.
9. Focused API tests, frontend build, and frontend lint pass.

## Open Questions

- None. The initial implementation uses a 20-second command timeout, captures
  at most 16 KiB of combined output, and auto-runs only simple `pwd`, `ls`,
  and constrained `git status`/`diff`/`log` forms accepted by the conservative
  classifier in `risky` mode.
