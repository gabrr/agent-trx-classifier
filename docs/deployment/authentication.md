# Login and authentication

Status: recommendation for review; no authentication has been implemented.
[Interactive walkthrough](../../../../docs/trx-classifier-authentication.html)
shows the overview, request sequences, forms, and security decisions.

## Recommended approach

Use **Supabase Auth** for people (Google sign-in first; email/password optional).
Use **Google service identities** for Cloud Tasks and other Cloud Run backends.
FastAPI uses separate authentication guards for those two kinds of callers.

For the browser, add a custom server-managed session in FastAPI. Route `/auth`
and `/api` through the same HTTPS origin as the frontend. Supabase access and
refresh tokens stay encrypted on the server. The browser receives a random
opaque `__Host-trx-session` cookie: Secure, HttpOnly, SameSite=Lax, Path=/,
with no Domain attribute. Store its hash, verified user ID, expiry, and
revocation state in private PostgreSQL tables.

This adds session storage, encryption-key management, and coordinated refresh.
It also requires same-origin hosting/proxy configuration. It makes native SSE
cookie authentication straightforward and reduces exposure of provider tokens
to browser JavaScript. HttpOnly does not prevent malicious scripts from acting
as the user: retain CSP, safe rendering, and dependency hygiene.
This is a custom backend session design, not the default Supabase browser SDK.

## Provider setup

1. Choose the application's HTTPS origin, for example `https://app.example.com`.
   Serve or proxy `/auth` and `/api` to FastAPI under that origin. Preserve cookies,
   redirects, upload limits, and unbuffered SSE. A separate `run.app` URL alone
   does not establish same-origin browser routing. The frontend hosting/proxy
   configuration must be completed before testing production cookies.
2. In Google Auth Platform **console**, configure the app name, audience/test
   users, and basic identity scopes; create a **Web application** OAuth client.
   Configure the app origin and add the Supabase Google-provider callback URL.
3. In Supabase **dashboard → Authentication → Google provider**, enable Google
   and enter that OAuth client ID/secret. Copy its callback URL into Google;
   the usual form is `https://PROJECT_REF.supabase.co/auth/v1/callback`.
4. In Supabase **URL Configuration**, set Site URL to the app origin and allow
   the exact app callback, `https://app.example.com/auth/callback`. FastAPI passes
   this fixed URL as the PKCE redirect destination. Avoid production wildcards.
5. For a new project, configure asymmetric JWT signing and verify through JWKS.
   Copy the project's publishable key. The Google client secret stays in Supabase;
   FastAPI does not need it or the Supabase service-role key for ordinary login.

| Redirect | Where configured | Purpose |
| --- | --- | --- |
| Google → Supabase `/auth/v1/callback` | Google OAuth client | Supabase finishes Google sign-in. |
| Supabase → app `/auth/callback` | Supabase redirect allowlist + FastAPI | FastAPI exchanges the code and sets our cookie. |

Use separate development URLs/client configuration when needed. Production
`__Host-` cookies require HTTPS; the standalone HTML is not a functioning login
client. Google OAuth registration needs the console; no CLI workaround is needed.
Supabase also exposes a management API, but dashboard setup is sufficient here.
Email/password remains optional: before enabling registration/recovery, configure
production SMTP, confirmation/recovery callbacks, rate limits, and generic errors.

## Runtime configuration

Add these proposed settings to the app configuration before deployment:

| Variable | Example / purpose |
| --- | --- |
| `APP_ORIGIN` | `https://app.example.com`; trusted fixed origin. |
| `AUTH_CALLBACK_URL` | App origin + `/auth/callback`. |
| `SUPABASE_URL` | `https://PROJECT_REF.supabase.co`. |
| `SUPABASE_PUBLISHABLE_KEY` | Project publishable key; ordinary configuration. |
| `SUPABASE_JWT_ISSUER` | Supabase URL + `/auth/v1`. |
| `SUPABASE_JWT_AUDIENCE` | `authenticated` for standard Supabase user tokens; verify project configuration. |
| `SUPABASE_JWKS_URL` | Supabase URL + `/auth/v1/.well-known/jwks.json`. |
| `AUTH_SESSION_TTL_SECONDS` | Initial candidate: `86400` (24 hours); enforce server-side. |
| `AUTH_LOGIN_ATTEMPT_TTL_SECONDS` | Initial candidate: `300` (5 minutes). |
| `TOKEN_ENCRYPTION_KEY` | Secret for authenticated encryption of provider tokens/PKCE verifiers. |

Prepare these shell variables for the Cloud Run command (replace placeholders):

```sh
export TRX_APP_ORIGIN="https://app.example.com"
export TRX_SUPABASE_URL="https://YOUR_PROJECT_REF.supabase.co"
export TRX_SUPABASE_PUBLISHABLE_KEY="YOUR_PROJECT_PUBLISHABLE_KEY"
```

Keep Google task settings separate: `TASK_AUDIENCE` and `TASK_CALLER_EMAIL`.
Prepare the values above locally, then [Cloud Run](cloud-run.md) maps them to the
runtime. These are proposed configuration names, not settings already implemented.

Create a fresh 32-byte, base64-encoded key directly in Secret Manager; the command
does not print it. Run with the bootstrap's `set -o pipefail` enabled.

```sh
python3 -c 'import base64, secrets, sys; sys.stdout.write(base64.b64encode(secrets.token_bytes(32)).decode())' |
  gcloud secrets create trx-token-encryption-key --replication-policy=automatic --data-file=-
```

Use a maintained authenticated-encryption library (for example AES-256-GCM),
unique nonces, and stored key-version metadata. Rotation must retain old key
versions until records are re-encrypted or expired; changing the secret alone
would make existing tokens unreadable. Restrict key access to the runtime identity.

## Implementation order

1. Configure Supabase Google OAuth and exact redirect URLs. Implement a
   short-lived, browser-bound, single-use PKCE login attempt and callback.
2. Verify Supabase signatures, issuer, audience, expiry, and user subject.
   Use request-specific auth clients. Encrypt tokens, rotate the session ID on
   login, serialize refresh per session, and enforce bounded session lifetimes.
3. Enforce exact Origin and session-bound CSRF checks on unsafe browser requests,
   including login and logout (use a pre-login CSRF session). Avoid wildcard
   credentialed CORS. Never place tokens in URLs or logs; auth responses use
   `Cache-Control: no-store`.
4. Derive job ownership from the verified session. Scope every job, result,
   file download, and SSE query to that owner. Keep session/job tables outside
   exposed Data API schemas; use scoped database roles. Direct SQL connections
   do not automatically acquire Supabase user RLS context.
5. For each job SSE stream, authenticate before registering/replaying events.
   Close at session expiry. Notify all backend processes on local revocation;
   recheck sessions after listener recovery and browser reconnect. Keep the
   existing durable `job_updates` flow without periodic progress polling.
6. Verify task OIDC separately: Google signature, issuer, expiry, exact audience,
   and the allowed verified service-account identity. Reject user credentials
   on internal routes. Task headers alone are not proof of identity.
7. Add abuse limits, server-side 30 MB batch checks, parser resource limits,
   and atomic job claims with fenced/idempotent result commits. A two-dispatch
   queue limit needs cancellation handling if processing outlives a dispatch.

Logout revokes the local server session immediately and closes its streams.
Authorized processing continues. Previously issued Supabase JWTs can remain
valid until expiry; provider-side revocation alone is not immediate local logout.
Check provider session validity on refresh, revoke locally when refresh fails,
and document that external revocations may have a detection delay.

Cloud Run remains publicly reachable for browser routes. FastAPI authenticates
routes because Cloud Run IAM covers the whole service. If another private Cloud
Run backend is added, use Google OIDC and narrowly scoped `run.invoker`; also
check which operations that service is authorized to perform.

## Configuration and launch checks

Configure Supabase URL, publishable key, expected JWT issuer/audience and JWKS;
app origin; fixed callback URL; session lifetime; and allowed task audience/caller.
Store database credentials and token-encryption keys in Secret Manager. The
Supabase service-role key is not needed for ordinary login; never expose it.
Email registration/reset requires production SMTP and abuse controls.

Before launch, verify cross-owner access denial, CSRF rejection, callback replay,
wrong task audience/service account, owner-checked/idempotent user retry,
concurrent refresh, logout across instances,
SSE expiry/recovery, and repeated task delivery. Forms in the HTML are fictional
examples and make no network requests.

Sources: [Supabase PKCE](https://supabase.com/docs/guides/auth/sessions/pkce-flow),
[Supabase sessions](https://supabase.com/docs/guides/auth/sessions),
[OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html),
[Google service identity](https://cloud.google.com/run/docs/authenticating/service-to-service).

[Google provider setup](https://supabase.com/docs/guides/auth/social-login/auth-google)
· [JWT verification](https://supabase.com/docs/guides/auth/jwts)
