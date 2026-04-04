# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |
| 0.0.5   | Yes       |
| < 0.0.5 | No        |

Only the current release receives security updates.

## Reporting a Vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Report vulnerabilities by email to chris@nationalstandardconsulting.com.
Include a description of the issue, steps to reproduce, and potential impact.

You can expect an acknowledgment within 48 hours and a status update within
7 days. If the vulnerability is accepted, a fix will be prioritized for the
next release. If declined, you will receive an explanation.

Wilson does not handle user authentication, store personal data, or process
payment information. The primary security concerns are:

- CourtListener API token exposure (stored in .env, gitignored)
- Ollama endpoint exposure if bound to a public interface
- Malformed document uploads triggering unexpected parser behavior

Please note Wilson is an open-source project maintained by a single developer.
Response times reflect that reality.
