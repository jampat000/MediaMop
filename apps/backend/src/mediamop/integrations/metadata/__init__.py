"""Metadata providers — the first external lookup surface in MediaMop.

Kept under ``integrations`` rather than inside Refiner because "what is this film's
original language" is not a Refiner question. Pruner and anything after it will want the
same answer, and a provider living inside one module is a provider the next module copies.
"""
