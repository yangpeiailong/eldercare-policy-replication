# Changing service agendas in Chinese eldercare policy documents

Replication materials for a descriptive analysis of eldercare-related policy documents in China. The repository separates figure reproduction from rerunning the analysis on the original corpus.

## Reproduce the figures from the supplied tables

From this directory, with Python 3.10 or later:

```shell
python -m pip install -r requirements.txt
python code/plot_manuscript_figures.py --results data/aggregates --output reproduced_figures
```

This rebuilds Figures 1–5 as PNG, PDF and SVG. The first figure diagrams the workflow and records the reported corpus counts. Figures 2–5 read the archived aggregate outputs. Table 2 uses the baseline rows for the three focal outcomes in `verification_standardized.csv`; sample counts and the comparison stages are also described in the workflow. The Figure 5 input contains two grouped rows in place of the document-level joint-mention list. See [the output map](docs/REPRODUCIBILITY.md) and [file checksums](data/provenance.json).

## Rerun the analysis with local inputs

The original screening, corpus assembly, passage extraction, dictionary analysis and verification scripts are in `code/`. The exact analysis dictionary is in `config/`. This route requires the authors' local data and intermediate files; it cannot be run end to end from this repository alone. The source corpus is not included. See [the local-input instructions](docs/REPRODUCIBILITY.md) for the required files and the commands.

No API credentials, raw policy texts, individual document records, draft manuscript, or local machine paths are included. The published aggregates describe the selected database corpus. They are not population estimates or measures of policy implementation.
