"""tolstack -- tolerance stack-up (dimension chain) analysis.

Worst-case (extreme value), RSS (root sum square) and Monte Carlo
stack-up analysis with per-link contribution ranking.  Pure standard
library; no third-party runtime dependencies.
"""

from .core import (
    AnalysisResult,
    Chain,
    Contribution,
    Link,
    MonteCarloResult,
    RSSResult,
    WorstCaseResult,
    analyze,
    contributions,
    monte_carlo,
    rss,
    worst_case,
)
from .io import load_chain

__version__ = "0.1.0"

__all__ = [
    "Link",
    "Chain",
    "WorstCaseResult",
    "RSSResult",
    "MonteCarloResult",
    "Contribution",
    "AnalysisResult",
    "worst_case",
    "rss",
    "monte_carlo",
    "contributions",
    "analyze",
    "load_chain",
    "__version__",
]
