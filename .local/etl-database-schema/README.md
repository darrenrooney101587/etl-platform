# etl-database-schema

`etl-database-schema` is a reusable Benchmark-specific Django base project designed to be extended by downstream Django services (for example, a web service that needs Benchmark defaults). It provides:

- Base settings and middleware
- SAML2 authentication
- OTP enforcement
- 404/500 templates
- Shared static files (CSS/JS/images)
- Common views/middleware/utilities

## Purpose (Benchmark Boilerplate)

This repository is the Benchmark-specific Django boilerplate. Its goal is to centralize Benchmark defaults, security posture, and shared apps/models so downstream projects can inherit instead of re-implementing. Keeping these conventions in one place gives us:

- Consistency across services (auth, logging, middleware, directory layout)
- Less duplication and faster new-service bootstrapping
- Easier compliance and security updates (one change, many consumers)
- Predictable upgrade path via versioned releases

## What this package provides

- Settings baseline: `etl_database_schema/settings/base.py` with sensible defaults and env-driven overrides
- Auth flows:
  - Password login + TOTP (two-factor)
  - Azure SAML SSO with MFA enforcement (via CustomSAMLBackend)
- Middleware:
  - ForceCustomLoginMiddleware (unify login URL)
  - CaptureSAMLResponseMiddleware (parse SAML for MFA signal)
  - RestrictSSOAccessMiddleware (SSO users limited until granted permissions)
  - EnforceAdminOTP (OTP required for admin, except for SSO)
  - OTPRequiredMiddleware (view-level OTP enforcement)
  - Optional Debug Toolbar
  - Lightweight per-request profiler (opt-in via ?profile_page=true)
- URLs:
  - Health check at `/healthz` (and `/healthz/`)
  - Accounts endpoints mounted at `/accounts/` (login, logout, 2FA setup/verify, backup tokens)
  - SAML endpoints mounted under `/saml2/`
  - Admin at `/admin/`
- Templates/Static:
  - Core error pages `etl_database_schema/templates/{404,500}.html`
  - Shared static at `etl_database_schema/static/`
- Account app: views, urls, templates, utilities for auth + OTP
- BMS data models: an unmanaged models package (`etl_database_schema/apps/bms/models/`) mapping to existing BMS tables for read/write where appropriate (requires correct DB connection)

## Directory Structure (Core)

```
etl_database_schema/
├── apps/
│   ├── account/         # login, logout, OTP, SAML backend, templates
│   └── bms/             # unmanaged BMS models (map to existing DB)
│       └── models/
├── middleware.py
├── static/
├── templates/
└── settings/
    └── base.py
```

---
#### Add `etl-database-schema` to your project with Poetry

The package name is `etl-database-schema` (version currently `0.4.0`). Choose one of the installation methods below.

- From PyPI (if published):
  - Command:
    ```bash
    poetry add etl-database-schema==0.4.0
    ```
  - pyproject.toml:
    ```toml
    [tool.poetry.dependencies]
    etl-database-schema = "==0.4.0"
    ```

- From GitLab over SSH (recommended for private/internal use):
  - Replace <group>/<repo> with your actual path (e.g., benchmark/etl-database-schema) and pin to a tag when possible.
  - Command (pin to tag):
    ```bash
    poetry add "git+ssh://git@gitlab.dev-benchmarkanalytics.com/<group>/<repo>.git#v0.4.0"
    ```
  - Command (track a branch):
    ```bash
    poetry add "git+ssh://git@gitlab.dev-benchmarkanalytics.com/<group>/<repo>.git#main"
    ```
  - pyproject.toml (equivalent):
    ```toml
    [tool.poetry.dependencies]
    etl-database-schema = { git = "ssh://git@gitlab.dev-benchmarkanalytics.com/<group>/<repo>.git", tag = "v0.4.0" }
    ```

Notes:
- Prefer pinning to a tag (e.g., v0.4.0) for reproducible builds.
- For SSH installs in Docker, ensure your SSH key is available to the container (see Docker notes in this README).
- To upgrade to the latest tag: update the tag in `pyproject.toml` and run `poetry update etl-database-schema`.

---
## Architecture and How to Inherit

Downstream projects typically do one of the following:

- Use core settings directly by pointing `DJANGO_SETTINGS_MODULE` to `etl_database_schema.settings.base`
- Or create your own `settings.py` that imports and overrides the core baseline

Example downstream `settings.py` layering:

```python
# your_project/settings.py
from etl_database_schema.settings.base import *  # noqa

# Project-specific toggles/overrides
DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS += ["your-service.internal"]

# Extend installed apps and middleware
INSTALLED_APPS += [
    "your_app",
]
MIDDLEWARE += [
    # "your_project.middleware.Something"
]

# Override/extend logging if needed
LOGGING["loggers"].update({
    "your_project": {"handlers": ["console"], "level": "INFO", "propagate": False}
})
```

### Important environment variables

- DEBUG: default False; toggles logging verbosity and debug-toolbar eligibility
- DJANGO_SECRET_KEY: required secret
- ALLOWED_HOSTS: space-delimited hosts; defaults to "127.0.0.1 localhost"
- CSRF_TRUSTED_ORIGINS: comma-delimited origins
- DJANGO_LOG_LEVEL: default INFO (or DEBUG if DEBUG=True)
- DJANGO_BACKEND_LOG_LEVEL: SQL logger level (default ERROR)
- DEBUG_TOOLBAR: true/false; when true, appends debug-toolbar
- Database (when not in Docker): POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT
- SAML:
  - SAML_ACS_URL, SAML_SLO_URL (auto-derived for localhost; override in env)
  - XMLSEC_BINARY (path to xmlsec1; auto-discovered if present)

### URLs provided by core

- /admin/
- /healthz and /healthz/
- /saml2/… (via djangosaml2)
- /accounts/… (named URLs): login, logout, otp-entry, setup-2fa, backup-tokens, disable-2fa, verify-2fa

### Authentication and MFA

- Password auth + TOTP: Users authenticate via username/password, then complete OTP at the `otp-entry` view. Admin area access requires a verified OTP session (unless SSO).
- Azure SAML SSO + MFA: CustomSAMLBackend extracts MFA assertion from the SAML response and denies access if MFA is not present. Successful SSO users are created/staffed and can be permissioned via groups.

### Middleware responsibilities

- ForceCustomLoginMiddleware: redirects default Django login routes to our custom login URL
- CaptureSAMLResponseMiddleware: attaches raw SAMLResponse XML to request for MFA parsing
- RestrictSSOAccessMiddleware: SSO-authenticated users see a warning and are redirected until groups/permissions are granted
- EnforceAdminOTP: requires OTP for /admin/ (SSO users bypass OTP per policy)
- OTPRequiredMiddleware: opt-in per-view OTP enforcement via mixins/flags
- ProfilingMiddleware: lightweight, opt-in profiler (`?profile_page=true`)

### Logging

- Structured JSON logging available via `python-json-logger` (DEFAULT_LOGGING_FORMAT=json)
- SQL logging is gated by DEBUG to avoid noise in production
- All installed apps get per-app loggers at the chosen level

### Health check

- GET /healthz returns `{ "status": "ok" }` (200) or `{ "status": "error" }` (500) on exception

### Templates and Static

- Error templates at `etl_database_schema/templates/`
- Static assets under `etl_database_schema/static/`
- Downstream apps can add their own `templates/` and `static/`; both are included in the template/static search paths

---
## BMS Data Models (Unmanaged)

The package `etl_database_schema.apps.bms.models` exposes a set of Django models mapped to existing BMS tables. Key points:

- These models are `managed = False` — migrations are not generated; they expect tables to exist
- Requires a valid Postgres connection with access to BMS tables
- Useful for read access and controlled write operations where appropriate
- Examples include: `BenchmarkUser`, `BenchmarkRole`, `Agency`, `Group`, `Notification`, `Snapshot` models, and many more

Usage example:

```python
from etl_database_schema.apps.bms.models.benchmark_user import BenchmarkUser

# Read by username
user = BenchmarkUser.objects.filter(username="jdoe").first()
if user:
    print(user.full_name)
```

---
## Quickstart (Downstream)

1) Add dependency (choose one): see Poetry section above

2) Create minimal settings

```python
# settings.py
from etl_database_schema.settings.base import *  # base defaults
ROOT_URLCONF = "admin.urls"  # example downstream URLConf
```

3) Wire URLs

```python
# admin/urls.py (downstream)
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from etl_database_schema import urls as core_urls
from your_app.views import index

urlpatterns = [
    path("", index, name="home"),
] + core_urls.urlpatterns + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
```

4) INSTALLED_APPS

```text
INSTALLED_APPS += [
  "your_app",
  "etl_database_schema.apps.account.apps.AccountsConfig",
]
```

5) Run

```bash
python manage.py migrate  # for your app’s migrations
python manage.py runserver
```

---
## Release and Versioning

- Version is defined in `setup.py`/`pyproject.toml` (currently 0.4.0)
- Release process (suggested):
  1. Update version in `setup.py` (and `pyproject.toml` if used)
  2. Commit and tag: `git tag vX.Y.Z && git push --tags`
  3. Consumers pin to the tag in Poetry: `#vX.Y.Z`
  4. Optionally publish to an internal index for wheel installs
- Write concise release notes highlighting settings changes, new middleware, and any breaking changes in URLs/auth flows.

---
## Support

- Issues/requests: open a ticket in the hosting Git repo
- Security or auth concerns: coordinate with the Benchmark platform team
