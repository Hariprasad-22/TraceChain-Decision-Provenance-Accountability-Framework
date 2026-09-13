# TraceChain
### Decision Provenance & Accountability Framework for Agentic AI

**TraceChain** is a domain-agnostic accountability layer for autonomous, multi-agent AI systems. It captures the context behind agent decisions, links evidence and execution history, evaluates accountability risk, and enables post-hoc decision reconstruction and audit.

> **The agents make the decisions. TraceChain makes those decisions traceable, explainable, and auditable.**

---

## Why TraceChain?

As AI systems become more autonomous, organizations need more than a final answer. They need to know:

- **WHO** contributed to the decision?
- **WHY** was the decision made?
- **WHAT** evidence and policies supported it?
- **HOW** risky or accountable was the decision?
- **CAN** the complete decision history be reconstructed later?

Traditional application logs are often not structured around the decision itself. TraceChain turns each meaningful agent execution into a structured, linked provenance record.

---

## Problem

In a multi-agent AI workflow, several specialized agents may contribute to a single consequential decision. Without a standardized provenance layer, it can be difficult to:

- identify the responsible agent or execution,
- understand which rule, model, or evidence influenced the result,
- reconstruct the chain of decisions after the event,
- assess accountability risk,
- prepare evidence for audits and governance processes.

This creates regulatory exposure, unclear responsibility, investigation effort, and hesitation around scaling agentic AI.

---

## Our Solution

TraceChain adds an **accountability and provenance plane** around existing agentic workflows rather than replacing the agents themselves.

### Core capabilities

**Decision Provenance**
- Captures inputs, outputs, timestamps, agent identity, and execution relationships.
- Links parent/child executions across a multi-agent chain.
- Preserves rule and model metadata used during execution.

**Evidence Lineage**
- Associates decisions with supporting documents, references, retrieved policies, and tool outputs.
- Makes the evidence behind a decision discoverable.

**Accountability Scoring**
- Evaluates decision accountability using dimensions such as:
  - Impact
  - Irreversibility
  - Explainability
- Produces an accountability/risk signal to help identify decisions that need greater scrutiny.

**Tamper-Evident Traceability**
- Uses hashes and linked records to strengthen the integrity of the decision history.
- Supports trustworthy post-hoc reconstruction of the decision chain.

**Audit & Governance**
- Provides a structured audit trail across the agent workflow.
- Supports governance and compliance mapping for frameworks such as the EU AI Act and NIST AI RMF.

---

## Demonstration Use Case: Personal Loan Approval

TraceChain is demonstrated using a **multi-agent personal loan approval workflow**.

### Specialized agents

| Agent | Responsibility |
|---|---|
| **Aadhaar Verification Agent** | Identity/document verification |
| **CIBIL Credit Agent** | Credit report and credit-risk assessment |
| **Payslip Income Agent** | Income and payslip verification |
| **Bank Statement Analysis Agent** | Cash-flow, transaction, and financial-behavior analysis |

A central orchestrator coordinates these agents, collects their outputs, and applies the final decision logic.

### Why loan approval?

Loan approval is a useful high-stakes demonstration because the final outcome can depend on multiple independent checks and supporting documents. The important contribution of TraceChain is not the loan workflow itself; it is the **ability to trace and reconstruct how the multi-agent decision was produced**.

---

## Generic Agent Workflow

Each specialized agent follows a controlled processing flow:

```text
Input
  ↓
Guardrail Validation
  ↓
Field / Signal Extraction
  ↓
Knowledge Retrieval
  ↓
LLM Reasoning
  ↓
Structured Output
  ↓
TraceChain Record
```

### Controlled AI principle

> **The LLM explains. Rules control.**

Guardrails and deterministic rules constrain the workflow, relevant knowledge is retrieved for context, and the LLM produces reasoning and a structured result rather than acting as an unrestricted decision-maker.

---

## System Architecture

TraceChain is structured as a layered architecture in which the application and API route requests into a LangGraph-based orchestrator. The orchestrator coordinates the four specialized verification agents, while the same controlled execution pattern is applied inside every agent.

![TraceChain System Architecture](tracechain-system-architecture.png)

### Architecture flow

```text
Browser
   ↓
Chatbot UI (React + Vite)
   ↓
API Layer (FastAPI)
   ↓
Orchestrator (LangGraph)
   ├── Aadhaar Verification Agent
   ├── CIBIL Credit Agent
   ├── Payslip Income Verification Agent
   └── Bank Statement Analysis Agent
   ↓
PostgreSQL
   ↓
Traceable response + audit trail
```

### Inside every agent

Every specialized agent follows the same controlled reasoning pattern:

```text
Input
  ↓
Guardrails
  ↓
Rule Engine
  ↓
Knowledge Retrieval
  ↓
LLM Reasoning
  ↓
Structured Output
  ↓
TraceChain Record
```

The purpose of this shared pattern is consistency across heterogeneous agents. Guardrails validate the request and data, the rule engine enforces deterministic policy, knowledge retrieval supplies relevant domain guidance, and the LLM generates contextual reasoning. The final structured output is captured as a traceable execution record.

> **The LLM explains. Rules control. TraceChain records.**

This separation makes the architecture modular, easier to extend to new agents, and suitable for adding provenance and accountability without rewriting the core decision logic of each agent.

---

## What Gets Recorded?

A TraceChain record can capture information such as:

```text
Application / Orchestration ID
Execution ID
Agent ID
Parent Execution ID
Input / Output
Decision
Reasoning
Confidence
Rule / Rule Version
Model / Model Version
Evidence References
Timestamp
Input Hash
Output Hash
Record Hash
Accountability Score
```

This transforms a simple log entry into a **decision-centered provenance record**.

---

## Example Trace

A simplified end-to-end trace might look like:

```text
Loan Application
      ↓
Orchestrator
      ↓
Aadhaar Agent
      └── Identity result + evidence
      ↓
CIBIL Agent
      └── Credit result + evidence
      ↓
Payslip Agent
      └── Income result + evidence
      ↓
Bank Statement Agent
      └── Financial result + evidence
      ↓
Orchestrator Decision Logic
      ↓
Final Decision
      ↓
Accountability Score
      ↓
Provenance / Audit Record
```

The same structure can be used to answer:

**Who acted? → What did they use? → Why did they decide? → What evidence supported it? → What was the final outcome?**

---

## Repository Structure

```text
TraceChain-Decision-Provenance-Accountability-Framework/
│
├── agents/
│   ├── aadhar/
│   ├── cibil/
│   ├── payslip/
│   └── bank_statement/
│
├── orchestrator/
├── schemas/
│
├── backend/
│   ├── database/
│   ├── models/
│   └── services/
│
├── frontend/
│
├── data/
│   ├── sample/
│   └── results/
│       ├── aadhaar/
│       ├── cibil/
│       ├── payslip/
│       ├── bank_statement/
│       └── end_to_end/
│
├── docs/
│   ├── architecture/
│   ├── agent_contracts/
│   └── demo/
│
├── tests/
│   ├── integration/
│   └── end_to_end/
│
└── examples/
```

---

## Key Design Principles

### 1. Agent-agnostic
TraceChain is designed around a common provenance contract, so different specialized agents can participate in the same trace.

### 2. Domain-agnostic
The same accountability model can be applied beyond banking, for example to healthcare, manufacturing, insurance, and other high-impact agentic workflows.

### 3. Non-intrusive
TraceChain is intended as an observability/governance layer around existing agent logic rather than a replacement for the agents.

### 4. Evidence-first
Important decisions should retain the evidence and policy context that supports them.

### 5. Auditable by design
Traceability and accountability are captured during execution instead of being reconstructed manually after an incident.

---

## Scalability

TraceChain uses a **schema-driven approach** so that new agent types, domains, and policy packs can be added without redesigning the entire framework.

The same architecture can scale from:

```text
One workflow
   ↓
Multiple agentic workflows
   ↓
Multiple business processes
   ↓
Enterprise-wide agent governance
```

Potential domains include:

- Banking
- Healthcare
- Manufacturing
- Insurance
- Supply Chain

The framework remains the same; the domain-specific agents, policies, and evidence sources can change.

---

## Security & Governance

The prototype architecture includes mechanisms relevant to enterprise AI governance, including:

- PII masking
- structured execution logging
- role-aware access patterns
- tamper-evident / hash-linked provenance
- evidence traceability
- accountability scoring

TraceChain is designed to **support** governance activities aligned with the **EU AI Act** and **NIST AI RMF** around traceability, documentation, risk management, oversight, and accountability.

> TraceChain should not be interpreted as a standalone certification of legal or regulatory compliance.

---

## Prototype & Data

The project is a capstone prototype and uses **synthetic / scenario-based data** for demonstration and testing. No production customer data is required for the prototype.

Local/generated artifacts such as virtual environments, caches, local ChromaDB stores, and large datasets should not be committed to the repository unless explicitly required.

---

## Tech Stack

The project uses an open-source-oriented stack including:

- **Python**
- **FastAPI**
- **React + Vite**
- **LangGraph**
- **PostgreSQL**
- **ChromaDB**
- **LLM endpoints**
- **RAG / vector retrieval**
- **Hash-based provenance**
- **Dashboard / audit interface**

---

## Expected Value

TraceChain is intended to help organizations:

- reduce investigation effort,
- improve accountability across multi-agent workflows,
- reduce governance risk during AI scale-up,
- speed up decision reconstruction,
- improve audit readiness,
- build trust in autonomous AI systems.

The goal is to move from:

> **“The AI made this decision.”**

to:

> **“Here is exactly how this decision was produced, what supported it, which agents contributed, and how the decision can be reconstructed.”**

---

## Current Prototype Status

TraceChain is being developed as a working capstone prototype with:

- four specialized loan-verification agents,
- an orchestration layer,
- structured execution/provenance records,
- accountability scoring,
- evidence and policy retrieval,
- a dashboard/audit interface,
- end-to-end decision tracing.

---

## Team

**Team ZenX**  
**VNR Vignana Jyothi Institute of Engineering and Technology**

- V. Srinidhi
- Greeshma Reddy Putha
- Hari Prasad Errolla
- Palla Nikhila
- Gunaganti Tejaswi

---

## Project Positioning

> **Others help AI make decisions smarter. TraceChain helps organizations prove how AI decisions were made.**
