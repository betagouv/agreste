# Search assessment for Agreste (Postgres FTS → OpenSearch)

Assessment notes from exploring faceted search ranking, PDF-heavy publications, synonyms/semantic search, and Scalingo options. **Target search engine going forward: OpenSearch** (not Elasticsearch 7.10). Elasticsearch is mentioned only for historical/license context.

## Table of contents

1. [Current state](#1-current-state)
2. [What we are optimizing for](#2-what-we-are-optimizing-for)
3. [Postgres FTS vs OpenSearch](#3-postgres-fts-vs-opensearch)
4. [Concepts](#4-concepts)
5. [Indexing publication PDFs](#5-indexing-publication-pdfs)
6. [Semantic search and Albert API](#6-semantic-search-and-albert-api)
7. [Adopting OpenSearch (Wagtail, local, Scalingo)](#7-adopting-opensearch-wagtail-local-scalingo)
8. [Recommended roadmap](#8-recommended-roadmap)
9. [Albert RAG as a full search replacement?](#9-albert-rag-as-a-full-search-replacement)

---

## 1. Current state

Search today is **Postgres full-text search** via [`config/settings.py`](../config/settings.py):

```python
WAGTAILSEARCH_BACKENDS = {
    "default": {
        "BACKEND": "wagtail.search.backends.database",
        "SEARCH_CONFIG": "french_unaccent",
    }
}
```

[`faceted_search/views.py`](../faceted_search/views.py) filters pages with facets, then calls `.search(query)`. Ranking is Postgres `SearchRank` (text relevance): mainly `title` (boost 2) and `body`. **Publication `date` is not part of the score** — only a `?year=` facet filter. Index refresh already exists (`just index` / weekly `update_index`).

No OpenSearch/Elasticsearch service in [`docker-compose.yml`](../docker-compose.yml) yet. Wagtail 7.2 ships `opensearch2` / `opensearch3` backends (and ES7/8/9).

---

## 2. What we are optimizing for

Agreste publications are typically: **title + short summary + date + metadata + content in an attached PDF**. Search that only hits title/summary is weak.

Product needs that go beyond “plain FTS”:

| Need | Why |
|------|-----|
| Index PDF text (interim dirty extract) | Recall for queries that only appear in the PDF |
| Relevance + recency | Recent bulletins should not lose to old verbose notes |
| Title ≫ summary ≫ PDF body | Avoid 200-page annexes dominating the SERP |
| Related vocabulary (`boeuf` ↔ `bovins`) | Synonyms first; semantic search later |
| Sovereign embeddings (optional) | DINUM Albert API instead of commercial APIs |

---

## 3. Postgres FTS vs OpenSearch

### Comparison

| Area | Postgres FTS (today) | OpenSearch |
|------|----------------------|------------|
| Relevance + other signals | `ts_rank` only; date needs custom SQL | `function_score` / decay for relevance + recency |
| Field boosts | Four Postgres weight levels (A–D) | Richer boosts, multi-match |
| Analyzers / synonyms | DB text-search config (`french_unaccent`) | App/`INDEX_SETTINGS`; easier to iterate |
| Fuzzy / suggest | Limited | Stronger tooling |
| Aggregations (facet counts) | Django after search ([`compute_facet_result_counts`](../faceted_search/facets.py)) | Native aggs if facet cost grows |
| Scale | Shares Postgres with CMS | Isolated search cluster |
| Ops / cost | Already paid | Addon (RAM/JVM), reindex discipline |
| Semantic / vectors | Via `pgvector` + external embeddings | k-NN (+ ML/neural plugins on Scalingo) |
| PDF extraction helper | App-side Tika/pypdf | App-side **or** `ingest-attachment` |

**Postgres still wins** for simplicity if you only need text match (or a light date nudge) and a small synonym list.

**OpenSearch pays off** for multi-signal ranking, PDF-heavy corpus at scale, synonyms iteration, and a path to hybrid lexical + semantic search on Scalingo.

### Why not Elasticsearch on Scalingo?

Managed Elasticsearch stops at **7.10.2** because Elastic changed licensing after 7.10 (SSPL). That blocks cloud providers from shipping newer ES as OSS. Amazon forked **OpenSearch**; Scalingo is [phasing ES out in favour of OpenSearch](https://scalingo.com/blog/introducing-opensearch-for-scalingo-database) (OpenSearch **2.x**, default ~2.19.3). ES 7.10 also lacks production approximate k-NN (arrived in ES 8). **Ignore Elasticsearch for new Agreste work.**

---

## 4. Concepts

### Analyzers

Pipelines that turn text into tokens (accents, stemming, stopwords, synonyms). They decide **what matches**. Ranking decides **order**. Today: Postgres `french_unaccent`. On OpenSearch: French analyzer + optional synonym filter.

### Aggregations

Server-side counts over the hit set (e.g. themes, years). **You choose** which aggs to run; nothing is automatic. Wagtail’s OS backend exposes simple `.facet("field")` for one `FilterField`. Current `faceted_search` already gets counts in Django — fine until it becomes slow.

### Ranking examples (when FTS alone is wrong)

1. Query `blé` — old verbose note outranks a short 2025 bulletin → need **recency**.
2. Query `prix du lait` — title match should beat table noise → **field boosts**.
3. Decay on publications only — don’t punish evergreen méthodologie pages.
4. PDF annex indexed — lower boost than title/summary.
5. Editorial “pin” — query-time boost (awkward on Postgres FTS).

### Synonyms (`boeuf` → `bovins`)

Neither FTS nor BM25 “understands” meaning. Stemming won’t link those roots.

1. **Synonym list** (best first step) — both backends; **OpenSearch is easier to iterate** (app config vs DB dictionaries).
2. **Query expansion** in Django before `.search()`.
3. **Semantic / vector search** — embeddings (heavier; see §6).

Synonyms are easy to wire, hard to curate (Agreste vocabulary).

### Wagtail and “type of search”

Wagtail abstracts the **engine** for its **lexical** contract (`.search()` → BM25/FTS). It does **not** auto-switch to semantic search when you attach OpenSearch. A custom backend *could* make `.search(q)` do neural/hybrid under the hood — same API shape, different wiring. Core Wagtail has **no built-in semantic search** ([roadmap](https://github.com/wagtail/roadmap/issues/119); ecosystem: [`wagtail-vector-index`](https://github.com/wagtail/wagtail-vector-index)).

---

## 5. Indexing publication PDFs

Nothing crawls linked Wagtail Documents into search automatically.

### Recommended interim: hidden field on `PublicationPage`

1. On publish / document change: extract PDF text (pypdf / pdfminer / Tika / later Albert OCR for scans).
2. Store in a non-displayed field, e.g. `pdf_text`.
3. `index.SearchField("pdf_text", boost=0.5)` (title/summary higher).
4. Works with **any** Wagtail backend (Postgres today, OpenSearch later).

### Dirty search extract vs clean user-facing HTML

**Final state:** publications expose **clean HTML** in the Wagtail page (PDF converted for reading). That is hard (columns, tables, figures).

**Search extract can stay dirtier:** flatten tables to text, drop charts, tolerate messy order/pagination noise, as long as recall is OK and title/summary stay boosted. Hidden-field DB size is a weak objection — that volume (or more) lands on the page when clean HTML ships. Interim: lossy extract → `pdf_text`. Final: search the visible body and drop the parallel dirty field. Prefer flattening table cells over dropping tables (many queries hit stats).

### OpenSearch `ingest-attachment`

Scalingo OpenSearch includes **`ingest-attachment`**. It runs **Apache Tika** on **Base64** bytes in an ingest pipeline and fills `attachment.content`. It does **not** find PDFs on pages, read S3, or sync Wagtail.

You still: discover Document → download → Base64 → index with `?pipeline=attachment` + metadata → reindex on change. **Removes app-side Tika**; does not remove the sync pipeline.

| | Hidden `pdf_text` + Wagtail search | OS ingest-attachment |
|--|------------------------------------|----------------------|
| Extraction | In Django | In OpenSearch |
| Search path | Stock `SearchField` | Custom indexer (usually) |
| Best when | First version / backend-agnostic | Already on OpenSearch, want Tika off the web dyno |

---

## 6. Semantic search and Albert API

### What semantic search is

Embed text → vectors → nearest neighbors. Same model for documents and queries. Lexical search matches words; semantic matches **nearby meanings**. Hybrid = both.

**Neither Postgres nor OpenSearch computes embeddings by itself.** An embedding model does; the store only holds vectors and runs k-NN.

### Who runs the model?

| Who | Role |
|-----|------|
| Django → API (prefer **Albert**) | Simplest; HTTP on index + search |
| Django / worker local model | More RAM/CPU |
| OpenSearch ML / neural-search | Cluster calls the model (Option 2 below) |
| Postgres | Never embeds — only `pgvector` |

### Albert API (DINUM / SIIAG)

Public-sector entry point: **[Albert API](https://ia.numerique.gouv.fr/outils-ia/albert-api/)** (OpenAI-compatible, SecNumCloud). “Plateforme de données” = data/RAG side (embeddings, OCR, RAG), not a CMS.

**Access:** [ALLiaNCE form](https://alliance.numerique.gouv.fr/albert/contacter-albert-api/) (~48h) · optional [Etalab contact](https://www.numerique.gouv.fr/offre-accompagnement/expertise-albert-ia-etat/).

**For Agreste:** embeddings for vectors; OCR for scans; optional RAG/chat later. Does **not** replace faceted `.search()`.

### Option 1 — Embed in Django, store in OpenSearch or pgvector

1. Albert embed(title+summary+pdf_text) on publish.
2. Write `knn_vector` (OpenSearch) or `vector(N)` (Postgres).
3. On search: Albert embed(q) → k-NN → page ids; optional hybrid with lexical.

OpenSearch does **not** auto-pick up Albert keys; your app orchestrates.

### Option 2 — OpenSearch calls Albert (ML Commons remote connector)

OpenSearch embeds at ingest and query via a **remote connector** to Albert. Not turnkey.

```text
Index { pdf_text } → text_embedding pipeline → remote model → Albert /v1/embeddings → knn_vector
Search neural { query_text } → same model via Albert → k-NN
```

**Steps:** trust Albert URL in `trusted_connector_endpoints_regex` · confirm Scalingo OS **egress** · create connector (`https://albert.api.etalab.gouv.fr/v1/embeddings`, OpenAI embedding [blueprint](https://github.com/opensearch-project/ml-commons/blob/main/docs/remote_inference_blueprints/openai_connector_embedding_blueprint.md)) · register/deploy remote model · ingest pipeline · knn index (correct **dimension**) · `neural` / hybrid search.

Still custom vs stock Wagtail `.search()`. Validate Albert JSON vs OpenSearch OpenAI pre/post processors. Scalingo RAG demos often use an **in-cluster** HF model; Albert is the same pattern with a remote URL ([Scalingo RAG tutorial](https://doc.scalingo.com/tutorials/opensearch-rag), [neural search tutorial](https://docs.opensearch.org/latest/tutorials/vector-search/neural-search-tutorial/)).

| | Option 1 Django→Albert | Option 2 OS→Albert |
|--|------------------------|--------------------|
| Who calls Albert? | App | OpenSearch ML |
| Config | App + env | Cluster connector/pipeline/mapping |
| Wagtail `.search()` | Custom for vectors | Custom (`neural`) |
| When attractive | Always a good default | Once OpenSearch is already in prod |

---

## 7. Adopting OpenSearch (Wagtail, local, Scalingo)

### Wagtail wiring (lexical)

1. Depend on OpenSearch client compatible with Wagtail’s `opensearch2` (or `opensearch3`) backend.
2. `WAGTAILSEARCH_BACKENDS` → that backend; `URLS` from `OPENSEARCH_URL` / Scalingo var.
3. Keep `update_index`; French analyzer via `INDEX_SETTINGS`.
4. Recency: custom query compiler (`function_score` / gauss on `date`) — not automatic.
5. Facets: existing Django counts should still work; watch latency (many `.search()` calls).

Public API stays `.search()` + facets for **lexical** search.

### Local

Add OpenSearch 2.x to Docker Compose, expose 9200, set URL, `update_index`. Fallback: if URL unset, keep database backend for contributors without Docker OS.

### Scalingo

```bash
scalingo --app <app> addons-add opensearch <plan>
```

Plugins available out of the box include `ingest-attachment`, `opensearch-knn`, `opensearch-ml`, `opensearch-neural-search` ([plugin list](https://doc.scalingo.com/databases/opensearch/guides/using-plugins)). Reindex on mapping changes; size the plan for JVM + vectors; review-app strategy (per-app addon vs shared cluster).

### Effort (order of magnitude)

| Slice | Rough effort |
|-------|----------------|
| OpenSearch lexical backend + local Docker + Scalingo | ~1 week |
| French analyzer parity + recency boost | +1–2 days |
| Hidden `pdf_text` extract + SearchField | +few days (pipeline quality) |
| Synonym list (curation-heavy) | ongoing |
| Semantic (Albert + k-NN, Option 1 or 2) | +1–2 weeks spike → prod |

---

## 8. Recommended roadmap

1. **Now (Postgres):** hidden `pdf_text` on publications + `SearchField` (lower boost); optional small synonym dictionary; optional date tie-break if needed.
2. **Next:** OpenSearch on Scalingo for lexical search (synonyms, recency `function_score`, French analyzer); keep or rehome PDF text via `SearchField` or ingest-attachment.
3. **Later:** Albert embeddings + hybrid search (Option 1 first; Option 2 if you want embedding off the web dyno).
4. **End state:** clean HTML bodies replace dirty `pdf_text` for both reading and search.

### Verdict

| Question | Answer |
|----------|--------|
| Stay on Postgres? | Yes for a first PDF+synonym spike |
| Search engine on Scalingo? | **OpenSearch**, not Elasticsearch 7.10 |
| PDF first version? | Dirty extract → hidden field → Wagtail search |
| Semantic? | Albert for vectors; store in OS k-NN or pgvector; not stock `.search()` |
| Biggest early win? | Indexing PDF text + title/summary boosts; then recency |


## 9. Albert RAG as a full search replacement?

Albert’s [RAG guide](https://guides.ia.numerique.gouv.fr/albert-api/guides/rag) lets you upload files into a **private collection** (extract → chunk → embed → vector store), then `POST /v1/search` (semantic / exact / hybrid) and optionally chat over retrieved chunks. Max **20 MB per file** (PDF/TXT/HTML/MD).

### Capacity rough check (~4000 publications + PDFs)

Token counts depend on extracted text, not page count. Order-of-magnitude (French prose ≈ **400–600 tokens per dense page**):

| Average extractable text per publication | ≈ tokens for 4000 docs |
|------------------------------------------|-------------------------|
| 1–2 short pages | ~2–5 M |
| 5 pages (typical bulletin) | ~8–12 M |
| 15+ pages / annex-heavy | **20 M+** |

A **3 M token** collection budget is tight or insufficient once PDFs are in. Title+summary only might fit; **full PDF corpus likely does not**. Confirm the exact limit via `GET /v1/me/info` / Albert quotas — published “vector store” storage rows are often still “en construction.” Ask Albert for a higher production quota if you pursue this.

### Should Agreste replace faceted search with Albert RAG?

**No as the sole search UI.** RAG/search-chunks and your current product solve different jobs:

| | Faceted Wagtail search | Albert RAG (`/v1/search` + optional chat) |
|--|------------------------|-------------------------------------------|
| Output | Ranked **pages** (URLs, dates, themes) | Ranked **chunks** / LLM answer |
| Facets (theme, year, …) | First-class | Weak / metadata_filters only if you push metadata |
| Browse + pagination | Yes | Not a SERP |
| Latency / cost per query | Low (your index) | Embed + (optional) LLM; rate limits RPM/RPD |
| Sync | Your CMS | Re-upload on every PDF/page change |
| Determinism | Stable listing | Semantic drift; chat can hallucinate if misused |

**Good fit:** optional “Posez une question” assistant on top of Agreste (Albert collection = curated subset or summaries).  
**Keep:** classic search + facets for finding publications.  
**Bridge:** use Albert **embeddings** (or `/v1/search` only) as a retrieval signal, but render **Wagtail pages** — don’t replace the SERP with chat.

