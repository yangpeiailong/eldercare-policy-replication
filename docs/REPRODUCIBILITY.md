# Reproducibility notes

| Paper output | Input and transformation |
| --- | --- |
| Figure 1 and Table 1 | Reported corpus-flow counts: 16,908 retrieved, 571 exact title-and-body duplicates removed, 16,337 retained, and 5,322 main candidates. The 5,322 include 912 specialized, 47 implementation/process, and 4,363 broader candidates with measure cues. Boundary and reserve records are excluded from the main analysis. |
| Figure 2 | `overall_category_rates.csv`: broader group, common local text, baseline candidate scope, nine service categories and three periods. |
| Figure 3 | `overall_annual_rates.csv`: broader group, three focal categories, 2011–2022. |
| Table 2 and Figure 4 | `verification_sensitivity.csv` and `verification_standardized.csv`: broader group, 2015–2018 vs 2019–2022. `verification_common_strata.csv` supplies common-stratum counts and weights; `verification_annual_joint.csv` supplies yearly counts. |
| Figure 5 | Baseline conditional denominators and joint counts in `verification_sensitivity.csv`; proximity split in `verification_joint_counts.csv`. Earlier: 1/78, 0 same fragment and 1 separate. Later: 57/154, 31 same fragment and 26 separate. |

CSV files use UTF-8. Labels from the analysis are retained, including the broader group `综合文件含措施线索`. Mention rates are percentages; standardized differences are percentage points. `documents` counts the applicable denominator, not the number of matches. The data provenance file records SHA-256 checksums. The supplied dictionary matches the lexicon digest in the original verification manifest.

## Local analysis with the original corpus

Use an isolated copy of the original research tree if rerunning; the original scripts write results and logs. Copy `code/config.example.json` to an untracked `code/config.json`, and set `research_root` to the local research tree. Put the exact supplied lexicon in the configured content directory as `lexicon_v01.json`. The minimum analysis starting point is `data/analysis/policy_patterns/results/connected_main_analysis.jsonl`. With that file and the lexicon in place:

```shell
python code/analyze_overall_content.py --config code/config.json
python code/verify_content_findings.py --config code/config.json
```

The first command writes profiles, summaries and its manifest. The second verifies its input hashes against that manifest before producing sensitivity, common-stratum and co-presence outputs. Keep those output folders local: the scripts also produce document-level records, evidence excerpts and logs.

To reconstruct the connected main input, `build_expanded_corpus.py` needs the V03 screening ledger and embedded evidence under `results/screening_v03`, plus the V05 core texts under the configured baseline results directory. `connect_corpus_texts.py` then reads the expanded registry and the original record JSONL (pass `--input` explicitly). The earlier screening and baseline scripts are preserved for inspection; the original recovery inputs, retrieval process and dataset snapshot are not bundled. Use the original local inputs rather than substituting a new download from a changing database.

The archived analysis tests use synthetic fixtures. Run them with `python -m unittest discover -s code -p "test_*.py"`. Passing these tests does not certify an end-to-end rerun on the original corpus.
