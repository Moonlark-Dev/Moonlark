# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Moonlark is a multi-functional chatbot built on Python 3.11+ and the Nonebot2 framework. It serves QQ through several adapters (OneBot V11/V12 and the QQ official adapter fork). The project follows a plugin-based architecture with custom plugins located in `src/plugins/`.

## Development Setup

### Installation
```bash
# Install dependencies using Poetry
poetry install

# Copy environment template
cp .env.template .env
# Edit .env with your configuration
```

### Running the Bot
```bash
# Start the bot
poetry run nb run

# Or use nb-cli directly
nb run
```

### Local Development Notes

- Every `nb` command loads all plugins. If `NO_PROXY`/`no_proxy` contains `[::1]`, httpx fails to build its
  proxy mounts (`InvalidURL`) and `nonebot_plugin_openai` fails to import, which cascades into a long list of
  "Cannot load plugin" errors. Run commands with the broken variable removed:
  `env -u NO_PROXY -u no_proxy poetry run nb orm check`.
- Running the whole test suite (`pytest tests/`) loads every plugin and is memory hungry; while developing,
  run only the test files related to your change.

### Server Environment

The production server (`xdnas`) runs:
- Python 3.11.2
- Poetry 2.3.2
- MySQL 9.3.0 (MySQL Community Server)

**Note**: MySQL does not support `CREATE INDEX IF NOT EXISTS` in all versions. Use `information_schema.statistics` to check index existence before creating indexes in plugin code.

## Essential Commands

### Code Quality
```bash
# Format code with black (line-length 120; this is what pre-commit.ci enforces)
poetry run black .

# Lint code with ruff (configuration in pyproject.toml)
poetry run ruff check .

# Run pre-commit hooks manually (flake8 --select=E9 + black, see .pre-commit-config.yaml)
poetry run pre-commit run --all-files
```

Do NOT reformat the repository with `ruff format`: on several existing files its output differs from black
(for example it removes the blank line after a class statement), so it rewrites unrelated files and fights the
black hook configured in `.pre-commit-config.yaml`.

### Testing
```bash
# Run the whole suite (exactly what CI runs)
poetry run pytest tests/ -v

# Run a single test file (preferred while developing)
poetry run pytest tests/test_name.py -v
```

### Database Migrations
```bash
# Create a new migration (autogenerate — review the generated file before committing)
poetry run nb orm revision -m "add xxx"

# Apply migrations
poetry run nb orm upgrade

# Report pending model/schema differences; CI requires "没有检测到新的升级操作"
poetry run nb orm check

# List revision heads; there must be exactly one head
poetry run nb orm heads

# Roll back to a revision: pass the revision id, `nb orm downgrade -1` fails ("No such option '-1'")
poetry run nb orm downgrade <revision>
```

Migration rules (all of them are enforced by CI):

- Every change to a plugin's `models.py` needs a migration, otherwise `nb orm check` fails the PR.
- `revision` / `down_revision` must form a **single head**. When `main` gains a new migration, re-parent yours
  onto the new head, or the branch ends up with two heads.
- `nb orm revision` autogenerates from the live metadata. If a plugin fails to load locally (see Local
  Development Notes), its tables show up as unrelated `drop_table` operations — delete everything that is not
  part of your change.
- Use `op.batch_alter_table` for column changes and give new columns `nullable=True` or a `server_default` so
  the MySQL production server can apply them.
- Verify against a throwaway database before pushing, for example
  `SQLALCHEMY_DATABASE_URL="sqlite+aiosqlite:////tmp/mig.db" poetry run nb orm upgrade`, then the same with
  `nb orm check`.

### Plugin-Specific Scripts
```bash
# Generate help documentation from help.yaml (CI regenerates COMMANDS.md automatically)
poetry run nb larkhelp-generate zh_hans COMMANDS.md

# Initialize larkcave hashes
poetry run nb larkcave-init-hash
```

Each registered script is a top-level nb command (`nb <script>`); `nb run` only starts the bot and has no
`--script` option.

## Architecture

### Core Plugin System

Moonlark uses a modular plugin architecture. All custom plugins are in `src/plugins/` and are registered in `src/pyproject.toml`.

**IMPORTANT**: When adding or removing a plugin, update BOTH registration files:
- Root `pyproject.toml` (`[tool.nonebot]` `plugins` list)
- `src/pyproject.toml` (`[tool.poetry]` `packages` list)

**Core Infrastructure Plugins** (use these in new plugins):
- **LarkUser** (`nonebot_plugin_larkuser`): User information and registration system
- **LarkUtils** (`nonebot_plugin_larkutils`): User ID and group ID utilities
- **LarkLang** (`nonebot_plugin_larklang`): Localization/i18n system
- **Render** (`nonebot_plugin_render`): Jinja2 template rendering
- **LocalStore**: File storage (via nonebot-plugin-localstore)
- **ORM**: Database operations (via nonebot-plugin-orm with SQLAlchemy)
- **Alconna**: Command parsing and message sending (via nonebot-plugin-alconna)
- **HtmlRender**: Markdown to image rendering (via nonebot-plugin-htmlrender)

### Multi-Bot Runtime

Moonlark keeps several bot accounts online at the same time (at least one OneBot V11 account and the QQ
official bot). Which account handles an incoming message, and which account a message is sent with, is decided
by `nonebot_plugin_bots` and always keyed on `bot.self_id`:

- `BOTS_LIST` maps a bot code to its `self_id`; `BOTS_APPID_MAP` maps a QQ official AppID to the matching QQ
  number so messages sent by Moonlark's own accounts can be recognised and ignored.
- Groups that contain both an OneBot bot and the QQ official bot are linked through `GroupBind`
  (QQ group number ↔ `group_openid`). OneBot takes precedence; the QQ official bot answers only when it is
  mentioned or when no OneBot bot is available. A session is assigned to one bot at a time.
- Private chat can be disabled per bot with `.pm on|off` (`UserBotPrivateChatSettings`, keyed by
  `(user_id, bot_id)`).
- Check `nonebot_plugin_bots.is_bot_online(bot_id)` / `get_bot_status(bot_id)` before pushing a message to a
  user: a stored session may point at an account that is currently offline.

### User IDs and Account Mapping

`nonebot_plugin_larkutils.get_user_id()` returns the **main account** id, not the adapter-native id:
`nonebot_plugin_auto_bind` maps a QQ official openid onto the OneBot QQ number through `MainAccountMapping`
(`nonebot_plugin_larkutils.subaccount`). Consequences:

- Anything keyed by `user_id` (per-user settings, sessions, relationships) is keyed by the main account.
- To talk to an adapter you need the adapter-native id from `event.get_user_id()` — the openid for QQ official
  C2C, the QQ number for OneBot — not the main account id.
- `get_group_id()` returns the platform-prefixed session key: `qq_{user_id}` in private chat, and
  `qq_{group_number}` / `qq_{group_openid}` in groups.

### Plugin Structure

Typical plugin layout:
```
nonebot_plugin_example/
├── __init__.py          # Plugin metadata and exports
├── config.py            # Plugin configuration
├── models.py            # ORM models
├── help.yaml            # Help documentation
├── matchers/            # Command handlers
└── utils/               # Utility functions
```

### Help YAML Format (`help.yaml`)

Each plugin registers command help in a `help.yaml` file. Standard format:

```yaml
plugin: <plugin_name>
commands:
  <command_name>:
    description: help.description     # LarkLang.text key
    details: help.details             # LarkLang.text key
    usages:                           # list of LarkLang.text keys
      - help.usage1
      - help.usage2
    category: game|tools|community|setting
```

Shorthand format:

```yaml
<command_name>: <localization_key>;<usage_count>;<category>
```

The **middle number is the usage count** (number of `help.usage<N>` entries in the lang file). For example, `rise-rank: help;3;community` expands to `description: help.description`, `details: help.details`, `usages: [help.usage1, help.usage2, help.usage3]`, `category: community`.

Every `help.usage<N>` text must follow the format `指令名 <子命令> <args...> [options] (说明)`: the explanation part is wrapped in **half-width (ASCII) parentheses** `( )`, e.g. `jrrp (查看今日人品值)` — do NOT use a ` - ` separator or full-width parentheses `（）` around the explanation.

See `docs/plugins/larkhelp.md` for full documentation.

### Localization

All user-facing text must be localized using LarkLang:
- Base language files: `src/lang/zh_hans/` (Chinese Simplified - source)
- Crowdin-managed: `src/lang/en_us/`, `src/lang/zh_tw/` (DO NOT edit directly)
- Use LarkLang's translation functions in code

### Database

- Default: SQLite (`database.db`)
- Configured via `SQLALCHEMY_DATABASE_URL` in `.env`
- Use nonebot-plugin-orm for all database operations
- Migrations managed with Alembic in `migrations/`

## Code Standards

### Required Practices

1. **Async Operations**: Use async/await for I/O operations (file, network, database)
2. **File Encoding**: Always specify `encoding="utf-8"` when opening files (Windows compatibility)
3. **Storage**: Use LocalStore for file storage, ORM for structured data
4. **Commands**: Use Alconna for command parsing
5. **User Data**: Access user info through LarkUser, not directly
6. **Localization**: All user-visible text must use LarkLang
7. **Message Sending**: Use `UniMessage.send()` when the message carries a keyboard/buttons (e.g. QQ official bot interactive messages) and read the returned `Receipt` for message ids. `UniMessage.send()` only sends — after it you must separately call `matcher.finish()` to end the handler. Plain text messages without a keyboard keep using `matcher.send(text, at_sender=...)`:
   ```python
   # Keyboard/button message (QQ official bot): UniMessage.send + separate matcher.finish
   receipt = await UniMessage().style("text", "markdown").keyboard(...).send(target=event, bot=bot)
   msg_id = receipt.msg_ids[0]["message_id"]  # msg_ids[0] may be a dict or a pydantic model
   await matcher.finish()

   # Plain text without keyboard: matcher.send(at_sender=True) is fine
   await matcher.send("text", at_sender=True)
   ```

### QQ Official Bot Interactive Buttons (Keyboard)

The QQ official bot adapter (`nonebot.adapters.qq`, imported as `QQBot`) supports keyboard buttons attached to messages. Follow this convention (see `nonebot_plugin_sign`, `nonebot_plugin_larkhelp`, `nonebot_plugin_quick_math`, `nonebot_plugin_jrrp`):

```python
from nonebot.adapters.qq import Bot as QQBot
from nonebot_plugin_alconna import Button, UniMessage
from nonebot_plugin_larkutils.command import get_command_prefix

# Inside an alconna handler (bot/event are injected)
if isinstance(bot, QQBot):
    message = (
        UniMessage()
        .style('消息文本', "markdown")
        .keyboard(
            Button("enter", "按钮名称", text=f"{get_command_prefix()}jrrp r"),
            Button("enter", "按钮名称", text=f"{get_command_prefix()}jrrp rr"),
        )
    )
    await message.send(target=event, bot=bot)
    # UniMessage.send 只负责发送，必须单独调用 matcher.finish 结束处理器
    await matcher.finish()
```

Guidelines:
- A `Button("enter", label, text=...)` sends the `text` back into the chat when clicked, so it should be a full command like `f"{get_command_prefix()}jrrp r"` (use `get_command_prefix()` from `nonebot_plugin_larkutils.command`).
- Attach the keyboard with `.keyboard(*buttons)`; the button "enter" type triggers a normal message that the alconna matcher will match.
- `UniMessage.send()` is for messages that carry a keyboard — it does NOT finish the handler, so always write `matcher.finish()` separately afterwards; extract the message id from the returned `Receipt.msg_ids` when needed.
- To mention a user, prepend `<qqbot-at-user id="{user_id}" />` inside the markdown content.
- Non-QQ platforms (no keyboard) keep plain text: `matcher.send(text, at_sender=True)`.

### Code Style

- Python 3.11+ syntax
- Line length: 120 characters
- Formatter: **black** (configured in `pyproject.toml` and `.pre-commit-config.yaml`); never reformat the
  repository with `ruff format`, its output disagrees with black on existing files
- Linter: ruff (`[tool.ruff]` in `pyproject.toml`; `E501`, `I001`, `RUF100` … are ignored while preview rules
  such as `COM812` and `TCH` are active)
- Type hints required for function parameters (ANN001)
- Line endings: LF (Unix-style)

### What NOT to Do

- Don't use `git add -A` or `git add .` (stage specific files)
- Don't edit Crowdin-managed files (`src/lang/en_us/*`, `src/lang/zh_tw/*`, `README_eng.md`, `README_zho.md`)
- Don't store BLOB data in ORM (use LocalStore instead)
- Don't bypass LarkUser to get user information
- Don't use blocking I/O operations

## Testing

- Test framework: pytest with pytest-asyncio (async mode: auto, configured in `pyproject.toml`)
- Test files: `tests/`
- Import plugin modules **inside** the test function, as every existing test does: `tests/conftest.py`
  initialises NoneBot only in a session-scoped autouse fixture, so a module-level plugin import fails during
  collection with `NoneBot has not been initialized`.
- `tests/conftest.py` also registers the Console/OneBot V11 adapters, loads every plugin from
  `pyproject.toml`, and sets `SQLALCHEMY_DATABASE_URL=sqlite+aiosqlite://` plus `ALEMBIC_STARTUP_CHECK=False`.
- `nonebug` is installed but most tests use plain `unittest.mock`; follow the file you are editing.
- Prefer a single test file: the full suite loads every plugin and is memory hungry.

## CI (GitHub Actions)

`.github/workflows/ci.yml` runs on every PR update (Python 3.11 + Poetry):

1. `poetry lock` / `poetry install --all-groups` / `poetry update`
2. `nb orm upgrade`, then `nb orm check` — the job fails unless it prints `没有检测到新的升级操作`
3. `poetry run pytest tests/ -v`, with `SQLALCHEMY_DATABASE_URL=sqlite+aiosqlite://` and
   `ALEMBIC_STARTUP_CHECK=False`
4. `nb larkhelp-generate zh_hans COMMANDS.md`
5. If the working tree changed (usually `poetry.lock` or `COMMANDS.md`), the job commits and pushes it back to
   the PR branch as `Auto update from GitHub Actions`

Practical consequences:

- A model change without a migration fails CI at step 2.
- Run `git pull --rebase` before pushing: the CI job may already have pushed a commit to your branch.
- A run triggered by that bot push is parked as `action_required` and must be approved manually in the Actions
  UI before it executes.
- Independently of this workflow, PRs also carry pre-commit.ci (`autofix_prs: true`, it may push
  `格式化代码` commits), Codacy and CodeFactor checks.

## Environment Variables

Key variables in `.env` (see `.env.template` for full list):
- `SQLALCHEMY_DATABASE_URL`: Database connection string
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`: OpenAI API configuration
- `OPENAI_DEFAULT_MODEL`: Default model for OpenAI-compatible APIs
- `MODEL_OVERRIDE`: JSON mapping for model overrides per application
- `WOLFRAM_API_KEY`: Wolfram Alpha API
- `BAIDU_API_KEY`, `BAIDU_SECRET_KEY`: Baidu translation API
- `SENTRY_DSN`: Error tracking
- `MOONLARK_API_BASE`: Moonlark API base URL
- `WAKATIME_APP_ID`, `WAKATIME_APP_SECRET`: WakaTime integration
- `TRANSLATE_DEEPLX_URL`: DeepLX translation endpoint
- `METASO_API_KEY`: Metaso search API
- `HTMLRENDER_BROWSER`: Browser for HTML rendering (default: firefox)

## Adapters

Supported chat platforms:
- OneBot V11 (QQ)
- OneBot V12
- QQ Official (uses custom fork `github.com/Moonlark-Dev/adapter-qq`, imported as `nonebot.adapters.qq`)

QQ official adapter specifics (easy to get wrong):

- `Bot.self_id` is the **AppID**, not a QQ number — never treat `self_id` as an account number.
- C2C (private) events: `event.get_user_id()` returns the counterpart's **openid**, `event.get_session_id()`
  returns `friend_{openid}`, and `nonebot_plugin_session` derives the key `qq_{openid}`. Sending to that user
  requires the openid; a main-account QQ number will not work.
- Group events carry a `group_openid`, linked to an OneBot group number through
  `nonebot_plugin_bots.GroupBind`.
- C2C replies need a fresh `qq.reply_seq` in the target extras; see
  `nonebot_plugin_chat/core/processor.py` for the existing handling.

## Frontend (moonlark-frontend)

The web frontend is maintained in a separate repository: <https://github.com/Moonlark-Dev/moonlark-frontend>. It is a Vue 3 + TypeScript single-page application built with Vite, using MDUI 2 for UI components, and deployed to GitHub Pages.

### Tech Stack

- Vue 3 + TypeScript, Vue Router 4
- Vite 7 (`@vitejs/plugin-vue`, `@vitejs/plugin-vue-jsx`)
- MDUI 2 + Sass for styling
- `@vueuse/core` utilities
- ESLint 9 (`eslint-plugin-vue`, `@vue/eslint-config-typescript`) for linting

### Commands

```bash
npm install        # Install dependencies
npm run dev        # Start Vite dev server with hot reload
npm run build      # Production build (outputs to dist/)
npm run preview    # Preview the production build
npm run lint       # Lint with ESLint
npm run lint-fix   # Auto-fix lint issues
```

### Project Structure

```
moonlark-frontend/
├── src/
│   ├── pages/         # Route views (LoginView, HomeView, UserView, SettingsView, RankingsView, HelpView, AdminMenuPanelView)
│   ├── components/    # Shared components (Navbar, SessionManager, BindMainAccount, ChangeNickName, Toast, ...)
│   ├── utils/         # API client (api.ts), cookie/session helpers, cache, toast, etc.
│   ├── styles/        # Global styles (index.scss)
│   ├── App.vue        # Root component
│   ├── main.ts        # App entry (MDUI setup, color scheme, auth error handler)
│   └── routes.ts      # Route definitions
└── public/            # Static assets (favicon.ico, CNAME)
```

### API & Auth

- API base URLs are hardcoded in `src/utils/utils.ts`: `BASE_URL = "https://moonlark-api.itcdt.top"` and `API_URL = BASE_URL + "/api"`.
- Requests go through `apiRequest`/`apiRequestFull` in `src/utils/api.ts`; authenticated requests send the `sessionID` cookie as `Authorization: Bearer <sessionID>`.
- 401 responses trigger a global handler (registered in `main.ts`) that redirects to `/login` with the current route as a `redirect` query parameter.

### CI/CD (frontend repository)

- GitHub Actions workflows in the frontend repository's `.github/workflows/`:
  - `ci.yaml`: runs `npm run lint` on Node 22 for pushes and PRs
  - `deloy.yaml`: on push to `main`, builds and deploys `dist/` to GitHub Pages (`peaceiris/actions-gh-pages`)

## Project Structure

```
Moonlark/
├── src/
│   ├── plugins/          # Custom plugins
│   ├── lang/             # Localization files
│   ├── prompt/           # Jinja2 prompt templates for AI features
│   ├── static/           # Static assets
│   └── templates/        # Jinja2 templates
├── migrations/           # Alembic database migrations
├── tests/                # Test files
├── docs/                 # Documentation
├── pyproject.toml        # Root project config
├── src/pyproject.toml    # Custom plugins package config
├── COMMANDS.md           # Auto-generated command documentation
├── CONTRIBUTING.md       # Contribution guidelines
├── CODE_OF_CONDUCT.md    # Code of conduct
└── .env                  # Environment configuration (not in git)
```

## License

AGPL-3.0 - All contributions must be compatible with this license.
