# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| latest  | Yes       |

Only the latest commit on main receives security updates.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Use [GitHub Security Advisories](https://github.com/sydlexius/prose-tooling/security/advisories/new)
to report vulnerabilities privately. This ensures the issue can be triaged and a
fix prepared before public disclosure.

When reporting, please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- The affected version(s) or commit(s)
- A suggested fix, if you have one

You should receive an initial acknowledgment within 72 hours. Critical issues
will be addressed as quickly as practical.

## Scope

In scope:

- The linter CLI and its configuration handling
- The container/service wrapper scripts under `bin/`
- Handling of any document content passed to the LanguageTool backend

Out of scope:

- Vulnerabilities in LanguageTool itself (report those upstream)
- Vulnerabilities in upstream Python dependencies (report those upstream)
- Issues requiring local shell access to the machine running the linter

## Security Measures

- **Pinned actions:** all GitHub Actions are pinned to a commit SHA
- **Least-privilege tokens:** workflow permissions are declared at job level
- **No persisted credentials:** checkouts use `persist-credentials: false`
- **CodeQL:** Python and workflow (`actions`) analysis run on every PR
- **Local-first:** document content is sent only to the configured backend
