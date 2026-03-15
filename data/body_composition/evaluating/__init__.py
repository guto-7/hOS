"""
body_composition.evaluating — Stage 3: Clinical evaluation engine.

Produces domain scores, phenotype detection, and cross-reference signals
from Stage 2 (flagged + ranged) markers.
"""

from .evaluator import evaluate, EvaluationResult

__all__ = ["evaluate", "EvaluationResult"]
