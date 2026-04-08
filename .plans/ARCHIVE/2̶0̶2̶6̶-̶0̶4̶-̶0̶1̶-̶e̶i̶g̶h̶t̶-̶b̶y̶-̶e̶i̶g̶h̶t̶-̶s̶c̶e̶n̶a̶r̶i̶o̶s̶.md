# ~~8x8 Real-World Scenarios for AgentAuth Components~~

> **Status:** ~~ARCHIVED~~ — demo-supporting educational doc. Kept for historical reference; may inform demo rebuild after v0.3.0.

**Created:** 2026-04-01
**Purpose:** Demonstrate deep understanding of how all 8 AgentAuth components appear in real-world multi-agent systems. Each domain has 8 scenarios — one per component. Some scenarios naturally don't need all components, and that's called out.

---

## Components Reference

- **C1 — Ephemeral Identity:** Each agent gets a unique SPIFFE ID on launch
- **C2 — Short-Lived Tokens:** Tokens have a TTL and die automatically
- **C3 — Zero-Trust Validation:** Every tool call validated by broker (sig, exp, rev, scope)
- **C4 — Expiration & Revocation:** Tokens can be revoked mid-task, proven dead
- **C5 — Immutable Audit:** Hash-chained event trail, tamper-proof
- **C6 — Mutual Auth:** Both parties must be registered for delegation
- **C7 — Delegation Chain:** Parent delegates attenuated scope to child
- **C8 — Observability:** Real-time visibility into credential lifecycle

---

## 1. Healthcare — Patient Triage System

**Agents:** Intake Agent, Diagnosis Agent, Prescription Agent, Referral Agent, Billing Agent

| # | Component | Scenario |
|---|-----------|----------|
| C1 | Ephemeral Identity | A Diagnosis Agent spins up to analyze a patient's symptoms. It gets a unique SPIFFE ID tied to this session. When the hospital audits who accessed patient X's records at 2:14 PM, they can trace it to exactly this agent instance — not "some diagnosis agent" but *this specific one*. |
| C2 | Short-Lived Tokens | The Prescription Agent gets a 10-minute token to write a prescription. The doctor's visit takes 7 minutes. Three minutes later the token is dead. If a delayed callback tries to use that token to write another prescription, it fails. No standing access to the prescription system. |
| C3 | Zero-Trust | The Diagnosis Agent calls `get_patient_vitals(patient_id="P-4421")`. Before the vitals database returns anything, the broker checks: is this token's signature valid? Has it expired? Has it been revoked? Does it have `read:patient:vitals` scope? All four pass — vitals returned. |
| C4 | Revocation | A nurse flags a Prescription Agent that seems to be writing unusual dosages. The supervisor revokes the agent's token immediately. The agent's next call to `write_prescription()` is rejected. Post-revocation check confirms: token dead, no more prescriptions can be written. |
| C5 | Immutable Audit | A malpractice investigation six months later asks: "Who authorized the fentanyl prescription for patient P-4421?" The audit trail shows every event hash-chained: Intake logged symptoms → Diagnosis read vitals → Prescription wrote the Rx. Each event links to the previous via hash. No event can be deleted or reordered without breaking the chain. |
| C6 | Mutual Auth | The Diagnosis Agent tries to delegate to a new Specialist Agent that was just deployed but hasn't registered with the broker yet. Broker rejects: "target agent not registered." The specialist must complete registration (get its own identity) before it can receive delegated credentials. |
| C7 | Delegation | The Intake Agent has `read:patient:*` (broad access to triage). It delegates to the Diagnosis Agent with only `read:patient:vitals, read:patient:history` — no access to billing, insurance, or contact info. The Diagnosis Agent physically cannot look up what the patient owes. The chain is traceable: Intake authorized Diagnosis to see vitals only. |
| C8 | Observability | The hospital's compliance dashboard shows real-time: Intake Agent registered (scope: `read:patient:*`), Diagnosis Agent received delegation (scope: `read:patient:vitals`), Prescription Agent's token expires in 3:42, last tool call was `write_prescription` — ALLOWED. All visible, all live. |

---

## 2. Financial Trading — Order Execution System

**Agents:** Market Data Agent, Strategy Agent, Order Agent, Risk Agent, Settlement Agent

| # | Component | Scenario |
|---|-----------|----------|
| C1 | Ephemeral Identity | A Strategy Agent is launched to execute a momentum trade on AAPL. It gets SPIFFE ID `spiffe://trading/strategy/sess-77a3`. When regulators ask "who initiated the AAPL buy at 10:03:22?", the answer is this exact agent instance — not the strategy service in general, but this session. |
| C2 | Short-Lived Tokens | The Order Agent gets a 2-minute token — just enough to place and confirm a single order. After confirmation, the token dies. Even if the agent's process stays running, it cannot place another order without requesting a new token. No accumulated trading authority. |
| C3 | Zero-Trust | The Order Agent calls `place_order(symbol="AAPL", qty=500, side="buy")`. Broker validates the token before the order hits the exchange: signature OK, not expired, not revoked, has `write:orders:equity` scope. If the agent tried `write:orders:options` instead, the broker would deny — the scope doesn't cover derivatives. |
| C4 | Revocation | The Risk Agent detects that the Strategy Agent is placing orders that exceed the firm's daily VaR limit. It triggers revocation of the Order Agent's token. The Order Agent's next `place_order()` call fails instantly. The position is frozen. No additional risk can be accumulated until a human reviews. |
| C5 | Immutable Audit | The SEC requests a complete record of all trades placed by automated agents on March 15th. The audit trail provides a hash-chained sequence: Market Data Agent read AAPL price → Strategy Agent decided to buy → Order Agent placed order #77291 → Settlement Agent confirmed T+1 delivery. Each event is cryptographically linked. The firm can prove nothing was inserted or removed after the fact. |
| C6 | Mutual Auth | The Strategy Agent tries to delegate order-placing authority to a newly deployed Hedging Agent. But the Hedging Agent hasn't registered with the broker yet — maybe it was deployed to the wrong cluster, or its startup script failed. Broker rejects the delegation. No credentials flow to an unknown entity. |
| C7 | Delegation | The Strategy Agent holds `read:market:*, write:orders:equity`. It delegates to the Order Agent with only `write:orders:equity` — no market data access. The Order Agent can place the trade but can't read the market data that informed the decision. Separation of concerns enforced by credential, not by code. The chain shows: Strategy authorized Order to write equities, nothing more. |
| C8 | Observability | The trading floor's operations screen shows: Strategy Agent (active, TTL 4:31, scope: `read:market:*, write:orders:equity`), Order Agent (active, TTL 1:12, scope: `write:orders:equity` — delegated from Strategy), Risk Agent monitoring (scope: `read:positions:*`). A red flash when the Risk Agent triggers revocation. Live enforcement cards showing each order validation. |

---

## 3. Legal — Contract Review Pipeline

**Agents:** Intake Agent, Clause Analyzer Agent, Risk Scorer Agent, Redlining Agent, Summary Agent

| # | Component | Scenario |
|---|-----------|----------|
| C1 | Ephemeral Identity | A Clause Analyzer Agent launches to review an NDA for Acme Corp. It gets SPIFFE ID `spiffe://legal/clause-analyzer/sess-9f2b`. Six months later, when opposing counsel asks who reviewed clause 4.2, the firm can point to this exact agent session — when it ran, what it accessed, what it concluded. |
| C2 | Short-Lived Tokens | The Redlining Agent gets a 15-minute token to suggest edits to a contract. The review takes 12 minutes. The token dies 3 minutes later. A junior associate can't accidentally re-run the agent next day and have it modify a finalized contract — the token is long dead. |
| C3 | Zero-Trust | The Clause Analyzer calls `get_contract_text(contract_id="NDA-2026-0441")`. The broker validates before the document server responds: valid signature, not expired, not revoked, has `read:contracts:nda` scope. If the agent tried to read a merger agreement with `read:contracts:ma`, it would be denied — wrong scope for its role. |
| C4 | Revocation | A partner realizes the wrong version of the contract was uploaded and the Redlining Agent is suggesting edits based on stale text. They revoke the agent's token. The agent's next `suggest_edit()` call fails. No edits based on the wrong document version can be saved. |
| C5 | Immutable Audit | A client disputes that a particular clause was reviewed. The audit trail shows the Clause Analyzer read the contract at 14:02, flagged clause 7.3 as non-standard at 14:04, the Risk Scorer assessed it at 14:06. Hash-chained: the client can verify no events were added retroactively to cover a missed clause. |
| C6 | Mutual Auth | The Clause Analyzer tries to hand off a particularly complex IP clause to a Patent Specialist Agent. But the Patent Specialist was recently decommissioned and deregistered. Broker rejects the delegation — no credentials flow to a deregistered agent. The Clause Analyzer has to handle it or escalate to a human. |
| C7 | Delegation | The Intake Agent has `read:contracts:*, read:client:*` (it needs to see the contract and know the client context). It delegates to the Clause Analyzer with only `read:contracts:nda` — no client data, no other contract types. The Clause Analyzer sees the NDA text but has no idea what the client's fee arrangement is or what other deals are in progress. |
| C8 | Observability | The firm's matter management dashboard shows: Intake Agent processed contract NDA-2026-0441, delegated to Clause Analyzer (scope: `read:contracts:nda`), Clause Analyzer flagged 3 clauses, Risk Scorer assessed 3 clauses (2 medium, 1 high), Redlining Agent suggested 2 edits — all with timestamps, token TTLs, and enforcement outcomes. |

---

## 4. DevOps — Incident Response System

**Agents:** Alert Triage Agent, Log Analyzer Agent, Remediation Agent, Notification Agent, Postmortem Agent

| # | Component | Scenario |
|---|-----------|----------|
| C1 | Ephemeral Identity | PagerDuty fires an alert at 3 AM. An Alert Triage Agent spins up with SPIFFE ID `spiffe://devops/triage/inc-8812`. Every log query, every runbook lookup, every Slack message sent during this incident traces back to this specific agent instance. In the postmortem, there's no ambiguity about which automated responder did what. |
| C2 | Short-Lived Tokens | The Remediation Agent gets a 5-minute token to restart a failing service. It restarts the service in 30 seconds. Four and a half minutes later, the token is dead. Even if the agent's container stays running, it can't restart anything else. If the service crashes again, a new incident and a new token are required. |
| C3 | Zero-Trust | The Remediation Agent calls `restart_service(service="payment-api", cluster="prod-east")`. The broker validates: signature, expiry, revocation, scope `write:infra:restart`. If the agent tried `scale_service()` (which requires `write:infra:scale`), the broker denies it — restarting is not scaling. The agent can fix but can't change capacity. |
| C4 | Revocation | The Log Analyzer Agent is querying production logs but the on-call engineer realizes it's pulling logs from the wrong cluster — the agent is reading customer PII from a region it shouldn't access. The engineer revokes the agent immediately. Next `query_logs()` call is rejected. The agent's access to logs is cut off mid-investigation. |
| C5 | Immutable Audit | After the incident, the postmortem asks: "Did the Remediation Agent restart the wrong service?" The audit trail is hash-chained: Alert received → Triage classified as P1/infra → Log Analyzer queried payment-api logs → Remediation restarted payment-api in prod-east. The sequence is cryptographically ordered. No one can claim the remediation happened before the diagnosis. |
| C6 | Mutual Auth | The Triage Agent tries to delegate log access to a newly deployed Compliance Agent that's supposed to check if the incident exposed customer data. But the Compliance Agent was just deployed and hasn't registered yet — maybe the Kubernetes pod is still starting. Broker rejects. The delegation waits until the agent is fully registered and known to the system. |
| C7 | Delegation | The Alert Triage Agent holds `read:logs:*, read:infra:status, write:notifications:*`. It delegates to the Log Analyzer with only `read:logs:payment-api` — not all logs, just the failing service's logs. The Log Analyzer can't read auth service logs, database logs, or anything outside payment-api. If the incident turns out to involve another service, a new delegation with broader scope is needed. |
| C8 | Observability | The incident command dashboard shows: Triage Agent (active, classified P1/infra), Log Analyzer (active, scope: `read:logs:payment-api`, queried 3 times — all ALLOWED), Remediation Agent (completed, token expired, restarted payment-api), Notification Agent (active, sent Slack to #incidents). Enforcement cards show every broker validation. |

---

## 5. E-Commerce — Order Fulfillment System

**Agents:** Order Intake Agent, Inventory Agent, Payment Agent, Shipping Agent, Customer Notification Agent

| # | Component | Scenario |
|---|-----------|----------|
| C1 | Ephemeral Identity | A customer places order #ORD-99281. A Payment Agent launches with SPIFFE ID `spiffe://ecom/payment/sess-4e71`. When the customer later disputes the charge, the company can trace exactly which agent instance processed the payment, what it accessed, and what it charged — not "the payment service" but this specific session. |
| C2 | Short-Lived Tokens | The Payment Agent gets a 3-minute token to charge the customer's card. The charge goes through in 2 seconds. The token dies 2 minutes and 58 seconds later. Even if there's a retry bug in the payment service, the token can't be reused to double-charge. A new order requires a new token. |
| C3 | Zero-Trust | The Shipping Agent calls `create_shipment(order_id="ORD-99281", address="...")`. The broker validates: does this agent have `write:shipping:create` scope? Is the token still alive? Every shipment creation is independently validated — the agent doesn't get trusted just because it created a shipment 5 minutes ago. |
| C4 | Revocation | A fraud detection system flags order #ORD-99281 as potentially fraudulent after the Payment Agent has already charged the card but before the Shipping Agent has shipped. The Shipping Agent's token is revoked. Its `create_shipment()` call fails. The product stays in the warehouse while fraud review happens. The payment can be reversed; the shipment was prevented. |
| C5 | Immutable Audit | A customer claims they were charged but never received the product. The audit trail shows: Order Intake received order → Inventory checked stock (in stock) → Payment charged $89.99 → Shipping Agent's token was REVOKED (fraud flag) → shipment never created. Hash-chained: the company can prove the shipment was blocked and the charge should be refunded. No events can be retroactively inserted to claim the shipment happened. |
| C6 | Mutual Auth | The Shipping Agent tries to delegate notification authority to a new Delivery Tracking Agent that the ops team just deployed. But the Tracking Agent hasn't completed registration — its health check is still failing. Broker rejects the delegation. No tracking notifications go out from an unverified agent. The system waits until the agent is healthy and registered. |
| C7 | Delegation | The Order Intake Agent holds `read:orders:*, read:customer:*`. It delegates to the Inventory Agent with only `read:orders:items` — the Inventory Agent can see what items were ordered (to check stock) but not the customer's address, payment method, or order history. The Inventory Agent doesn't need to know who the customer is to check if item SKU-8812 is in stock. |
| C8 | Observability | The fulfillment operations dashboard shows: Order #ORD-99281 in progress. Inventory Agent (done, stock confirmed), Payment Agent (done, charged $89.99, token expired), Shipping Agent (REVOKED — fraud flag), Customer Notification Agent (pending — blocked because shipping didn't complete). Real-time enforcement cards show the fraud revocation and the blocked shipment call. |

---

## 6. Education — AI Tutoring System

**Agents:** Assessment Agent, Curriculum Agent, Tutoring Agent, Grading Agent, Parent Report Agent

| # | Component | Scenario |
|---|-----------|----------|
| C1 | Ephemeral Identity | A student starts a math tutoring session. A Tutoring Agent launches with SPIFFE ID `spiffe://edu/tutor/sess-3a92`. The school can audit exactly which agent instance interacted with the student — critical for FERPA compliance. If the student reports the tutor said something inappropriate, the school can trace the exact session. |
| C2 | Short-Lived Tokens | The Grading Agent gets a 10-minute token to score a quiz. The student submitted a 5-question quiz; grading takes 15 seconds. The token dies. If the Grading Agent's process hangs and restarts an hour later, it can't retroactively change the grade — the token is expired. A new grading request requires a new token. |
| C3 | Zero-Trust | The Tutoring Agent calls `get_student_progress(student_id="STU-1122")` to personalize a lesson. The broker validates every call: does this agent have `read:student:progress` scope for this student? Even though the agent just successfully read the student's progress 2 minutes ago, this new call is independently validated. No cached trust. |
| C4 | Revocation | A parent calls the school and requests that the AI tutoring be stopped for their child immediately. The administrator revokes the Tutoring Agent's token mid-session. The agent's next call to `present_lesson()` fails. The session ends instantly — the parent's request is honored in real-time, not at the next scheduled check. |
| C5 | Immutable Audit | The school district audits AI tutoring compliance. The audit trail shows: Assessment Agent evaluated student STU-1122 at 9:01 → Curriculum Agent selected algebra lesson plan at 9:03 → Tutoring Agent presented 12 problems over 25 minutes → Grading Agent scored 10/12 at 9:28. Hash-chained: the district can verify the sequence is authentic and unmodified. |
| C6 | Mutual Auth | The Tutoring Agent tries to delegate report-writing to a Parent Report Agent that was just updated and redeployed. The new version hasn't completed registration. Broker rejects. The old version's registration was invalidated by the redeployment, and the new version isn't ready yet. No student data flows to an unverified agent version. |
| C7 | Delegation | The Assessment Agent holds `read:student:*, write:student:assessments`. It delegates to the Tutoring Agent with only `read:student:progress` — the Tutoring Agent can see how the student is doing but cannot read their home address, parent contact info, disability accommodations, or any other sensitive records. FERPA's minimum necessary principle enforced by credential. |
| C8 | Observability | The school's AI oversight dashboard shows: 47 active tutoring sessions. Student STU-1122's session: Tutoring Agent (active, TTL 12:44, scope: `read:student:progress`), last tool call `present_problem` — ALLOWED, 3 tool calls total, 0 denied. Grading Agent (pending, waiting for quiz submission). Parent Report Agent (not yet invoked). |

---

## 7. Supply Chain — Logistics Coordination System

**Agents:** Demand Forecast Agent, Procurement Agent, Warehouse Agent, Routing Agent, Customs Agent

| # | Component | Scenario |
|---|-----------|----------|
| C1 | Ephemeral Identity | A Procurement Agent launches to negotiate with a supplier for 10,000 units of component X. It gets SPIFFE ID `spiffe://supply/procurement/po-6621`. When the supplier later disputes the agreed price, the company can prove exactly which agent instance communicated the terms — not "our procurement system" but this specific negotiation session. |
| C2 | Short-Lived Tokens | The Customs Agent gets a 30-minute token to file an import declaration. The filing takes 5 minutes. The token dies 25 minutes later. If a duplicate filing attempt comes in (network retry, queued message replay), the token is dead and the duplicate is rejected. No accidental double-filings with different declared values. |
| C3 | Zero-Trust | The Routing Agent calls `get_carrier_rates(origin="Shanghai", dest="Los Angeles", weight_kg=8200)`. The broker validates: valid token, not expired, not revoked, has `read:logistics:rates` scope. If the Routing Agent tried `book_carrier()` (which requires `write:logistics:booking`), it would be denied. Reading rates doesn't mean you can book. |
| C4 | Revocation | The Procurement Agent has been negotiating with a supplier, but intelligence arrives that the supplier is on a sanctions list. The compliance team revokes the Procurement Agent's token immediately. The agent's next call to `submit_purchase_order()` fails. No order goes to a sanctioned entity, even though negotiations were already underway. |
| C5 | Immutable Audit | A container of goods is stuck at the port. Customs asks for a full chain of custody for the shipment. The audit trail shows: Demand Forecast predicted 10,000 units needed → Procurement submitted PO to Supplier X → Warehouse received goods at Dock 7 → Routing booked carrier MaerskLine → Customs declaration filed. Hash-chained: every handoff is cryptographically ordered. Customs can verify no step was fabricated. |
| C6 | Mutual Auth | The Routing Agent tries to delegate shipment tracking to a new Carrier Integration Agent that the logistics partner just deployed. But the partner's agent hasn't registered with the company's broker — it's from an external system that hasn't completed onboarding. Broker rejects. No shipment data flows to an unverified external agent, even if the partner claims it's legitimate. |
| C7 | Delegation | The Demand Forecast Agent holds `read:sales:*, read:inventory:*, read:logistics:*` (it needs broad visibility to predict demand). It delegates to the Procurement Agent with only `read:inventory:levels, write:procurement:orders` — the Procurement Agent can see what's low in stock and place orders, but can't read sales data, pricing margins, or logistics routes. It knows what to buy but not why or how much profit each unit generates. |
| C8 | Observability | The supply chain control tower shows: PO-6621 in progress. Demand Forecast Agent (done, predicted 10,000 units), Procurement Agent (active, negotiating, scope: `read:inventory:levels, write:procurement:orders`, TTL 18:22), Warehouse Agent (pending), Routing Agent (pending). An enforcement card flashes red when the Procurement Agent's token is revoked due to the sanctions flag. |

---

## 8. Media — Content Moderation System

**Agents:** Intake Agent, Content Analysis Agent, Policy Check Agent, Action Agent, Appeal Agent

| # | Component | Scenario |
|---|-----------|----------|
| C1 | Ephemeral Identity | A user reports a post. A Content Analysis Agent launches with SPIFFE ID `spiffe://moderation/analysis/report-44210`. When the user appeals the moderation decision, the platform can show exactly which agent instance reviewed the content, what tools it used, and what it concluded. Accountability at the individual session level, not "our AI reviewed it." |
| C2 | Short-Lived Tokens | The Action Agent gets a 1-minute token to remove a post. It removes the post in 200ms. The token dies 59.8 seconds later. If the agent tries to remove another post (say, a bug causes it to loop), the token is scoped to a single content ID and dies quickly. No bulk removal authority from a single token. |
| C3 | Zero-Trust | The Content Analysis Agent calls `get_post_content(post_id="POST-88712")`. Broker validates: signature, expiry, revocation status, and `read:content:reported` scope. When the same agent later calls `get_user_profile(user_id="USR-2291")` to check the poster's history, that's a separate validation — does it have `read:user:history` scope? Each call stands alone. |
| C4 | Revocation | The Content Analysis Agent is reviewing a post and the Policy Check Agent determines it contains CSAM. The system immediately revokes the Content Analysis Agent's token (it should not continue accessing this content) and escalates to law enforcement tooling with completely different credentials. The Analysis Agent's next call to the content fails — the content is now locked to a different, more restricted access path. |
| C5 | Immutable Audit | A government regulator audits the platform's moderation practices. The audit trail for post POST-88712 shows: Intake received report → Analysis Agent read content → Policy Check Agent evaluated against 3 rules (hate speech: no, harassment: yes, spam: no) → Action Agent removed post → user was notified. Hash-chained: the platform can prove the decision was made through this exact process and no steps were altered. |
| C6 | Mutual Auth | The Action Agent tries to delegate notification authority to a User Communication Agent in a different region (EU data residency requirement). But the EU agent's registration expired last night due to a certificate rotation issue. Broker rejects. No user notification data (which includes PII) flows to an agent with expired registration. The ops team is alerted to re-register the EU agent. |
| C7 | Delegation | The Intake Agent has `read:content:*, read:reports:*` (it sees all reported content and report metadata). It delegates to the Content Analysis Agent with only `read:content:reported` — the Analysis Agent can read the specific reported post but not all content on the platform. It can't browse other users' posts, DMs, or unreported content. Its view is limited to what was reported. |
| C8 | Observability | The trust & safety operations dashboard shows: 2,847 reports in queue. Report #44210: Content Analysis Agent (done, read 1 post, 1 profile — both ALLOWED), Policy Check Agent (done, checked 3 rules, flagged harassment), Action Agent (active, TTL 0:42, scope: `write:content:moderate`). A denied enforcement card shows the Analysis Agent tried to read the poster's DMs — `read:content:private` scope DENIED. |

---

## Coverage Summary

Every domain naturally exercises all 8 components, but the *emphasis* differs:

| Domain | Strongest Components | Natural Tension |
|--------|---------------------|-----------------|
| Healthcare | C5 (HIPAA audit), C7 (need-to-know) | Patient privacy vs. care coordination |
| Financial Trading | C2 (ephemeral orders), C4 (risk revocation) | Speed vs. risk controls |
| Legal | C5 (evidence integrity), C7 (privilege boundaries) | Client confidentiality vs. collaboration |
| DevOps | C4 (incident revocation), C2 (blast radius) | Speed of response vs. access control |
| E-Commerce | C4 (fraud prevention), C5 (dispute resolution) | Fulfillment speed vs. fraud protection |
| Education | C7 (FERPA minimum necessary), C1 (accountability) | Personalization vs. student privacy |
| Supply Chain | C6 (cross-org trust), C7 (info compartmentalization) | Collaboration vs. competitive secrets |
| Media | C4 (content locking), C5 (regulatory audit) | Free expression vs. safety enforcement |

---

## Implications for Demo App

The demo doesn't need to implement all 8 domains. It needs to pick ONE domain where:

1. The user's text input naturally routes to different agents
2. Different agents need visibly different scopes
3. At least 2-3 preset scenarios exercise denial/revocation (not just happy path)
4. The credential lifecycle is the interesting part, not the LLM output
5. A non-technical observer can understand what's happening

Multiple domains above would work. The customer support domain from the old app checked all these boxes. But so would healthcare triage, incident response, or content moderation — any domain where "who can access what" is the core tension.
