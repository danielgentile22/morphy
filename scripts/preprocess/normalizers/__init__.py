"""Normalizer implementations.

This package's modules self-register via the @register_normalizer decorator
when imported. Don't import them here at package level — use preprocess.registry
to load everything together so missing-module errors surface cleanly.
"""
