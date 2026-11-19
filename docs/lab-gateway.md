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
- The plain HTTP port stays available, but the login page and form always
  redirect to HTTPS. The session cookie is `Secure`, `HttpOnly` and
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
- Sessions live in the sidecar's memory: up to 8 hours, 2 hours idle, and they
  end early if FortiAIGate rejects the stored session. Restarting the gateway
  signs everyone out.
- Fallback mode (`lab_gateway_mode: fallback`) checks salted PBKDF2 hashes from
  the Secret named by `lab_gateway_fallback_secret_name` (key `fallback.json`)
  instead of FortiAIGate; Traffic Log views are unavailable in that mode. The
  admin portal that will manage these passwords is not built yet.

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
lab_gateway_idle_minutes: 120
lab_gateway_mode: faig
lab_gateway_signing_secret_name: lab-gateway-signing
lab_gateway_fallback_secret_name: ""
lab_gateway_chatbot_placeholder: "{{ not (lab_chatbot_enabled | default(true) | bool) }}"
```

The gateway now uses the nginx stable line `1.30-alpine`. Because it takes HTTP
port 30081, do not deploy the 8.0.1 chatbot (which also uses NodePort 30081)
in the same cluster.

## Validation

Observed on 2026-11-18 (Ohio lab): unauthenticated HTTP and HTTPS requests
redirect to sign-in; HTTP sign-in redirects to HTTPS; forged identity headers
without a session are ignored; a wrong password returns 401; student02 signs
in and sees `student02_workspace` with its latest Traffic Log rows; the super
admin maps to role `admin`; logout ends the session; the internal log API
returns only student02's entries (including a single entry's prompt, response
and violations) for correctly signed headers and 403 for tampered or missing
ones. Unit tests: `tests/test_lab_auth.py`.
