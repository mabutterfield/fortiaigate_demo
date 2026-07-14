# FortiAIGate Demo Lab - LLM Request Flow

Path picks the transport/endpoint; Profile picks the LiteLLM alias. All profiles
end at the same Bedrock target - the selection only changes URL, header, and
model-name construction, and therefore what FAIG inspects.

```mermaid
flowchart TD
    UI["Chat UI (WebUI / chatbot)<br/><b>Step 1 - Path:</b> Direct LiteLLM | FAIG Static | FAIG Intelligent<br/><b>Step 2 - Profile:</b> pass-bedrock | demo-a | demo-b | demo-a-faig-be | demo-b-faig-be<br/><b>FAIG route:</b> passthrough | demo-a | demo-b | demo-a-faig-be | demo-b-faig-be"]

    RD["Direct request<br/>POST LiteLLM /v1/*<br/>body model = {profile}"]
    RS["Static request<br/>POST FAIG /v1/{profile}/*"]
    RI["Intelligent request<br/>POST FAIG /v1/intelligent/*<br/>no header: passthrough<br/>header x-faig-model-route: demo-a | demo-b"]

    FAIG["FortiAIGate (front)<br/>AI guard inspects user request<br/>(pre-injection view)"]
    LL["LiteLLM - alias = {profile}<br/>pre-call hook injects backend instructions"]
    FB["FortiAIGate (post-injection)<br/>URI rule /v1/passthrough/*<br/>AI guard inspects again"]
    LP["LiteLLM - alias = pass-bedrock<br/>(no injection - passthrough)"]
    BR["Amazon Bedrock"]

    UI -->|"Path = Direct LiteLLM"| RD
    UI -->|"Path = FAIG Static"| RS
    UI -->|"Path = FAIG Intelligent"| RI

    RD -->|"no inspection"| LL
    RS --> FAIG
    RI --> FAIG
    FAIG -->|"static: alias {profile}<br/>intelligent: header-selected demo-a / demo-b"| LL
    FAIG -.->|"intelligent default:<br/>no header"| LP

    LL -->|"profile = demo-a / demo-b"| BR
    LL -.->|"profile = *-faig-be"| FB
    FB -.->|"guard litellm-pass-bedrock<br/>model pass-bedrock"| LP
    LP -.-> BR

    classDef ui fill:#d5e8d4,stroke:#82b366,color:#000
    classDef req fill:#ffffff,stroke:#666666,color:#000
    classDef faig fill:#f8cecc,stroke:#b85450,color:#000
    classDef ll fill:#dae8fc,stroke:#6c8ebf,color:#000
    classDef br fill:#e1d5e7,stroke:#9673a6,color:#000

    class UI ui
    class RD,RS,RI req
    class FAIG,FB faig
    class LL,LP ll
    class BR br
```

Notes:

- Direct LiteLLM: model name in request body, FAIG never sees the request.
- FAIG Static: profile encoded in the URI path (`/v1/{profile}/*`).
- FAIG Intelligent: single URI `/v1/intelligent/*`; no route header uses
  `passthrough`, which maps to LiteLLM alias `pass-bedrock`; the
  `x-faig-model-route` header selects `demo-a` or `demo-b`.
  `*-faig-be` profiles apply to the static path.
- Dashed path applies only when profile = `*-faig-be`: LiteLLM injects
  instructions, then chains through FAIG `/v1/passthrough/*` so the guard sees
  the post-injection request. `/v1/passthrough/*` maps to `pass-bedrock` through
  the `litellm-pass-bedrock` guard/provider (never a `*-faig-be` alias, or the
  request loops).
- FAIG is reached via the in-cluster nginx ingress service; LiteLLM appends
  `/chat/completions` to configured base paths.
