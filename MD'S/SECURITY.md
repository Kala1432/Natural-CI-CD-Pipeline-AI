# Security Strategy & Hardening - CI/CD Pipeliner

This document outlines the security architecture and required hardening measures for the CI/CD Pipeliner platform.

## 1. Authentication & Identity Management
*   **Password Storage:** All passwords must be hashed using a computationally intensive algorithm (e.g., Argon2id or bcrypt). Plaintext passwords must never be logged, stored, or returned in API responses.
*   **Token Management:** JSON Web Tokens (JWT) must be stored in `HttpOnly`, `Secure`, `SameSite=Strict` cookies. Storing JWTs in `localStorage` or `sessionStorage` is strictly prohibited to prevent XSS exfiltration.
*   **OAuth Security:** OAuth implementations (GitHub, Google) must rigorously validate the `state` parameter to prevent CSRF attacks. Access tokens obtained via OAuth must be encrypted at rest in the database.
*   **Session Expiration:** Implement absolute session timeouts and idle timeouts. Support immediate session revocation.

## 2. Authorization & RBAC
*   **Role-Based Access Control:** API endpoints must explicitly check the user's role (e.g., `user`, `admin`). The Admin interface must be logically separated from the standard user interface.
*   **Resource Ownership:** Every API request accessing a specific resource (Project, Pipeline, Deployment) must verify that the requesting user owns that resource. Insecure Direct Object Reference (IDOR) vulnerabilities must be prevented through mandatory ownership checks.

## 3. Data Protection & Secrets Management
*   **Secrets Storage:** Hardcoded secrets in the repository are forbidden. Production secrets (Database passwords, API keys, AWS credentials, JWT signing keys) must be managed using a secure vault (e.g., AWS Secrets Manager, HashiCorp Vault) and injected at runtime.
*   **Data at Rest:** The PostgreSQL database and any S3 buckets containing sensitive logs or generated artifacts must be encrypted at rest (e.g., using AWS KMS).
*   **Data in Transit:** All communications between the client and server, and between internal services, must use TLS 1.2 or higher.

## 4. Input Validation & Protection Against Injection
*   **Repository URL Handling:** Users provide external GitHub URLs. The backend must strictly validate these URLs to prevent Server-Side Request Forgery (SSRF) and ensure the application only interacts with authorized GitHub endpoints.
*   **SQL Injection:** All database queries must use SQLAlchemy's parameterized queries or ORM methods. Raw SQL execution must be avoided or rigorously sanitized.
*   **Command Injection:** The generation of Dockerfiles and GitHub Actions YAML must use templating engines with strict escaping. User-provided data (e.g., repository names, branch names) must never be interpolated directly into shell commands.

## 5. Execution Sandboxing
*   **Untrusted Code:** CI/CD Pipeliner analyzes third-party repository code. This code must be treated as hostile.
*   **Isolation:** Never execute untrusted repository code directly on the application host. If code execution is required for analysis or validation, it must happen within a strongly isolated sandbox (e.g., gVisor, Firecracker microVMs) with no network access to internal services and strict resource limits (CPU/Memory).

## 6. Audit Logging
*   **Immutable Logs:** Critical actions (logins, password changes, role changes, GitHub OAuth connections, PR creations, deployments) must be logged immutably.
*   **Log Contents:** Logs must include the timestamp, user ID, IP address, action performed, and outcome (success/failure).
*   **Sensitive Data Scrubbing:** Audit logs must never contain passwords, API keys, OAuth tokens, or PII.

## 7. Web Application Security (Frontend & API)
*   **CORS:** Cross-Origin Resource Sharing must be strictly configured to only allow requests from the trusted frontend domain.
*   **Rate Limiting:** Implement rate limiting on all API endpoints, particularly authentication routes, to mitigate brute-force and DDoS attacks.
*   **Security Headers:** Nginx/Flask must enforce security headers, including Content-Security-Policy (CSP), Strict-Transport-Security (HSTS), X-Frame-Options, and X-Content-Type-Options.
