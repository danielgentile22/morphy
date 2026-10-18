"""morphy data TUI, the puller (PRD #233).

Full data lifecycle from one terminal app: pull → preprocess → verify →
deploy. A thin shell over the unchanged headless ``fetch`` + ``preprocess``
libraries and ``deploy.sh``.
"""
