-- =====================================================================
-- TraceChain PostgreSQL Schema
-- Generated from: TraceChain_Column_Type_Worksheet.xlsx (updated)
--
-- Changes applied vs. original worksheet, based on real Aadhaar agent
-- test output (account_100001_to_100010_results.json):
--   1. user_id / application_id / orchestration_id / agent_id changed
--      from UUID -> VARCHAR to match the human-readable ID strategy
--      already in use ('100001', 'APP-100001', 'A001').
--   2. APPLICATIONS.status and AGENT_EXECUTIONS.status CHECK values
--      lowercased ('processing', 'completed') to match actual agent
--      output instead of the original Title Case.
--   3. AGENT_EXECUTIONS.input_hash is NOT a column here -- the agent
--      currently emits it, but it's dropped at insert time. Hashing is
--      the orchestrator's job, and it belongs solely on
--      PROVENANCE_RECORDS.
--   4. PROVENANCE_RECORDS deliberately has no input_data/output_data
--      columns (kept as a lean hash-chain table) -- the agent's JSON
--      includes them, but they're stripped before insert.
--   5. AGENT_DECISIONS.decision_timestamp is populated from the
--      agent's `decision.timestamp` field at insert time (name differs
--      in the JSON, not in the DB).
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ---------------------------------------------------------------------
-- USERS
-- ---------------------------------------------------------------------
CREATE TABLE USERS (
    user_id     VARCHAR(50)  PRIMARY KEY,          -- human-readable, e.g. '100001'
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- APPLICATIONS
-- ---------------------------------------------------------------------
CREATE TABLE APPLICATIONS (
    application_id    VARCHAR(50)     PRIMARY KEY,      -- e.g. 'APP-100001'
    user_id           VARCHAR(50)     NOT NULL REFERENCES USERS(user_id) ON DELETE RESTRICT,
    loan_amount       DECIMAL(15,2)   NOT NULL CHECK (loan_amount > 0),
    application_date  TIMESTAMPTZ     NOT NULL DEFAULT now(),
    status            VARCHAR(30)     NOT NULL CHECK (status IN ('processing','approved','rejected','under_review'))
);

-- ---------------------------------------------------------------------
-- AGENTS  (fixed catalog, 4 rows: KYC / Income / BankAnalysis / CreditScore)
-- ---------------------------------------------------------------------
CREATE TABLE AGENTS (
    agent_id     VARCHAR(10)  PRIMARY KEY,           -- e.g. 'A001'
    agent_name   VARCHAR(100) NOT NULL,
    agent_type   VARCHAR(30)  NOT NULL CHECK (agent_type IN ('KYC','Income','BankAnalysis','CreditScore')),
    description  TEXT,
    version      VARCHAR(20)  NOT NULL,
    status       VARCHAR(20)  NOT NULL CHECK (status IN ('Active','Deprecated','Disabled'))
);

-- ---------------------------------------------------------------------
-- ORCHESTRATIONS
-- ---------------------------------------------------------------------
CREATE TABLE ORCHESTRATIONS (
    orchestration_id      VARCHAR(50)  PRIMARY KEY,     -- currently == application_id until orchestrator assigns real IDs
    application_id        VARCHAR(50)  NOT NULL REFERENCES APPLICATIONS(application_id) ON DELETE RESTRICT,
    orchestrator_version  VARCHAR(20)  NOT NULL,
    scenario               VARCHAR(50),
    status                 VARCHAR(20)  NOT NULL CHECK (status IN ('InProgress','Completed','Failed','HaltedAtGate')),
    start_time             TIMESTAMPTZ  NOT NULL,
    end_time               TIMESTAMPTZ
);

-- ---------------------------------------------------------------------
-- AGENT_EXECUTIONS
-- ---------------------------------------------------------------------
CREATE TABLE AGENT_EXECUTIONS (
    execution_id         UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    orchestration_id     VARCHAR(50)   NOT NULL REFERENCES ORCHESTRATIONS(orchestration_id) ON DELETE RESTRICT,
    agent_id             VARCHAR(10)   NOT NULL REFERENCES AGENTS(agent_id) ON DELETE RESTRICT,
    parent_execution_id  UUID          REFERENCES AGENT_EXECUTIONS(execution_id) ON DELETE SET NULL,
    sequence_number      SMALLINT      NOT NULL CHECK (sequence_number BETWEEN 1 AND 4),
    input_data           JSONB         NOT NULL,
    output_data          JSONB         NOT NULL,
    model_id             VARCHAR(100)  NOT NULL,
    rule_id              VARCHAR(100),
    start_time           TIMESTAMPTZ   NOT NULL,
    end_time              TIMESTAMPTZ,
    status                VARCHAR(20)  NOT NULL CHECK (status IN ('completed','failed','inprogress'))
    -- NOTE: no input_hash column here by design -- see header comment.
);

-- ---------------------------------------------------------------------
-- AGENT_DECISIONS
-- ---------------------------------------------------------------------
CREATE TABLE AGENT_DECISIONS (
    decision_id         UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID           NOT NULL UNIQUE REFERENCES AGENT_EXECUTIONS(execution_id) ON DELETE RESTRICT,
    decision_output     VARCHAR(100)   NOT NULL,
    confidence_score    DECIMAL(5,4)   NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    reasoning            TEXT          NOT NULL,
    decision_timestamp   TIMESTAMPTZ   NOT NULL   -- populated from agent's `decision.timestamp` field
);

-- ---------------------------------------------------------------------
-- EVIDENCE
-- ---------------------------------------------------------------------
CREATE TABLE EVIDENCE (
    evidence_id          UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id         UUID           NOT NULL REFERENCES AGENT_EXECUTIONS(execution_id) ON DELETE RESTRICT,
    evidence_type        VARCHAR(50),
    source                VARCHAR(100)  NOT NULL,
    data_reference        TEXT,
    model_id              VARCHAR(100),
    document_reference     VARCHAR(255) NOT NULL,
    policy_id              VARCHAR(100),
    retrieval_score         DECIMAL(5,4) CHECK (retrieval_score BETWEEN 0 AND 1),
    timestamp                TIMESTAMPTZ NOT NULL
);

-- ---------------------------------------------------------------------
-- ACCOUNTABILITY_SCORES
-- ---------------------------------------------------------------------
CREATE TABLE ACCOUNTABILITY_SCORES (
    score_id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id             UUID          NOT NULL UNIQUE REFERENCES AGENT_EXECUTIONS(execution_id) ON DELETE RESTRICT,
    irreversibility_score    SMALLINT      NOT NULL CHECK (irreversibility_score BETWEEN 0 AND 10),  -- sent by agent
    impact_score             SMALLINT      NOT NULL CHECK (impact_score BETWEEN 0 AND 10),           -- sent by agent
    explainability_score     SMALLINT      NOT NULL CHECK (explainability_score BETWEEN 0 AND 10),   -- sent by agent
    composite_risk_score     DECIMAL(5,2)  NOT NULL,   -- computed by orchestrator: 0.35*impact + 0.40*irreversibility + 0.25*(10-explainability)
    risk_level               VARCHAR(20)   NOT NULL CHECK (risk_level IN ('Low','Medium','High','Critical')),  -- computed by orchestrator
    review_required           BOOLEAN      NOT NULL DEFAULT FALSE,  -- computed by orchestrator
    scoring_model_version     VARCHAR(20)  NOT NULL,
    calculated_at             TIMESTAMPTZ  NOT NULL
);

-- ---------------------------------------------------------------------
-- FINAL_DECISIONS
-- ---------------------------------------------------------------------
CREATE TABLE FINAL_DECISIONS (
    final_decision_id     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    orchestration_id      VARCHAR(50)   NOT NULL UNIQUE REFERENCES ORCHESTRATIONS(orchestration_id) ON DELETE RESTRICT,
    answer                 VARCHAR(30)  NOT NULL CHECK (answer IN ('Approved','Rejected','Manual Review')),
    responsible_agent_id    VARCHAR(10) REFERENCES AGENTS(agent_id) ON DELETE SET NULL,
    reasoning                TEXT       NOT NULL,
    risk_score                DECIMAL(5,2) NOT NULL,
    decision_status            VARCHAR(20) NOT NULL CHECK (decision_status IN ('Final','PendingReview','Overturned')),
    timestamp                    TIMESTAMPTZ NOT NULL
);

-- ---------------------------------------------------------------------
-- PROVENANCE_RECORDS  (lean hash-chain table -- no raw input/output data)
-- ---------------------------------------------------------------------
CREATE TABLE PROVENANCE_RECORDS (
    record_id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    orchestration_id        VARCHAR(50)   NOT NULL REFERENCES ORCHESTRATIONS(orchestration_id) ON DELETE RESTRICT,
    execution_id             UUID         REFERENCES AGENT_EXECUTIONS(execution_id) ON DELETE RESTRICT,  -- NULL for orchestrator-level events
    event_type                VARCHAR(50) NOT NULL,
    timestamp                   TIMESTAMPTZ NOT NULL,
    input_hash                   VARCHAR(64) NOT NULL,   -- SHA-256 hex digest, computed by orchestrator
    output_hash                   VARCHAR(64) NOT NULL,  -- SHA-256 hex digest, computed by orchestrator
    previous_record_hash            VARCHAR(64),         -- NULL only for the first record in the chain
    record_hash                       VARCHAR(64) NOT NULL UNIQUE  -- computed by orchestrator over this record + previous_record_hash
);

-- ---------------------------------------------------------------------
-- AUDIT_EVENTS
-- ---------------------------------------------------------------------
CREATE TABLE AUDIT_EVENTS (
    audit_id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    orchestration_id    VARCHAR(50)   NOT NULL REFERENCES ORCHESTRATIONS(orchestration_id) ON DELETE RESTRICT,
    execution_id         UUID         REFERENCES AGENT_EXECUTIONS(execution_id) ON DELETE RESTRICT,  -- NULL for orchestrator-level events
    event_type            VARCHAR(50) NOT NULL,
    actor                  VARCHAR(50) NOT NULL,
    description              TEXT      NOT NULL,
    timestamp                  TIMESTAMPTZ NOT NULL,
    record_hash                  VARCHAR(64) REFERENCES PROVENANCE_RECORDS(record_hash)  -- optional link to a cryptographic record
);

-- ---------------------------------------------------------------------
-- REGULATORY_MAPPINGS  (static reference table)
-- ---------------------------------------------------------------------
CREATE TABLE REGULATORY_MAPPINGS (
    mapping_id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id              UUID         REFERENCES PROVENANCE_RECORDS(record_id) ON DELETE SET NULL,
    framework                VARCHAR(50) NOT NULL CHECK (framework IN ('EU_AI_Act','NIST_AI_RMF','ECOA_RegB','FCRA')),
    requirement_id             VARCHAR(50) NOT NULL,
    requirement_name             VARCHAR(255) NOT NULL,
    tracechain_control             TEXT NOT NULL,
    compliance_status                 VARCHAR(20) NOT NULL CHECK (compliance_status IN ('Supported','PartiallySupported','Gap')),
    evidence_reference                  TEXT,
    notes                                 TEXT
);

-- ---------------------------------------------------------------------
-- Helpful indexes for common lookups (not in original worksheet, but
-- worth having from day one -- every FK column here gets queried
-- constantly when tracing a single application end-to-end)
-- ---------------------------------------------------------------------
CREATE INDEX idx_applications_user_id            ON APPLICATIONS(user_id);
CREATE INDEX idx_orchestrations_application_id   ON ORCHESTRATIONS(application_id);
CREATE INDEX idx_agent_executions_orchestration  ON AGENT_EXECUTIONS(orchestration_id);
CREATE INDEX idx_agent_executions_agent_id       ON AGENT_EXECUTIONS(agent_id);
CREATE INDEX idx_agent_decisions_execution_id    ON AGENT_DECISIONS(execution_id);
CREATE INDEX idx_evidence_execution_id           ON EVIDENCE(execution_id);
CREATE INDEX idx_accountability_execution_id     ON ACCOUNTABILITY_SCORES(execution_id);
CREATE INDEX idx_provenance_orchestration_id     ON PROVENANCE_RECORDS(orchestration_id);
CREATE INDEX idx_provenance_execution_id         ON PROVENANCE_RECORDS(execution_id);
CREATE INDEX idx_audit_events_orchestration_id   ON AUDIT_EVENTS(orchestration_id);
