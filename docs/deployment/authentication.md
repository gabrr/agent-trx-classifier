# Authentication setup

Supabase Auth manages user sign-in and client sessions. The client sends its access token to FastAPI in `Authorization: Bearer <token>`. FastAPI verifies it and checks job ownership. [Security and identity](../trx-system-design/03-security-and-identity.md) explains the boundaries.

## Prerequisites and settings

Apply the [database migration](supabase.md) for jobs and user profiles. Backend authentication requires:

| Setting | Purpose |
| --- | --- |
| `AUTH_SUPABASE_URL` | Supabase project's HTTPS URL. |
| `AUTH_SUPABASE_PUBLISHABLE_KEY` | Project's publishable API key. |

Use HTTPS in production. Local Supabase can use a localhost HTTP URL. Google service identities are configured separately in [Cloud Tasks](cloud-tasks.md).

## Google and Supabase configuration

1. Create Google OAuth client credentials and configure them in Supabase's Google provider settings.
2. Register the Supabase provider callback URL in Google using the value supplied by the project.
3. Allowlist the frontend login return URL in Supabase, including a separate local development URL.

The frontend handles the return from login through the Supabase SDK. The backend has no login or logout endpoint. [Google provider setup](https://supabase.com/docs/guides/auth/social-login/auth-google), [redirect allowlists](https://supabase.com/docs/guides/auth/redirect-urls)

## Frontend integration

Configure the frontend Supabase SDK with the project URL and publishable key for sign-in, client sessions and logout. Send the access token to FastAPI in the Authorization header.

With an initialized Supabase client:

```typescript
const { data: { session } } = await supabase.auth.getSession();
if (!session) throw new Error("Sign in required");

const response = await fetch("/auth/me", {
  headers: { Authorization: `Bearer ${session.access_token}` },
  credentials: "omit",
});
if (response.status === 401) throw new Error("Sign in again");
```

Proxy `/auth/me` and `/api/jobs` routes to FastAPI on the frontend host. Preserve Authorization headers and unbuffered streaming. Use `fetch` for authenticated event streams so requests can include the Authorization header. Internal routes are called directly by Google services.

## Verification and access

The adapter uses the SDK's `get_claims()` to verify signatures and expiry, then checks issuer, audience, authenticated role and user ID. Asymmetric signing keys are cached by the SDK; legacy symmetric tokens are validated through Supabase's Auth server. Only verified identity data is used to synchronize the application user profile.

The backend stores no user tokens or application login sessions. An open stream checks token expiry periodically and sends `session_expired` before closing. Supabase logout can leave an issued access token valid until expiry; client logout must also close open streams. Token claims do not replace application ownership checks or automatically configure RLS for a direct database connection.

Before deployment, verify:

- A real Supabase token reaches `/auth/me` and returns the expected identity.
- Missing, malformed, expired, forged and wrong-project tokens are rejected with 401.
- Users cannot read, retry or stream another user's jobs.
- Missing provider configuration or temporary provider failures return 503.
- The frontend handles sign-in, renewal, logout and expired streams through the deployed proxy.

Implementation: [authentication service](../../src/services/authentication/), [Supabase adapter](../../src/services/authentication/supabase.py) and [auth routes](../../src/api/authentication.py). [SDK verification](https://supabase.com/docs/reference/python/auth-getclaims), [logout behavior](https://supabase.com/docs/guides/auth/signout)
