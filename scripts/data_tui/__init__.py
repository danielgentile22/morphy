"""Pilot Data TUI — *the* puller since the Qt app's retirement (PRD #233/#240).

Full data lifecycle from one terminal app: pull → preprocess → verify →
deploy. A thin shell over the unchanged headless ``fetch`` + ``preprocess``
libraries and ``deploy.sh``.
"""
