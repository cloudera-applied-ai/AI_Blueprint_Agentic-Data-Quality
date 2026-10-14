# Data Quality Automation Through Private AI Inferencing and Intelligent Remediation

## Executive Summary

Organizations ingesting large volumes of structured data from external sources face two persistent challenges: detecting the full spectrum of quality issues hidden across hundreds of fields in millions of records, and translating those findings into production-ready remediation artifacts that can be deployed into enterprise data pipelines. The Data Quality AI platform addresses both by combining deep automated profiling with a private AI inference service to deliver deployable Apache NiFi flows, Cloudera Data Engineering (CDE) Spark jobs, YAML metadata specifications, and sensitivity classifications — without sensitive data ever leaving the organization's security boundary.

This document outlines the value proposition of this approach for data engineering teams, FinOps practitioners, compliance officers, and platform architects.


## The Problem

Consumption-based data platforms make quality management inherently difficult. The cost of bad data is not just the storage and compute spent processing it — it is the cascading failures, incorrect analytics, compliance violations, and manual rework that follow when quality issues go undetected. Without visibility into what is actually wrong with incoming data, remediation efforts are guesswork.

Typical pain points include:

**Invisible corruption at scale.** A single corrupted field — a random English word where a coded value should be — is invisible in a dataset of millions of rows. Without automated detection, these errors propagate silently into downstream analytics, reporting, and operational systems. Traditional data quality tools require extensive upfront rule configuration per data source, and static schema validation alone cannot catch values that are syntactically valid but semantically wrong.

**Manual remediation does not scale.** When quality issues are found, data engineers must hand-code NiFi dataflows to route and correct bad records, write PySpark scripts to flag and fix issues at scale, and create metadata documentation that captures the rules applied. Each of these artifacts takes days to develop per data source. For organizations onboarding dozens of new data feeds per year, the backlog grows faster than teams can clear it.

**No connection between detection and action.** Existing data quality tools treat detection and remediation as separate concerns. Profiling tools identify that 40% of phone numbers start with invalid digits, but generating the NiFi expression to route those records or the PySpark expression to flag them remains manual engineering work. This gap between "we found a problem" and "here is the fix" is where most data engineering time is consumed.

**Sensitivity classification is an afterthought.** With hundreds of fields containing a mix of PII, sensitive business data, and operational metadata, classification is typically performed manually during initial onboarding and never revisited. Determining whether a field constitutes sensitive data under applicable regulations requires contextual analysis of actual data content, not just column names.

**Quality teams spend their time on the wrong work.** Industry estimates suggest data engineers spend 60–80% of their time on repetitive detection and remediation tasks rather than higher-value pipeline architecture, optimization, and governance work.


## The Solution

### Automated Quality Detection: See What Is Actually Wrong

The platform loads incoming data into an in-memory DuckDB instance and executes six categories of quality analysis across every field. Unlike rule engines that require months of upfront configuration, the analyzer comes preloaded with configurable valid value sets and detection patterns that work immediately against any delimited dataset.

This enables three categories of analysis that directly inform remediation priorities:

#### 1. Coded Value and Format Validation

The analyzer checks coded fields against their valid value sets — identifying values outside permitted ranges, numeric codes that exceed valid bounds, and format mismatches where syntactically valid data is semantically incorrect. Values outside these sets are flagged with the specific invalid value, the percentage of affected records, and sample bad values for investigation.

**Remediation action:** Each invalid value finding directly translates into a NiFi RouteOnAttribute processor using Expression Language and a corresponding PySpark flag expression. The platform generates both automatically from the detection results.

#### 2. Corruption, Length, and Structural Analysis

The analyzer detects random text in fields that should contain structured codes or identifiers, values exceeding field-defined maximum lengths, and data appearing in fields designated as reserved or blank. Each issue type uses targeted detection — regex patterns for corruption, length comparisons against metadata-defined maximums, and emptiness checks for reserved fields.

**Remediation action:** Corrupted and blank-field violations generate nulling expressions in both NiFi and Spark artifacts. Length violations generate truncation logic in PySpark and quality flag attributes in NiFi. Each fix is calibrated to the specific issue type and field constraints.

#### 3. Severity-Based Prioritization

Issues are automatically classified by severity based on the percentage of affected records:

| Affected Records | Severity | Implication |
|---|---|---|
| > 50% | Critical | Systemic source problem — likely a feed-level failure |
| > 10% | High | Significant quality gap — affects downstream analytics reliability |
| > 1% | Medium | Notable issue — should be addressed in next remediation cycle |
| <= 1% | Low | Edge cases — monitor but may not warrant immediate action |

**Remediation action:** Severity ratings drive the prioritized action queue, ensuring engineering effort is directed at the highest-impact issues first. A field with 100% corruption needs a different remediation strategy than one with 0.5% invalid values.


### Production-Ready Remediation: From Detection to Deployment

The platform does not stop at identifying problems. For every set of detected issues, it generates three categories of production artifacts that integrate directly into enterprise data platforms.

**Apache NiFi v2 Flows** — Importable dataflow definitions that:
- Route records based on quality rules using NiFi Expression Language
- Split data into valid, corrected, and rejected streams
- Apply attribute-level corrections (nulling bad values, flagging issues, truncating oversized fields)
- Deploy directly into NiFi v2 environments without manual configuration

**CDE Spark Jobs** — PySpark scripts and job definitions that:
- Read delimited input at scale using Spark distributed processing
- Add boolean flag columns for each detected issue type using batched `.select()` operations (a deliberate performance optimization over sequential `.withColumn()` calls)
- Create composite quality flags for downstream filtering
- Split data into valid, corrected, and rejected DataFrames
- Apply fix expressions (truncation, nulling, code normalization)
- Write output in Parquet, Delta, CSV, or JSON formats
- Include pre-configured CDE job definitions POST-able directly to the CDE API

**YAML Metadata Specifications** — Data ingestion documents that:
- Catalog all fields with inferred data types, constraints, and profiling statistics
- Map valid value sets to their respective coded fields
- Summarize quality issues with severity ratings
- Provide null percentages, distinct value counts, and length distributions
- Serve as machine-readable input for data governance frameworks and catalog integration

All generated artifacts are persisted with full version history — each tracked by unique identifier with version numbering, clone capability, and complete edit history.


### Private AI Inferencing: Intelligent Analysis Without Data Exposure

The application integrates with a private inferencing service (such as Cloudera AI Inference) using an OpenAI-compatible API endpoint. This is not a generic chatbot — it is a ReAct-style agent equipped with 10 purpose-built tools spanning quality detection, remediation generation, and data exploration.

#### Why Private Inferencing Matters

Enterprise datasets contain highly sensitive information: field values may include personal identifiers, financial data, or regulated information. Column names reveal business domains and data models. Quality analysis results expose the organization's data handling weaknesses. Sending this context to a public AI service introduces unacceptable risk for most enterprises.

A private inferencing service provides:

**Data sovereignty:** All data, field values, quality analysis results, and generated remediation artifacts remain within the organization's network boundary. The LLM runs on infrastructure that the organization controls.

**Compliance alignment:** Meets requirements for SOC 2, HIPAA, PCI DSS, GDPR, and other frameworks that govern where sensitive operational data can be processed.

**Auditability:** Every inference request and response stays within the organization's logging and monitoring infrastructure.

**No training on your data:** Private models do not use your queries, data patterns, or quality analysis results to improve future model versions, eliminating the risk of information leakage through model updates.

#### What the AI Agent Can Do

Unlike a static dashboard, the AI assistant enables interactive, conversational exploration of data quality and remediation. Users can ask natural-language questions and receive answers grounded in actual data analysis. The agent has access to:

| Capability | Tools | Example Question |
|---|---|---|
| Data profiling | Column profiling, data summary, SQL queries | "Profile the customer ID column and show me the value distribution" |
| Quality detection | Issue detection, coded value validation | "Scan all phone number fields for quality issues" |
| Schema exploration | Field metadata lookup, data summary | "What fields are classified as code fields and what are their valid values?" |
| NiFi generation | Issue detection + flow generation | "Generate a NiFi flow to remediate all critical code violations" |
| Spark generation | Issue detection + job generation | "Create a Spark job that fixes all length violations and outputs to parquet" |
| Metadata generation | Profiling + YAML generation | "Generate a complete YAML specification for this data source" |
| Sensitivity classification | ML + LLM classification | "Classify all columns for PII sensitivity and map to industry standards" |
| Ad-hoc investigation | SQL queries via DuckDB | "Show me all records where the country code is not in the valid set" |

The agent reasons through multi-step problems, chaining tool calls together. For example, when asked "What are the highest-priority quality issues and how should we fix them?", the agent might:

1. Run quality detection across all fields
2. Profile the most severely affected columns to understand data distributions
3. Cross-reference field metadata to assess compliance implications
4. Generate a NiFi flow targeting the critical and high-severity issues
5. Generate a CDE Spark job for at-scale remediation
6. Provide a prioritized action plan with severity-based recommendations

This level of analysis would take a data engineer days of manual work across multiple tools. The AI agent delivers it in minutes, with full traceability of its reasoning.


### Automated Column Classification: Sensitivity and Compliance Mapping

The platform includes a two-layer classification pipeline that categorizes every field automatically:

**Layer 1: Machine Learning Classifiers** — Three pre-trained TF-IDF + Logistic Regression pipelines classify each column by sensitivity level (PII, PHI, internal, public), semantic type (identifier, phone, name, date, code, address, and 15+ others), and expected format. Classification runs in milliseconds and provides confidence scores.

**Layer 2: LLM Enhancement** — For columns where classifier confidence falls below a configurable threshold (default 70%), the LLM provides enriched classification including business terms, industry-standard mappings, and regulatory tags. This hybrid approach combines the speed of ML with the contextual reasoning of an LLM.

The result is a complete sensitivity map of every field in the data source — essential for data governance, access control decisions, and compliance reporting.


## Quantified Value

Based on typical enterprise data ingestion environments:

| Category | Without Data Quality AI | With Data Quality AI |
|---|---|---|
| Quality issue detection | Days to weeks per data source (manual review) | Minutes (automated scan, all fields, 6 issue types) |
| Remediation artifact development | 2–5 days per artifact (hand-coded NiFi flows, Spark jobs) | Minutes per artifact (AI-generated, validated) |
| Data source onboarding | 4–8 weeks per new feed | Hours of guided AI interaction |
| Quality check coverage | Partial (human fatigue limits manual review) | Comprehensive (all fields, all issue types, every record) |
| Sensitivity classification | Manual, performed once at onboarding | ML-driven with confidence scores, repeatable |
| Metadata documentation | Often missing or outdated | Auto-generated, versioned, machine-readable |

For an organization onboarding 10–20 new data feeds per year, the cumulative impact is significant:

- **Engineering time saved:** 40–80 weeks of data engineer effort annually, redirected from repetitive detection and remediation coding to higher-value pipeline architecture and optimization
- **Reduced defect leakage:** Comprehensive automated scanning catches issues that manual review misses, reducing downstream data quality incidents in analytics and reporting
- **Faster time to production:** New data sources reach production readiness in hours instead of weeks, accelerating partner integrations, vendor onboarding, and program launches
- **Compliance confidence:** Automated sensitivity classification and documented remediation rules provide auditable evidence of data handling controls


## Architecture Advantages

### Eight-Stage Automated Pipeline

When data is loaded, the platform executes a complete analysis pipeline as a single streaming operation:

1. **Profiling** — Statistical analysis of all non-reserved fields (counts, distributions, lengths, top values)
2. **Issue Detection** — Six quality checks across all fields with severity classification
3. **Schema Recommendation** — LLM-generated data type, nullability, primary key, and constraint recommendations
4. **Rules Derivation** — Conversion of detected issues into editable data quality rules with severity tiers and enable/disable controls
5. **NiFi Flow Generation** — Automatic generation and persistence of a complete remediation flow
6. **Spark Job Generation** — Automatic generation and persistence of a CDE job definition and PySpark script
7. **Column Classification** — ML + LLM sensitivity, semantic type, and compliance classification
8. **Metadata Generation** — Complete YAML data ingestion specification with profiling, constraints, and quality summary

Each stage streams progress to the UI in real time. Any stage failure is non-fatal — the pipeline continues and reports which stages completed. All generated artifacts are immediately navigable from the pipeline view.

### Streaming, Transparent AI Reasoning

The AI assistant streams its responses in real time via Server-Sent Events, providing visibility into which tools it calls, what arguments it passes, and what data it examines. This transparency is critical for building trust — users can see exactly how the agent arrived at its recommendations, not just the final answer.

### No Credentials Required for Core Analysis

The core quality analysis, remediation generation, and classification capabilities operate entirely on uploaded data files. Organizations can gain the full value of automated detection and remediation without granting the platform access to production databases. Data is loaded into an in-memory DuckDB instance that exists only for the duration of the session — no raw data is persisted to disk by the application.

### Flexible LLM Backend

The platform connects to any OpenAI-compatible inference endpoint:

- **Cloudera AI Inference** — Primary enterprise target, with automatic token resolution and workload authentication
- **Local models via Ollama** — For development, air-gapped environments, or maximum data isolation
- **Any OpenAI-compatible API** — Extensible to organizational model serving infrastructure

This flexibility allows organizations to choose their preferred inference backend based on security requirements, model capabilities, and infrastructure constraints.


## Who Benefits

| Role | Value |
|---|---|
| **Data Engineers** | Eliminate days of manual NiFi flow and Spark job development per data source; receive production-ready remediation artifacts from a conversational interface |
| **Data Quality Analysts** | Comprehensive, automated scanning of all fields and issue types replaces partial manual review; severity-based prioritization focuses effort on highest-impact issues |
| **FinOps / Platform Teams** | Reduced compute waste from reprocessing bad data; quantified quality metrics support data-driven pipeline investment decisions |
| **Compliance Officers** | Automated PII/sensitivity classification provides auditable documentation; private inferencing keeps all data within the security boundary |
| **Data Architects** | Complete YAML metadata specifications and schema recommendations provide machine-readable documentation for data governance frameworks and catalog integration |
| **Engineering Leadership** | Quantifiable reduction in data source onboarding time and remediation development effort; measurable quality coverage improvements tied to specific automated checks |
