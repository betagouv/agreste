# PDF corpus token notes

Notes from exploring `medias/documents/` for RAG corpus sizing (Albert / ~3M token limit).

Date: 2026-08-20

## Corpus inventory

| Item | Count / size |
|------|----------------|
| Folder | `medias/documents/` (flat, no subfolders) |
| All files | 4668 |
| PDFs | 3289 |
| Other files | 1379 (xlsx, etc.) |
| Total size (all docs) | ~3.8 GB |
| PDF total size | ~3105 MB (~967 KB avg) |

## Token estimate (all PDFs)

Method:

1. Sample of **150 / 3289** PDFs with `pypdf` + `tiktoken` (`cl100k_base`) → ~**36.3M** tokens extrapolated.
2. Full pass with **PyMuPDF** text extract + chars÷2.90 estimate → ~**40.8M** tokens for the whole PDF set.
3. Top 150 candidates re-counted exactly with `tiktoken` `cl100k_base`.

| Metric (sample of 150) | Value |
|------------------------|------:|
| Mean tokens / PDF | ~11 000 |
| Median tokens / PDF | ~5 500 |
| Mean pages / PDF | ~11.4 |
| Empty extractable text | 0 % (in sample) |
| Est. total pages (extrapolated) | ~37 000 |
| Est. total tokens (sample extrapolate) | ~**36M** |
| Est. total tokens (full char-based pass) | ~**41M** |

Caveats:

- Counts are **extractable embedded text**, not OCR of image-only pages.
- French text often uses more tokens per character than English (hence chars÷4 underestimates vs `cl100k`).
- Other tokenizers (Albert, etc.) will differ slightly; order of magnitude is **tens of millions**.

### Order-of-magnitude (from earlier assessment notes)

French prose ≈ **400–600 tokens per dense page**:

| Average extractable text per publication | ≈ tokens for ~4000 docs |
|------------------------------------------|-------------------------|
| 1–2 short pages | ~2–5 M |
| 5 pages (typical bulletin) | ~8–12 M |
| 15+ pages / annex-heavy | **20 M+** |

Measured corpus is closer to the high end (~36–41 M).

## RAG budget (3M tokens)

- Full PDF text corpus **does not fit** a **3M** token collection.
- Top **100** PDFs alone ≈ **13.0M** tokens.
- Discarding only the largest files is not enough; need a curated subset, summaries, or title/summary-only (or a higher quota).

Easy wins spotted in the top list:

- Duplicate / near-duplicate GraphAgri vs GraFra integral editions (e.g. 2025 accessible + integral same token count).
- Near-duplicate `Rap*` pairs with different upload suffixes (`_fy5lDvO` / `_IQGOB4a`, etc.).
- Heavy series: **Ouv**, **GraFra\*Integral**, **Chd** (BAEA / comptes), **Dos** dossiers, **BilanConj**.

## Exclusion scenarios (count only — files not deleted)

Estimates use PyMuPDF extractable text + **chars ÷ 2.90**. Full corpus baseline ≈ **40.8M** tokens.

### 1. Drop all PDFs whose name starts with `Ira`

Infos Rapides: many files, relatively short → modest token savings.

| | PDFs | Est. tokens |
|--|-----:|------------:|
| Removed `Ira*` | 1489 | ~**6.4M** (~16% of corpus) |
| **Remaining** | **1800** | **~34.3M** |

Still far above a 3M budget.

### 2. Also drop selected large / redundant titles

On top of all `Ira*`, also exclude:

- `Ouv201701_cep-mondalim2030_01.pdf`
- `Ouv201001_Ouv201001.pdf`
- `Ouv201309_Ouv201309.pdf`
- `GraphAgri2025_accessible.pdf`
- Anything starting with `GraFra2025` **except** `GraFra2025Integral.pdf`

| | PDFs | Est. tokens |
|--|-----:|------------:|
| Removed `Ira*` | 1489 | ~6.4M |
| Removed named extras | 4 | ~1.4M |
| **Remaining** | **1796** | **~33.0M** (~11× a 3M limit) |

Breakdown of the named extras:

| Est. tokens | Pages | File |
|------------:|------:|------|
| 405 564 | 232 | `Ouv201701_cep-mondalim2030_01.pdf` |
| 413 195 | 314 | `Ouv201001_Ouv201001.pdf` |
| 275 196 | 234 | `Ouv201309_Ouv201309.pdf` |
| 289 876 | 224 | `GraphAgri2025_accessible.pdf` |

Note: the only `GraFra2025*` file in `medias/documents/` is `GraFra2025Integral.pdf`, so that rule removed nothing extra (Integral kept).

## Top 100 PDFs by tokens

Exact `cl100k_base` on PyMuPDF-extracted text. Ranked by tokens descending. Sum of top 100 ≈ **13 022 525** tokens.

| # | Tokens | Pages | File |
|---|-------:|------:|------|
| 1 | 366 245 | 232 | `Ouv201701_cep-mondalim2030_01.pdf` |
| 2 | 355 592 | 314 | `Ouv201001_Ouv201001.pdf` |
| 3 | 314 247 | 234 | `Ouv201309_Ouv201309.pdf` |
| 4 | 302 329 | 224 | `GraphAgri2025_accessible.pdf` |
| 5 | 302 329 | 224 | `GraFra2025Integral.pdf` |
| 6 | 300 417 | 208 | `Chd2106_Chd2106-BAEA2019_V2.pdf` |
| 7 | 296 922 | 245 | `Ouv201901_Cep-actifagri-2019.pdf` |
| 8 | 293 546 | 224 | `GraFra2024Integral.pdf` |
| 9 | 288 814 | 224 | `GraFra2023Integral.pdf` |
| 10 | 286 608 | 224 | `GraFra2022Integral.pdf` |
| 11 | 265 622 | 176 | `ChdAgr253_cd253-BAEA2016.pdf` |
| 12 | 262 803 | 224 | `GraFra2021Integral.pdf` |
| 13 | 261 376 | 220 | `GraFra2020Integral.pdf` |
| 14 | 255 666 | 251 | `ChdAal166_ChdAal166.pdf` |
| 15 | 255 636 | 212 | `GraFra2019Integral.pdf` |
| 16 | 220 723 | 135 | `ChdAgr225_ChdAgr225.pdf` |
| 17 | 208 243 | 140 | `ChdAal163_ChdAal163.pdf` |
| 18 | 179 157 | 112 | `ChdAgr235_ChdAgr235.pdf` |
| 19 | 172 396 | 199 | `Rap2409_Diversites-sociale-et-geographique-des-apprenants-des-ecoles-agro-et-v_fy5lDvO.pdf` |
| 20 | 172 396 | 199 | `Rap2409_Diversites-sociale-et-geographique-des-apprenants-des-ecoles-agro-et-v_IQGOB4a.pdf` |
| 21 | 172 005 | 240 | `Rap2508_rapport_final_Quels-avenirs-pour-le-secteur-bio-francais-d-ici-2040.pdf` |
| 22 | 171 072 | 307 | `Rap2406_Rapport_etude_Accord-de-libre-echange-entre-l-Union-europeenne-et-l-Inde.pdf` |
| 23 | 168 934 | 158 | `Dos3_Dos3.pdf` |
| 24 | 145 002 | 113 | `Dos13_Dos13.pdf` |
| 25 | 132 469 | 164 | `Pri2213_Insee_CourrierStatistiques-n7-0120221.pdf` |
| 26 | 132 469 | 164 | `Aut004-RA2020_Insee_CourrierStatistiques-n7-012022.pdf` |
| 27 | 129 876 | 111 | `ChdAal167_ChdAal167.pdf` |
| 28 | 129 136 | 128 | `Dos2501_Dossiers2025-1_Commission-des-Comptes-de-l-Agriculture-de-la-Nation_Vdef.pdf` |
| 29 | 124 283 | 151 | `Dos11_Dos11.pdf` |
| 30 | 124 151 | 143 | `Aut010_Iref-Transformation-agriculture-et-consommations-alimentaires.pdf` |
| 31 | 119 382 | 121 | `Dos7_Dos7.pdf` |
| 32 | 118 151 | 121 | `Dos33_Dos33.pdf` |
| 33 | 117 352 | 128 | `Dos38_Dos38.pdf` |
| 34 | 116 488 | 113 | `Dos15_Dos15.pdf` |
| 35 | 113 337 | 151 | `ChdAal171_ChdAal171.pdf` |
| 36 | 113 158 | 145 | `Rap2406-2_Etude-sur-les-outils-de-financement-innovants-pour-l-agriculture-fra_zy8Wnqi.pdf` |
| 37 | 113 158 | 145 | `Rap2406-2_Etude-sur-les-outils-de-financement-innovants-pour-l-agriculture-fra_uJ2dFb3.pdf` |
| 38 | 110 707 | 124 | `Rap2212_Prospective-des-besoins-de-l_agriculture-biologique-en-fertilisants-or_fhiWGWq.pdf` |
| 39 | 110 707 | 124 | `Rap2212_Prospective-des-besoins-de-l_agriculture-biologique-en-fertilisants-or_QZW1b91.pdf` |
| 40 | 102 188 | 130 | `Rap2202-1_Ceresco_-_Rapport_final_etude_freins_et_leviers_logistiques_legumineuses.pdf` |
| 41 | 102 043 | 122 | `Dos2002_Dossier2020-2_CCAN_3_Juillet_2020Definitive.pdf` |
| 42 | 102 023 | 119 | `Dos23_Dos23.pdf` |
| 43 | 100 699 | 138 | `Ouv201703_Ouv201703_Prospective_metiers.pdf` |
| 44 | 99 205 | 118 | `Dos10_Dos10.pdf` |
| 45 | 95 766 | 100 | `Dos4_Dos4.pdf` |
| 46 | 94 868 | 71 | `ChdAgr234_ChdAgr234.pdf` |
| 47 | 94 867 | 84 | `BilanConj2020_V2_Bilan_conjoncturel_2020_Site.pdf` |
| 48 | 94 167 | 124 | `Ouv201202_Ouv201202.pdf` |
| 49 | 93 858 | 71 | `ChdAgr197_ChdAgr197.pdf` |
| 50 | 92 990 | 69 | `ChdAgr224_ChdAgr224.pdf` |
| 51 | 92 784 | 105 | `ChdAgr229_ChdAgr229.pdf` |
| 52 | 92 640 | 80 | `BilanConj2021_Bilan_conjoncturel_2021_Definitif.pdf` |
| 53 | 92 281 | 73 | `Dos5_Dos5.pdf` |
| 54 | 91 982 | 108 | `Dos2203_CCAN-2022-3_decembre2022_VersionDefnitive.pdf` |
| 55 | 90 971 | 72 | `Dos9_Dos9.pdf` |
| 56 | 90 524 | 129 | `Dos2202_CCAN-2022-2_7juillet2022_Version_definitive.pdf` |
| 57 | 89 877 | 116 | `Dos2402_Dossiers2024-2_CCAN-Oct.2024_Vdef.pdf` |
| 58 | 89 860 | 69 | `Dos2_Dos2.pdf` |
| 59 | 89 776 | 79 | `ChdAgr231_ChdAgr231.pdf` |
| 60 | 88 830 | 130 | `Dos2302_CCAN-2023-2_6juillet2023_Version_definitive.pdf` |
| 61 | 88 755 | 78 | `BilanConj2019_conjBilan2019.pdf` |
| 62 | 88 236 | 71 | `Chd2001_cd2020-1_Rica1.pdf` |
| 63 | 88 024 | 72 | `ChdAgr247_cd247bspca150317.pdf` |
| 64 | 87 926 | 104 | `Dos2105_Dossier2021-5_CCAN_Definitif_dec2021_V2.pdf` |
| 65 | 87 654 | 97 | `Dos16_Dos16.pdf` |
| 66 | 87 040 | 72 | `Chd1902_cd2019-2bspca070319.pdf` |
| 67 | 86 306 | 84 | `DOC-CEP18_CEP_Document-de-travail_18_Images-et-representations-de-l-agriculture.PDF` |
| 68 | 86 237 | 137 | `Dos2104_Dossier2021-4_CCAN_Definitive_110821.pdf` |
| 69 | 84 526 | 115 | `Rap2311_Anticiper_-les-retraits-de-substances-phytopharmaceutiques-RAPPORT-FINAL-1.pdf` |
| 70 | 84 453 | 71 | `Dos14_Dos14.pdf` |
| 71 | 84 159 | 55 | `ChdAgr202_ChdAgr202.pdf` |
| 72 | 84 153 | 78 | `BilanConj2018_conjbilan2018.pdf` |
| 73 | 83 364 | 92 | `Dos2404_Dossiers2024-4_CCAN-dec2024_Vdef.pdf` |
| 74 | 83 331 | 69 | `Dos12_Dos12.pdf` |
| 75 | 83 285 | 70 | `BilanConj2022_Bilan_conjoncturel_2022.pdf` |
| 76 | 82 768 | 60 | `Dos24_Dos24.pdf` |
| 77 | 82 761 | 70 | `Chd2102_cd2021-2_Rica2019_v3.pdf` |
| 78 | 82 705 | 97 | `Dos40_dossier40_integral_1610.pdf` |
| 79 | 82 642 | 92 | `Dos2019-1_Dossier45_CCAN__janv2019.pdf` |
| 80 | 81 467 | 94 | `Dos2306_Dossiers2023-6__CCANdefinitif-dec2023.pdf` |
| 81 | 80 680 | 89 | `ChdAgr201_ChdAgr201.pdf` |
| 82 | 79 860 | 92 | `Dos201_Dossier2020-1_CCAN_Janvier2020v3.pdf` |
| 83 | 79 655 | 86 | `Dos41_dossier41_integral.pdf` |
| 84 | 79 116 | 106 | `Dos1904_Dossier2019_CCAN__juillet2019.pdf` |
| 85 | 79 023 | 98 | `Nes26A2_Nes26A2.pdf` |
| 86 | 78 715 | 79 | `ChdAgr222_ChdAgr222.pdf` |
| 87 | 78 491 | 72 | `ChdAgr240_cd240bspca.pdf` |
| 88 | 77 543 | 92 | `Dos203_Dossier2020-3_CCAN_Definitif_dec2020.pdf` |
| 89 | 76 643 | 72 | `ChdAgr233_ChdAgr233.pdf` |
| 90 | 75 689 | 72 | `ChdAgr228_ChdAgr228.pdf` |
| 91 | 75 594 | 72 | `ChdAgr221_ChdAgr221.pdf` |
| 92 | 74 986 | 73 | `ChdAgr218_ChdAgr218.pdf` |
| 93 | 74 884 | 96 | `ChdAal158_ChdAal158.pdf` |
| 94 | 73 939 | 71 | `ChdAgr216_ChdAgr216.pdf` |
| 95 | 73 759 | 94 | `ChdAal165_ChdAal165.pdf` |
| 96 | 73 706 | 74 | `ChdAgr203_ChdAgr203.pdf` |
| 97 | 72 841 | 73 | `ChdAgr214_ChdAgr214.pdf` |
| 98 | 72 178 | 65 | `ChdAgr220_ChdAgr220.pdf` |
| 99 | 70 480 | 103 | `Rap2403_Rapport-final-d-evaluation-FEAMP.pdf` |
| 100 | 69 848 | 74 | `ChdAgr210_ChdAgr210.pdf` |

## Related

- Broader search / Albert RAG assessment: [`docs/opensearch-search-assessment.md`](opensearch-search-assessment.md) (section on Albert RAG capacity).
- Machine-readable top-100 dump from the run: `/tmp/top100_pdf_tokens.csv` (local, ephemeral).
