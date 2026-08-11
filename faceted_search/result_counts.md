# Faceted search result counts

Each facet value on the search page can show a **result count**, rendered as
`Name (N)` via the `facet_label` template tag. The count is stored as a
`result_count` attribute on the facet value object (theme, tag, author, …),
not as a separate context key.

## Meaning

For a value `V` in facet `F` (theme, collection, tag, author, …):

```text
result_count(V) = | pages matching q
                    AND all selected values outside F
                    AND F = {V} only |
```

In words: how many search hits that value alone accounts for, given the current
query and the selections from **other** facets. Other selections **inside** `F`
are ignored so sibling options stay comparable.

Facet selections still combine as elsewhere in search: **OR within a facet**,
**AND across facets**, then full-text `q` (facet selection applied before search).

## Example

Toy catalog under `q=blé`, with **Theme = Agriculture** and **Tag = Report**
selected (current header total: 2 pages).

| Theme value | Query used for the count               | Count |
| ----------- | -------------------------------------- | ----- |
| Agriculture | `q` ∧ Tag=Report ∧ Theme={Agriculture} | 2     |
| Forestry    | `q` ∧ Tag=Report ∧ Theme={Forestry}    | 1     |
| Livestock   | `q` ∧ Tag=Report ∧ Theme={Livestock}   | 1     |

| Tag value   | Query used for the count                    | Count |
| ----------- | ------------------------------------------- | ----- |
| Report      | `q` ∧ Theme=Agriculture ∧ Tag={Report}      | 2     |
| Data        | `q` ∧ Theme=Agriculture ∧ Tag={Data}        | 2     |
| Infographic | `q` ∧ Theme=Agriculture ∧ Tag={Infographic} | 0     |

Zero-count options are hidden from the sidebar unless they are currently
selected.

### Why ignore other selections in the same facet?

The count answers: “Under my other constraints, how big is **this** value?”

If Agriculture is already selected and we kept it while counting Forestry:

- **Distribution of current results** would show Forestry `(0)` even though
  Forestry+Report has hits.
- **OR-union after click** would show Forestry `(3)` (Agriculture ∪ Forestry),
  which users read as “3 Forestry results” even though only one page is
  Forestry.

So Forestry shows `(1)`: that value alone under the other facets. The page
header remains the source of truth for the current total (including OR unions
after a click).

## Implementation

| Piece | Role |
| ----- | ---- |
| `compute_facet_result_counts()` | Builds `{facet_name: {object_pk: count}}` for enabled facets |
| `_search_without_given_facet()` | `BaseSearchResults` for `q` + all selections except the facet being counted |
| `_page_pks_from_search_results()` | Extracts page pks from a `BaseSearchResults` (cheap path via `get_queryset` when available) |
| `_counts_for_m2m_field()` | `{related_pk: page_count}` for a direct M2M / parental M2M (themes, collections, authors, …) |
| `_counts_for_tags()` | Same for tags across `ContentPage` and `BlogEntryPage` |
| `_counts_for_sources()` | Same for organizations via `authors__organization` |
| `_set_result_counts()` | Sets `result_count` on objects from a `{pk: count}` map |
| `_drop_zeroes()` | Keeps items with `result_count > 0`, plus selected values |
| `_facet_values_with_counts_or_selected()` | Theme/collection options with a positive count or currently selected |
| `_attach_counts_to_tree()` | Sets `result_count` on each node in a facet-value tree (including ancestors) |
| `_facet_value_tree()` | Builds a theme/collection tree, with or without result counts |
| `_set_facet_selection_result_counts()` | Sets `result_count` on selected chip objects |
| `get_facet_context(..., query=...)` | Orchestrates sidebar context; assigns `selected_*` after counts are set |
| `facet_label` | Renders `Name (N)` in templates |

Counts are only computed when the search view passes a non-empty `query`.
Without `q`, option lists come from all live content under the site root and
have no `result_count`.

Aggregations clear Page’s default `path` ordering (`.order_by()`) before
`values(…).annotate(Count(…))`; otherwise `path` enters `GROUP BY` and every
count collapses to at most 1.

## Interactive demo

Open [`demo/facet_counts_demo.html`](demo/facet_counts_demo.html) in a browser
to click through the same semantics on a fixed toy catalog (no database).
The **Result count** mode matches production.
