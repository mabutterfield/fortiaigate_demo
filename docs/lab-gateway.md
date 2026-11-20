# Lab Login Gateway

The lab login gateway puts a sign-in in front of the student chatbot so many
students can share one URL, each using only their own FortiAIGate virtual keys
and Traffic Log entries. It extends the existing nginx HTTPS gateway
(`chatbot/https-gateway`, deployed by `deploy_demo_https_gateway.yml`) with an
auth sidecar; it does not use the retired `ingress-nginx` controller.

## How It Works

```
browser ──► nginx (HTTP 30081 / HTTPS 30444) ──auth_request──► lab-auth sidecar
                │                                                 │ FAIG login,
                │  X-Lab-* signed identity headers                │ sessions,
                ▼                                                 ▼ FAIG sessions
          chatbot route upstream                        FortiAIGate API (in-cluster)
```

- Students and FortiAIGate super admins sign in with their FortiAIGate email
  and password. A student is an account that is Workspace Admin of a
  `studentNN_workspace`; other accounts are refused.
- HTTPS only (Change 2026-11-20, owner: HTTPS is mandatory for browser
  routes): the plain HTTP port (30081) answers every request with a 301 to the
  same path and query on HTTPS 30444; it no longer serves any page. A redirect
  cannot protect anything already sent over HTTP, so give students the HTTPS
  address. Other HTTP listeners (FAIG ingress, optional apps) are part of the
  deployment and are handled there. The session cookie is `Secure`, `HttpOnly` and
  `SameSite=Lax`, so after sign-in students use HTTPS.
- nginx asks the sidecar (`/_lab/verify`) about every request on routes with
  `auth: true`. A valid session returns HMAC-signed `X-Lab-User`,
  `X-Lab-Student`, `X-Lab-Role`, `X-Lab-Workspace-Id`, `X-Lab-Ts` and
  `X-Lab-Signature` headers, which nginx forwards upstream after overwriting
  any client-supplied values. Upstreams verify the signature with the shared
  key in the `lab-gateway-signing` Secret (key `hmac-key`); signatures are
  valid for five minutes.
- The sidecar keeps each student's FortiAIGate session server-side. Upstream
  apps read that student's own Traffic Log entries through
  `/_lab/internal/traffic-logs` on the cluster-internal
  `demo-https-gateway-auth:8090` Service by forwarding the signed headers;
  `?key=&since=` filters the list and `?uuid=` returns one entry. The
  FortiAIGate session never reaches the browser or the upstream app.
- Sessions live in the sidecar's memory: up to 8 hours, 25 minutes idle, and
  they end early if FortiAIGate rejects the stored session. Restarting the
  gateway signs everyone out. Any browser request through the gateway counts as
  activity. The 25-minute default sits just under FortiAIGate's own idle
  timeout (25-30 minutes, measured 2026-11-20; using the session resets it), so
  users see the sign-in page instead of FortiAIGate errors.
- Fallback mode (`lab_gateway_mode: fallback`) checks salted PBKDF2 hashes from
  the Secret named by `lab_gateway_fallback_secret_name` (default
  `lab-gateway-fallback`, key `fallback.json`, created empty once) instead of
  FortiAIGate; Traffic Log views are unavailable in that mode. Admin password
  resets from the lab chatbot's Admin tab write the matching hash there, so
  switching modes keeps the same passwords. A new hash reaches the sidecar
  within about a minute (Kubernetes syncs mounted Secrets periodically). The
  sidecar's service account may only `get` and `patch` that Secret.
- Admin-only internal calls (signed `admin` identity plus the admin's live
  FortiAIGate session in the sidecar): `GET /_lab/internal/admin/students`
  lists the lab students from `/api/v1/admin/users`, and
  `POST /_lab/internal/admin/password` (`{"student", "password"}`) checks
  strength with `/api/v1/me/password/strength`, resets the FortiAIGate
  password with `/api/v1/admin/users/{id}/password/reset`, and stores the
  fallback hash. Passwords are never logged.

The chatbot route serves the [student lab chatbot](lab-chatbot.md). With
`lab_gateway_chatbot_placeholder: true` (the default when
`lab_chatbot_enabled: false`) it serves the sidecar's "who am I" page instead,
showing the signed-in account, student, workspace and the latest Traffic Log
rows read with the student's FortiAIGate session.

## Settings

Repo defaults are in `ansible/roles/demo_https_gateway/defaults/main.yml`:

```yaml
lab_gateway_enabled: true
lab_gateway_http_port: "{{ demo_chatbot_http_port | default(30081) }}"
lab_gateway_auth_port: 8090
lab_gateway_faig_url: "https://ingress-nginx-controller.ingress-nginx.svc.cluster.local"
lab_gateway_faig_verify_tls: false
lab_gateway_max_session_hours: 8
lab_gateway_idle_minutes: 25
lab_gateway_auto_approve_seconds: 60
lab_gateway_mode: faig
lab_gateway_signing_secret_name: lab-gateway-signing
lab_gateway_fallback_secret_name: lab-gateway-fallback
lab_gateway_chatbot_placeholder: "{{ not (lab_chatbot_enabled | default(true) | bool) }}"
```

The gateway now uses the nginx stable line `1.30-alpine`. (The 8.0.1 chatbot,
which also used NodePort 30081, was removed from the 8.0.2 branch.)

The sign-in sidecar also runs [auto-approval](lab-management.md#auto-approval)
(`/_lab/internal/admin/auto-approve`, Lab Management caller only).

## Validation

Observed on 2026-11-18 (Ohio lab): unauthenticated HTTP and HTTPS requests
redirect to sign-in; HTTP sign-in redirects to HTTPS; forged identity headers
without a session are ignored; a wrong password returns 401; student02 signs
in and sees `student02_workspace` with its latest Traffic Log rows; the super
admin maps to role `admin`; logout ends the session; the internal log API
returns only student02's entries (including a single entry's prompt, response
and violations) for correctly signed headers and 403 for tampered or missing
ones. Unit tests: `tests/test_lab_auth.py`.
