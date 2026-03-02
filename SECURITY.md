# Security Policy

> **License:** [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)
> **Copyright:** © 2026 Arne Magnus Tveita Løken
---

## Supported Versions

As this is a personal Curriculum Vitae project, security support is only provided for the latest version on the `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

I take the security of this automation pipeline and my personal data seriously. However, since this is a personal project, please do not report security vulnerabilities through public GitHub issues.

If you discover a vulnerability in the rendering logic, the CI/CD pipeline, or potential data leaks in the public builds, please report it by:

1. Opening a **GitHub Security Advisory** (if applicable) or,
2. Contacting me directly via the contact information listed on my [LinkedIn profile](https://linkedin.com/in/((( cv.contact.linkedin )))).

I will aim to acknowledge the report and initiate a fix via Dependabot or manual patch within a reasonable timeframe.

## Privacy and Data Protection

This repository is designed with a "Privacy by Design" approach:

- **Secrets Management:** Sensitive information (Email, Phone, Address) is stored in GitHub Environment Secrets and is never committed to the repository in plaintext.
- **Anonymization:** Public PDF builds are explicitly rendered without sensitive contact details using the `--public` flag in the rendering script.
- **Dependency Tracking:** Dependabot is active to ensure that underlying libraries (like Jinja2 and PyYAML) are kept up to date to prevent known exploit vectors.
