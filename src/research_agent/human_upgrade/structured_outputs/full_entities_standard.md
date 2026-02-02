Full Entities Standard (v2) — Final

Mode goal
Produce a reliable, evidence-anchored overview of an organization (company, clinic, brand, author platform, researcher, or biotech entrepreneur) covering:

who they are

what they offer

how it works / how it’s made

what is claimed

what evidence exists (triage-level)

what confidence to assign

what research to run next

This mode is intentionally non-exhaustive and designed to route into deeper modes.

STAGE 1 — Entity Biography, Identity & Ecosystem

Purpose: Establish who this entity is, who leads it, how it positions itself, and why it matters.

Assumption: entity name, major people, and major products are already provided as inputs.
This stage enriches and contextualizes, not merely identifies.

Sub-stages
1.1 Entity Biography & Organizational Overview

What this stage answers

“What is this organization/person, really?”

“How do they describe themselves vs how others describe them?”

Responsibilities

Produce a concise but information-dense biography / overview

Clarify the entity’s core mission, audience, and operating posture:

consumer wellness vs medical-adjacent vs clinical vs media vs hybrid

Summarize the origin story and major inflection points

Identify primary lines of business and how they interrelate

Sub-Agent

BusinessIdentityAndLeadershipAgent

Outputs

EntityBiography

OperatingPostureSummary

HighLevelTimeline

1.2 People, Leadership & Expert Roles

What this stage answers

“Who is responsible for the ideas, products, and claims?”

“Who lends credibility or influence?”

Responsibilities

Enrich provided people with:

roles, tenure, and functional responsibility

education, licenses, certifications (where applicable)

prior companies, labs, clinics, or notable projects

Flag:

advisory vs operational roles

public-facing experts vs internal decision-makers

Sub-Agent

PersonBioAndAffiliationsAgent

Outputs

PeopleProfiles

RoleResponsibilityMap

CredentialAnchors

1.3 Ecosystem Positioning

What this stage answers

“Where does this entity sit in the biotech / biohacking / wellness ecosystem?”

Responsibilities

Identify:

direct competitors

adjacent substitutes or alternatives

partners, distributors, platforms, clinics, labs

Classify ecosystem role:

product manufacturer

platform / protocol originator

reseller / educator

clinic or service provider

Sub-Agent

EcosystemMapperAgent

Outputs

CompetitorSet

PartnerAndPlatformGraph

MarketCategoryPlacement

1.4 Credibility & Risk Signals (Light)

What this stage answers

“Are there early warning signs or credibility anchors?”

Responsibilities

Surface:

notable credentials and affiliations

past controversies or disputes (non-exhaustive)

retractions, sanctions, licensing issues if obvious

Characterize risk posture, not adjudicate it

Sub-Agent

CredibilitySignalScannerAgent

Outputs

CredibilitySignals

RiskFlagsLight

STAGE 2 — Products, Specifications, Technology & Claims

Purpose: Precisely define what is offered, how it works / is made, and what is promised.

2.1 Product / Service Inventory

What this stage answers

“What exactly is being sold or delivered?”

Responsibilities

Enumerate:

products, devices, services, programs, books, courses

Capture:

delivery route

intended use

target audience

De-duplicate overlapping offerings

Sub-Agent

ProductCatalogerAgent

Outputs

ProductCatalog

ProductGroupingMap

2.2 Product Specifications (Deep Slice)

What this stage answers

“What’s actually in this product / how is it used / what does it cost?”

Responsibilities

For selected priority products:

ingredients / actives / materials

dosages, directions, schedules

pricing, variants, subscriptions

manuals, warranties, what’s included

Extract officially stated warnings (not interpretive)

Sub-Agent

ProductSpecAgent ✅

Outputs

ProductSpecs

IngredientOrMaterialLists

UsageAndWarningSnippets

2.3 Manufacturing & Technology Platform

What this stage answers

“How does this product or service actually work?”

“How is it made or delivered?”

Responsibilities

Extract:

formulation or delivery technology

device mechanisms or protocols

QA / GMP / ISO / testing claims

patents or proprietary processes (if disclosed)

Translate marketing descriptions into technical mechanisms where possible

Sub-Agent

TechnologyProcessAndManufacturingAgent ✅

Outputs

TechnologyMechanismSummaries

ManufacturingAndQAClaims

PatentAndProcessReferences

2.4 Claims Extraction, Normalization & Salience

What this stage answers

“What outcomes are being promised — and which matter most?”

Responsibilities

Extract all explicit claims from:

product pages

help/FAQ

landing pages

books/course descriptions

Normalize claims into taxonomy buckets:

compounds, pathways, conditions, biomarkers, technologies

Rank claims by:

prominence

differentiation

implied impact

Sub-Agent

ClaimsExtractorAndTaxonomyMapperAgent

Outputs

ClaimsLedger

NormalizedClaimMap

ClaimSalienceRanking

Optional 2.X — Product Reviews & User Feedback

Purpose: Capture anecdotal signals without conflating with evidence.

Responsibilities

Aggregate first- and third-party reviews

Separate:

praise vs complaints

efficacy vs logistics (shipping, UX)

Clearly label anecdotal nature and bias risks

Sub-Agent

ProductReviewsAgent (optional)

Outputs

UserFeedbackSummary

AnecdotalSignalNotes

STAGE 3 — Evidence & Validation Snapshot (Triage)

Purpose: Rapidly assess what evidence exists and where gaps are.

3.1 Evidence Discovery

Responsibilities

Harvest:

trials, studies, whitepapers, case studies

Distinguish:

company-affiliated vs independent evidence

Sub-Agent

CaseStudyHarvestAgent

Outputs

EvidenceArtifacts

3.2 Evidence Classification

Responsibilities

Classify evidence by:

human / animal / in vitro

RCT / observational / mechanistic / anecdotal

peer-reviewed vs marketing

Sub-Agent

EvidenceClassifierAgent

Outputs

EvidenceClassificationTable

3.3 Strength & Gaps Assessment

Responsibilities

Evaluate:

evidence–claim alignment

overextension or mismatch

Identify what evidence would be required to strengthen claims

Sub-Agent

StrengthAndGapAssessorAgent

Outputs

ClaimSupportMatrix

EvidenceGapNotes

3.4 Safety & Risk Signals

Responsibilities

Surface:

contraindications

adverse effects language

early regulatory warning signals (non-deep)

Sub-Agent

ContraindicationsAndSafetyAgent

Outputs

SafetySignalSummary

STAGE 4 — Synthesis, Confidence & Research Routing

Purpose: Convert research into usable judgment and next actions.

4.1 Entity Synthesis

Responsibilities

Merge outputs from Stages 1–3 into a coherent entity representation

Sub-Agent

KnowledgeSynthesizerAgent

Outputs

EntityResearchSummary

4.2 Claim Confidence Scoring

Responsibilities

Assign confidence tiers:

Proven / Plausible / Speculative / Unsupported

Provide rationale tied to evidence type and quality

Sub-Agent

ClaimConfidenceScorerAgent

Outputs

ClaimConfidenceScores

4.3 Narrative Summary

Responsibilities

Contrast:

marketing narrative vs evidentiary reality

Highlight:

key stories, adoption drivers, tensions

Sub-Agent

NarrativeAnalystAgent

Outputs

NarrativeAndContextSummary

4.4 Next-Step Research Routing

Responsibilities

Recommend escalation paths:

Full Entities Deep

Regulatory Deep Dive

Trial-Level Validation

Market or Trend Analysis

Sub-Agent

ResearchRouterAgent

Outputs

ResearchRecommendations

What this mode intentionally does not do

Full regulatory adjudication

Financial modeling

Adversarial red-teaming

Macro trend synthesis

Those are explicit follow-on modes.

Why this version is “ready to implement”

Every sub-agent has a single clear responsibility

Stages depend on artifacts, not implicit order

Works whether agents are run:

standalone

per stage

or in a LangGraph DAG

Naturally supports partial entry and recomposition

If you want, next we can:

express this as a LangGraph node graph

define artifact schemas

or design automatic escalation triggers based on confidence scores