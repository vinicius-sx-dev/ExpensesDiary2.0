# Smart insights advisor — implementation and activation status

Base: `feat/pluggy-integration`, b761112b82d4971d03b1ef014ac517c463842701.

## What works without external credentials

- Manual entries, statement confirmation and Pluggy mock share `make_entry` and context validation.
- Granular private niches supplement existing public category slugs, preserving budgets. Context: fast food, subscriptions, self-declared impulse purchases, beauty, tattoo, travel. Aportes remain `finance_contributions`, never a duplicate consumption expense.
- Explicit merchant/address/time columns in CSV and tables extracted from supported PDF/DOCX are retained encrypted. Free-text bank descriptions are never treated as merchant names. Missing context remains unknown. XML/OFX retain the existing conservative date/amount extraction; they do not guess merchants from NAME/MEMO.
- Strategies respect essential expenses and require three occurrences across three weeks in an 84-day window. Impulse/unplanned travel require explicit user classification. Subscriptions require matching merchant across at least two months. Evidence is association, not proof of causality.
- Goal projections use integer cents, three completed calendar months of recorded contributions (including zero-record months), no interest, and the chosen contribution day (1–28). Incomplete financial history is disclosed. The 30-day reference frequency limits occurrence replacements. Different scenarios are alternatives, not additive allocations. Each targets one user-selected goal.
- No known contribution baseline means no finite “days earlier” claim. Completed goals do not produce savings suggestions.
- Food recipes distinguish cost consumed, cost per portion, and the sample mean of full packages needed. Leftovers must be used to realize the projected saving. No recipe price means no food savings/acceleration claim. For non-food alternatives, the user must explicitly supply replacement/cancellation costs (zero is allowed); this is a conditional simulation, not a verified cancellation offer.
- Groq receives only an allowlisted generic strategy plus calculated savings/days, and is used only on explicit simulation requests. The validated prose is separate from numerical results, with deterministic fallback. No free-text goal titles, raw statements, merchant, city, address, store links or account IDs are sent to Groq.

## Price collection: external dependency, not activated

**There is no live retailer/price source connected in this commit.** The application intentionally returns “Preços locais indisponíveis”. `RegionalFeed` is an implemented bounded HTTPS consumer of a contract, not a claim of a working Menor Preço integration or automatic internet research.

The Menor Preço terms explicitly prohibit using its services in another app/site (clause 3.3(g)); authorization is needed before building such an adapter:
https://gpptu.github.io/docs/MPRECO/TERMO_COND_USO/

Next decision: select a licensed price provider or obtain retailer/CELEPAR authorization. Do not enable a scraping service, invent product prices, or treat search-engine snippets/LLM output as verified prices. Google Places alone does not provide grocery item prices.

The feed URL/token are server configuration only. The feed receives only a municipality code (no user identifier or exact location). It must return a JSON array (max 200 observations / 256 KB) with these fields, and implement source verification upstream:

| Field | Required semantics |
|---|---|
| ingredient | `bread`, `cheese`, `tomato`, `oats`, `milk`, `banana`; verified equivalent product |
| product | Product name, brand/packaging details |
| store_id | Stable physical store identifier; not one identifier per SKU |
| municipality | Paraná IBGE municipality code for the offer, not headquarters |
| unit | `kg`, `l`, or `unit` |
| package_quantity | Decimal quantity in that normalized unit |
| package_price_cents | Positive integer price of the full package |
| source_url | HTTPS evidence URL; never fetched by the advisor or passed to Groq |
| observed_at / valid_until | Aware ISO timestamps; evidence must be observed within 24h and still valid |
| conditions | Only `regular_in_store` accepted; exclude club, coupon, quantity-tied and online-only offers |
| available | Current availability verified by provider |

At least two distinct stores for every recipe ingredient in the selected municipality are required. The newest quote per store is used. Values are rounded up only at monetary outputs. The UI presents a municipal sample mean with sources; it does not claim the same price in an unobserved store or a purchasable basket from one store. No inference that an online national price is a local physical price. Availability/rights/coverage must be validated with the chosen supplier before activation.

Municipality picker dataset: 399 Paraná municipalities, IBGE codes, vendored from https://github.com/kelvins/municipios-brasileiros (see data attribution). The official API was unavailable from the execution environment during implementation: https://servicodados.ibge.gov.br/api/v1/localidades/estados/41/municipios . No GPS permission is required in this release. Places integration remains a future adapter; the app uses municipal coverage rather than claiming nearby store discovery.

## Encryption migration and deployment

1. Stop API and scheduled jobs. Back up the database and the existing `STATEMENT_ENCRYPTION_KEY` independently and verify restore procedures. Do not generate a different key for existing previews.
2. Install locked dependencies. Run `alembic upgrade head` with the existing Fernet key. Migration 004 fails before DDL if no key exists; it adds fields, encrypts and authenticates each goal/report, then clears plaintext legacy columns to inert sentinels. It is restartable after interrupted MySQL DDL. Do not run the old application on this schema.
3. New goal properties transparently read encrypted title, motivation, target, deadline, monthly plan and contribution day. Reports also encrypt their copies. New context, preferences, advice history and push tokens are encrypted and bound to owner/purpose/record key. Ledger amounts, dates and base categories remain plaintext as previously agreed. Existing descriptions are not copied to new context.
4. Backups/binlogs made before migration can still contain plaintext: apply your existing backup retention/access policy. Do not run a downgrade that recreates plaintext; restore a verified backup if rollback is required.
5. Deploy the API and mobile together. Run `python -m app.maintenance` daily (advisor retention: 90 days). Missing/incorrect encryption keys fail closed.

## Push activation

- Install a development/production build on a real phone. Expo Go/web are not the supported push test surface.
- Configure an EAS project and `EXPO_PUBLIC_EAS_PROJECT_ID`. Supply `GOOGLE_SERVICES_FILE` in the Android build environment and configure FCM v1/APNs credentials with EAS. Never commit these files.
- Enable enhanced push security in Expo, configure server-only `EXPO_ACCESS_TOKEN`, then `ADVISOR_PUSH_ENABLED=true`.
- Run `python -m app.advisor.notifications` every 15 minutes via cron/systemd or your scheduler. The API process alone does not run the job.
- User selects a goal, enables permission and generates a useful simulation. The job schedules the highest savings candidate from recent simulations two hours before an observed weekday/hour. No inferred hour from date-only data. Default quiet hours 20–09, at most two attempts per rolling seven days, at least 24h apart. Only one registered device per user receives each alert to prevent duplicate notifications.
- Before sending, revalidate consent/goal, current pattern, prices and savings. Expired jobs are cancelled. Only active authenticated sessions receive pushes. Logout revokes delivery eligibility; a new login must register again.
- Persistent claims happen before network sending: ambiguous outcomes are **not retried**, choosing missed delivery over duplicate alerts. Expo tickets/receipts are checked; invalid devices are removed. `provider_accepted` is not proof the device displayed the alert.
- Lockscreen/Expo payload is generic and contains no goal name, amount or store. Opening the app navigates to Dicas for current analysis. Android force-stop can prevent notifications until reopening; OS delivery is never guaranteed.

## API

Authenticated routes: `/advisor/regions`, `/advisor/preferences` GET/PUT, `/advisor/patterns?goal_id=`, `/advisor/simulate` POST, `/advisor/history` GET, `/advisor/history/{id}` DELETE, `/advisor/devices` POST/DELETE. Financial endpoints retain ownership checks, session/device binding, rate limits and safe error responses. Advisor calculations reject oversized history rather than silently truncating. Responses have no-store caching policy.

## Validation scope

Automated tests cover money/calendar scenarios, missing/stale/wrong-region quotes, package costs, ciphertext tenant/record binding, legacy migration, explicit parser metadata, PII exclusion from LLM payload, ownership checks and notification claims/throttling. Runtime activation still requires a chosen authorized price source and real-device FCM/APNs testing. No production migration or real notification was performed by this implementation session.
