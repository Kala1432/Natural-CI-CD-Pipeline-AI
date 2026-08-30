# Authentication Architecture - CI/CD Pipeliner

This document details the authentication and authorization flows used within the CI/CD Pipeliner platform.

## 1. Local Authentication (Email/Password)

### Registration
1.  User submits email and password.
2.  Backend hashes the password using Argon2id/bcrypt.
3.  A new `User` record is created.
4.  If email verification is enabled, an OTP is generated, hashed, stored in the database, and emailed to the user.

### Login
1.  User submits email and password.
2.  Backend retrieves the user and verifies the password hash.
3.  Upon success, a JSON Web Token (JWT) is generated.
4.  The JWT is returned to the client in an `HttpOnly`, `Secure` cookie to prevent XSS attacks.

## 2. OAuth Authentication (GitHub & Google)

### Flow
1.  User clicks "Login with GitHub/Google".
2.  Frontend requests an authorization URL from the backend. The backend generates a secure `state` parameter and stores it in the session/Redis.
3.  Frontend redirects the user to the OAuth provider.
4.  User authorizes the application and is redirected back to the frontend with an authorization `code` and the `state`.
5.  Frontend sends the `code` and `state` to the backend.
6.  Backend verifies the `state` to prevent CSRF.
7.  Backend exchanges the `code` for an access token.
8.  Backend fetches the user's profile from the provider.
9.  Account Linking:
    *   If a user with that provider ID exists, log them in.
    *   If a user with that email exists but a different provider, link the accounts securely (prompting for password if necessary, based on security policy).
    *   Otherwise, create a new `User` record.
10. Backend issues an `HttpOnly` JWT cookie.

## 3. GitHub App Integration (Repository Access)

To interact with user repositories, CI/CD Pipeliner uses a GitHub App integration rather than relying solely on OAuth personal access tokens.
1.  User clicks "Install GitHub App".
2.  User is redirected to GitHub to install the app on selected repositories.
3.  GitHub redirects back with an `installation_id`.
4.  Backend stores the `installation_id` associated with the `GithubConnection`.
5.  When backend services need to access the GitHub API (e.g., fetching a file tree, opening a PR), they generate a short-lived, repository-scoped Installation Access Token dynamically using the GitHub App's private key.

## 4. Role-Based Access Control (RBAC)

*   **User Role:** Standard access. Users can only access resources (Projects, Pipelines, Deployments) where `resource.user_id == current_user.id`.
*   **Admin Role:** Elevated access. Admins can access the `/api/admin/*` endpoints to view global analytics, manage users, and view system-wide incidents. Admins do *not* have access to view plaintext secrets or user passwords.
