# Student Services Assistant — Solution Accelerator Implementation Plan

> **Purpose:** Provide 24/7, consistent first-line support for common student questions
> (admissions, financial aid, registration, housing, IT basics), reducing wait times and
> call-center load — built on **Azure AI Foundry**, the **Microsoft Agent Framework**, and
> supporting Azure services.

This document is the master plan. It captures scope, architecture, a phased delivery roadmap,
cost/sizing tiers, and governance — all derived from the solution brief.

---

## 1. Product Overview

| Aspect | Definition |
|--------|------------|
| **Purpose** | 24/7 consistent first-line support for common student questions; reduce wait times and call-center load. |
| **Primary users** | Students and prospective students. Staff benefit via deflection of routine inquiries and better routing/triage. |
| **Core scope** | FAQ-style Q&A, guided workflows (forms, links, next steps), escalation to humans, analytics on top issues and resolution rates. |
| **Agentic extensions** | Multi-step tasks that call systems/tools ("check my application status," "reset my password," "book an advising appointment") where the university enables secure integrations and approvals. |
| **Out of scope** | Final decisions (admissions/aid), authoritative policy interpretation, or actions without explicit permissions/guardrails. Hand off when confidence is low. |
| **Channel scope** | Web chat first; add SMS / Teams / mobile only if needed (each channel increases licensing and support costs). |
| **Data boundaries** | Retrieval only from approved content (web pages, knowledge base, SIS-approved data) with role-based access. Log and monitor for privacy / **FERPA** considerations. |

### Key cost drivers
1. Interaction volume
2. Number of departments and content owners
3. Level of personalization (SIS / CRM integrations)
4. Human handoff + contact center integration
5. Security posture and monitoring

---

## 2. Capability Map (Scope → Feature)

```mermaid
mindmap
  root((Student Services<br/>Assistant))
    Core
      FAQ Q&A
      Guided workflows
        Forms
        Links
        Next steps
      Human escalation
      Analytics
        Top issues
        Resolution rates
    Agentic Extensions
      Check application status
      Reset password
      Book advising appointment
      Approvals & guardrails
    Guardrails
      Confidence-based handoff
      No final decisions
      No policy interpretation
      Permission-gated actions
    Channels
      Web chat first
      SMS / Teams / Mobile later
    Data Boundaries
      Approved web content
      Knowledge base
      SIS-approved data
      Role-based access
      FERPA logging & monitoring
```

---

## 3. Target Architecture

### 3.1 Logical architecture

```mermaid
flowchart TB
    subgraph Channels["Channels"]
        Web["Web Chat (Phase 1)"]
        Teams["Teams / SMS / Mobile (Phase 5)"]
    end

    subgraph Front["Security & Guardrails"]
        Entra["Microsoft Entra ID<br/>(SSO, RBAC, roles)"]
        CS["Azure AI Content Safety<br/>(input/output guardrails)"]
    end

    subgraph Foundry["Azure AI Foundry"]
        Router["Triage / Router Agent"]
        FAQ["Knowledge (RAG) Agent"]
        Actions["Agentic Action Agents"]
        Handoff["Escalation / Handoff Agent"]
        Models["Model deployments<br/>(chat + embeddings)"]
    end

    subgraph Framework["Microsoft Agent Framework (orchestration)"]
        Orchestrator["Multi-agent orchestrator<br/>+ tool calling + memory"]
    end

    subgraph Knowledge["Knowledge & Data"]
        Search["Azure AI Search<br/>(vector + hybrid index)"]
        Blob["Azure Blob Storage<br/>(approved content)"]
        Cosmos["Azure Cosmos DB<br/>(conversation state)"]
    end

    subgraph MCP["MCP Tool Layer (Model Context Protocol servers)"]
        McpSIS["SIS/CRM MCP server<br/>(application status)"]
        McpIdP["Identity MCP server<br/>(password reset)"]
        McpSched["Scheduling MCP server<br/>(advising appointment)"]
        McpKB["Knowledge MCP server<br/>(AI Search retrieval)"]
    end

    subgraph Integrations["Backend systems of record"]
        SIS["SIS / CRM"]
        IdP["Identity provider"]
        Sched["Advising scheduler"]
        Contact["Contact center / live agent"]
    end

    subgraph Observability["Observability & Governance"]
        AppIns["Application Insights"]
        Monitor["Azure Monitor / Log Analytics"]
        Eval["Foundry Evaluations<br/>(quality + continuous eval)"]
    end

    Web --> Entra
    Teams --> Entra
    Entra --> CS
    CS --> Orchestrator
    Orchestrator --> Router
    Router --> FAQ
    Router --> Actions
    Router --> Handoff
    FAQ --> McpKB
    McpKB --> Search
    Search --> Blob
    Actions --> McpSIS
    Actions --> McpIdP
    Actions --> McpSched
    McpSIS --> SIS
    McpIdP --> IdP
    McpSched --> Sched
    Handoff --> Contact
    Orchestrator --> Cosmos
    Foundry --> Models
    Orchestrator --> AppIns
    AppIns --> Monitor
    Eval --> Foundry
```

### 3.2 Multi-agent design (Microsoft Agent Framework + Foundry)

```mermaid
flowchart LR
    User(["Student"]) --> Triage

    Triage["🧭 Triage/Router Agent<br/>intent + confidence"]
    Triage -->|"informational"| KB["📚 Knowledge Agent<br/>(RAG over AI Search)"]
    Triage -->|"action request"| Act["⚙️ Action Agents"]
    Triage -->|"low confidence /<br/>out of scope"| HO["🙋 Handoff Agent"]

    subgraph Act["⚙️ Agentic Action Agents"]
        A1["Application Status"]
        A2["Password Reset"]
        A3["Appointment Booking"]
    end

    A1 -->|"guardrail:<br/>auth + approval"| Tools[("MCP servers<br/>(scoped tools)")]
    A2 --> Tools
    A3 --> Tools
    HO --> Live(["Human / Contact Center"])
    KB --> User
    Act --> User
```

### 3.3 Request/guardrail sequence

```mermaid
sequenceDiagram
    participant S as Student
    participant W as Web Chat
    participant G as Entra + Content Safety
    participant O as Agent Framework Orchestrator
    participant R as Triage Agent
    participant K as Knowledge Agent
    participant A as Action Agent
    participant M as MCP server
    participant H as Handoff

    S->>W: Ask question
    W->>G: Authenticated request
    G->>G: Input safety + role check (FERPA)
    G->>O: Sanitized message + identity
    O->>R: Classify intent + confidence
    alt High confidence FAQ
        R->>K: Retrieve via Knowledge MCP tool
        K-->>S: Grounded answer + citations
    else Permitted action (authorized)
        R->>A: Execute multi-step task
        A->>A: Confirm permission / approval
        A->>M: Call scoped MCP tool (on-behalf-of user)
        M-->>A: Tool result
        A-->>S: Result (status / booking / reset)
    else Low confidence / out of scope
        R->>H: Escalate
        H-->>S: Warm handoff to human
    end
    O->>O: Log interaction + metrics
```

---

## 4. Azure Service Mapping

| Concern | Azure Service | Notes |
|---------|---------------|-------|
| Agent registration & hosting | **Azure AI Foundry** (hosted agents, projects) | Register Triage, Knowledge, Action, Handoff agents |
| Agent orchestration & tool calling | **Microsoft Agent Framework** | Multi-agent routing, memory, tool invocation |
| Chat & embedding models | **Foundry model deployments** | e.g. GPT-class chat + embedding model |
| Knowledge retrieval (RAG) | **Azure AI Search** | Vector + hybrid index over approved content |
| Approved content store | **Azure Blob Storage** | Web pages, KB docs, policy PDFs |
| Conversation state / memory | **Azure Cosmos DB** | Threads, session context |
| Secure tool integration | **MCP servers on Azure Container Apps** | Model Context Protocol servers expose scoped tools (SIS/CRM, IdP, scheduler, knowledge); per-tool auth, Entra on-behalf-of |
| Identity, SSO, RBAC | **Microsoft Entra ID** | Role-based access, per-department scoping, on-behalf-of token flow to MCP tools |
| Guardrails | **Azure AI Content Safety** | Input/output filtering, jailbreak detection |
| Channels | **Azure Bot Service / Web Chat**, later Teams/SMS | Web chat first |
| Telemetry & analytics | **Application Insights + Azure Monitor / Log Analytics** | Top issues, resolution rate, FERPA audit logs |
| Quality & continuous eval | **Foundry Evaluations** | Batch + continuous production evaluation |
| Secrets / keys | **Azure Key Vault** | Integration credentials, API keys |
| IaC & CI/CD | **azd (Azure Developer CLI) + Bicep** | Reproducible provisioning and deployment |

---
