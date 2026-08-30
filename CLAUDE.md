# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Moonlark is a multi-functional chatbot built on Python 3.11+ and the Nonebot2 framework. It supports multiple chat platforms (QQ, Discord) through various adapters (OneBot V11/V12, QQ official adapter). The project follows a plugin-based architecture with 67 custom plugins located in `src/plugins/`.

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

### Server Environment

The production server (`xdnas`) runs:
- Python 3.11.2
- Poetry 2.3.2
- MySQL 9.3.0 (MySQL Community Server)

**Note**: MySQL does not support `CREATE INDEX IF NOT EXISTS` in all versions. Use `information_schema.statistics` to check index existence before creating indexes in plugin code.

## Essential Commands

### Code Quality
```bash
# Format code with Ruff
poetry run ruff format .

# Lint code
poetry run ruff check .

# Run pre-commit hooks manually
poetry run pre-commit run --all-files
```

### Testing
```bash
# Run tests with nonebug
poetry run nb test

# Run specific test file
poetry run nb test tests/test_name.py
```

### Database Migrations
```bash
# Create new migration
poetry run nb orm revision

# Apply migrations
poetry run nb orm upgrade

# Rollback migration
poetry run nb orm downgrade -1
```

### Plugin-Specific Scripts
```bash
# Generate help documentation
poetry run nb run --script larkhelp-generate

# Initialize larkcave hashes
poetry run nb run --script larkcave-init-hash
```

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

### Code Style

- Python 3.11+ syntax
- Line length: 120 characters
- Formatter: Ruff (configured in `pyproject.toml`)
- Type hints required for function parameters (ANN001)
- Line endings: LF (Unix-style)

### What NOT to Do

- Don't use `git add -A` or `git add .` (stage specific files)
- Don't edit Crowdin-managed files (`src/lang/en_us/*`, `src/lang/zh_tw/*`, `README_eng.md`, `README_zho.md`)
- Don't store BLOB data in ORM (use LocalStore instead)
- Don't bypass LarkUser to get user information
- Don't use blocking I/O operations

## Testing

- Test framework: pytest with pytest-asyncio
- Test files: `tests/`
- Use `nonebug` for Nonebot plugin testing
- Async mode: auto (configured in `pyproject.toml`)

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

### CI/CD

- GitHub Actions workflows in `.github/workflows/`:
  - `ci.yaml`: runs `npm run lint` on Node 22 for pushes and PRs
  - `deloy.yaml`: on push to `main`, builds and deploys `dist/` to GitHub Pages (`peaceiris/actions-gh-pages`)

## Project Structure

```
Moonlark/
├── src/
│   ├── plugins/          # 67 custom plugins
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
