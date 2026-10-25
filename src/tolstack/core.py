"""Core tolerance stack-up (dimension chain) analysis.

Model
-----
A dimension chain is a list of links.  Each link has a nominal size, an
upper deviation ``tol_plus`` (>= 0) and a lower deviation ``tol_minus``
(>= 0), plus a direction sign: ``+1`` for an increasing link and ``-1``
for a decreasing link.  The closed (resulting) dimension is

    X = sum(sign_i * x_i)

Three complementary methods are provided:

* **Worst case (extreme value)** -- every link simultaneously at the
  extreme that pushes the closed dimension to its max / min.
* **RSS (root sum square)** -- statistical stack-up.  Each link's
  tolerance band is modelled as the +/-3 sigma interval of a normal
  distribution centred on the band midpoint, so
  ``sigma_i = (tol_plus_i + tol_minus_i) / 2 / 3`` and the closed
  dimension's sigma is ``sqrt(sum(sigma_i**2))`` (signs do not matter
  for variance).
* **Monte Carlo** -- random sampling from exactly the same per-link
  normal model, so its mean / std converge to the RSS values.  Uses a
  fixed seed by default so results are reproducible.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

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
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Link:
    """One link (component dimension) of a dimension chain.

    ``tol_plus`` / ``tol_minus`` are the magnitudes of the upper and
    lower deviations, both >= 0.  If ``tol_minus`` is omitted it defaults
    to ``tol_plus`` (symmetric tolerance).  ``sign`` is +1 (increasing
    link) or -1 (decreasing link).
    """

    name: str
    nominal: float
    tol_plus: float
    tol_minus: Optional[float] = None
    sign: int = 1

    def __post_init__(self) -> None:
        if self.tol_minus is None:
            object.__setattr__(self, "tol_minus", float(self.tol_plus))
        if not str(self.name).strip():
            raise ValueError("link name must not be empty")
        if self.tol_plus < 0:
            raise ValueError(
                f"link {self.name!r}: tol_plus must be >= 0, got {self.tol_plus}"
            )
        if self.tol_minus < 0:
            raise ValueError(
                f"link {self.name!r}: tol_minus must be >= 0, got {self.tol_minus}"
            )
        if self.sign not in (1, -1):
            raise ValueError(
                f"link {self.name!r}: sign must be +1 or -1, got {self.sign!r}"
            )

    # -- derived quantities -------------------------------------------------

    @property
    def upper(self) -> float:
        """Largest possible value of this link."""
        return self.nominal + self.tol_plus

    @property
    def lower(self) -> float:
        """Smallest possible value of this link."""
        return self.nominal - self.tol_minus

    @property
    def total_tolerance(self) -> float:
        """Full width of the tolerance band."""
        return self.tol_plus + self.tol_minus

    @property
    def half_tolerance(self) -> float:
        """Half width of the tolerance band."""
        return self.total_tolerance / 2.0

    @property
    def mean(self) -> float:
        """Midpoint of the tolerance band (statistical centre)."""
        return self.nominal + (self.tol_plus - self.tol_minus) / 2.0

    @property
    def sigma(self) -> float:
        """Standard deviation under the +/-3 sigma band assumption."""
        return self.half_tolerance / 3.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "name": self.name,
            "nominal": self.nominal,
            "tol_plus": self.tol_plus,
            "tol_minus": self.tol_minus,
            "sign": self.sign,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Link":
        try:
            return cls(
                name=str(data["name"]),
                nominal=float(data["nominal"]),
                tol_plus=float(data["tol_plus"]),
                tol_minus=(
                    float(data["tol_minus"]) if data.get("tol_minus") is not None else None
                ),
                sign=int(data.get("sign", 1)),
            )
        except KeyError as exc:
            raise ValueError(f"link is missing required field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid link definition {data!r}: {exc}") from exc


@dataclass
class Chain:
    """An ordered list of links forming one dimension chain."""

    links: List[Link] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.links = list(self.links)
        if not self.links:
            raise ValueError("chain must contain at least one link")

    def __len__(self) -> int:
        return len(self.links)

    def __iter__(self):
        return iter(self.links)

    @property
    def nominal(self) -> float:
        """Closed dimension at nominal link values."""
        return sum(link.sign * link.nominal for link in self.links)

    def to_dict(self) -> Dict:
        return {"links": [link.to_dict() for link in self.links]}

    @classmethod
    def from_dict(cls, data) -> "Chain":
        if isinstance(data, dict):
            raw_links = data.get("links")
            if raw_links is None:
                raise ValueError("chain JSON must contain a 'links' list")
        elif isinstance(data, list):
            raw_links = data
        else:
            raise ValueError("chain must be a JSON object with 'links' or a list")
        if not raw_links:
            raise ValueError("chain must contain at least one link")
        return cls([Link.from_dict(item) for item in raw_links])


# ---------------------------------------------------------------------------
# Worst case (extreme value method)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorstCaseResult:
    nominal: float  # closed dimension at nominal values
    minimum: float  # smallest possible closed dimension
    maximum: float  # largest possible closed dimension

    @property
    def total_tolerance(self) -> float:
        return self.maximum - self.minimum

    @property
    def deviation_plus(self) -> float:
        return self.maximum - self.nominal

    @property
    def deviation_minus(self) -> float:
        return self.nominal - self.minimum

    def to_dict(self) -> Dict[str, float]:
        return {
            "nominal": self.nominal,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "total_tolerance": self.total_tolerance,
            "deviation_plus": self.deviation_plus,
            "deviation_minus": self.deviation_minus,
        }


def worst_case(chain: Chain) -> WorstCaseResult:
    """Extreme-value stack-up: all links at their worst extreme at once."""
    maximum = 0.0
    minimum = 0.0
    for link in chain.links:
        if link.sign > 0:
            maximum += link.upper
            minimum += link.lower
        else:
            # Subtracting a link: the closed dimension is largest when
            # the subtracted link is smallest, and vice versa.
            maximum -= link.lower
            minimum -= link.upper
    return WorstCaseResult(nominal=chain.nominal, minimum=minimum, maximum=maximum)


# ---------------------------------------------------------------------------
# RSS (root sum square, statistical)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RSSResult:
    mean: float  # statistical centre of the closed dimension
    sigma: float  # standard deviation of the closed dimension
    nominal: float  # closed dimension at nominal values

    @property
    def lower_3sigma(self) -> float:
        return self.mean - 3.0 * self.sigma

    @property
    def upper_3sigma(self) -> float:
        return self.mean + 3.0 * self.sigma

    @property
    def total_tolerance(self) -> float:
        """Full +/-3 sigma width: sqrt(sum(total_tolerance_i**2))."""
        return 6.0 * self.sigma

    def to_dict(self) -> Dict[str, float]:
        return {
            "mean": self.mean,
            "sigma": self.sigma,
            "nominal": self.nominal,
            "lower_3sigma": self.lower_3sigma,
            "upper_3sigma": self.upper_3sigma,
            "total_tolerance": self.total_tolerance,
        }


def rss(chain: Chain) -> RSSResult:
    """Root-sum-square stack-up under the +/-3 sigma band model."""
    mean = sum(link.sign * link.mean for link in chain.links)
    variance = sum(link.sigma**2 for link in chain.links)
    return RSSResult(mean=mean, sigma=math.sqrt(variance), nominal=chain.nominal)


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MonteCarloResult:
    samples: int
    seed: int
    mean: float
    std: float
    minimum: float
    maximum: float
    percentiles: Dict[str, float]  # keys: "p1", "p5", "p50", "p95", "p99"
    spec_min: Optional[float] = None
    spec_max: Optional[float] = None
    out_of_spec_rate: Optional[float] = None  # fraction in [0, 1]

    @property
    def out_of_spec_ppm(self) -> Optional[float]:
        if self.out_of_spec_rate is None:
            return None
        return self.out_of_spec_rate * 1_000_000.0

    def to_dict(self) -> Dict:
        return {
            "samples": self.samples,
            "seed": self.seed,
            "mean": self.mean,
            "std": self.std,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "percentiles": dict(self.percentiles),
            "spec_min": self.spec_min,
            "spec_max": self.spec_max,
            "out_of_spec_rate": self.out_of_spec_rate,
            "out_of_spec_ppm": self.out_of_spec_ppm,
        }


def _percentile(sorted_samples: Sequence[float], pct: float) -> float:
    """Percentile with linear interpolation (like numpy's default)."""
    if not sorted_samples:
        raise ValueError("no samples")
    if len(sorted_samples) == 1:
        return float(sorted_samples[0])
    rank = (pct / 100.0) * (len(sorted_samples) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return float(sorted_samples[low])
    frac = rank - low
    return float(sorted_samples[low] * (1.0 - frac) + sorted_samples[high] * frac)


def monte_carlo(
    chain: Chain,
    samples: int = 10000,
    seed: int = 42,
    spec_min: Optional[float] = None,
    spec_max: Optional[float] = None,
) -> MonteCarloResult:
    """Monte Carlo stack-up using the same +/-3 sigma normal model as RSS."""
    if samples <= 0:
        raise ValueError(f"samples must be positive, got {samples}")
    if spec_min is not None and spec_max is not None and spec_min > spec_max:
        raise ValueError(f"spec_min ({spec_min}) must be <= spec_max ({spec_max})")

    rng = random.Random(seed)
    # Pre-extract per-link parameters to keep the sampling loop fast.
    params = [(link.mean, link.sigma, link.sign) for link in chain.links]
    results: List[float] = []
    for _ in range(samples):
        total = 0.0
        for mean, sigma, sign in params:
            total += sign * (rng.gauss(mean, sigma) if sigma > 0.0 else mean)
        results.append(total)
    results.sort()

    out_rate: Optional[float] = None
    if spec_min is not None or spec_max is not None:
        lo = -math.inf if spec_min is None else spec_min
        hi = math.inf if spec_max is None else spec_max
        bad = sum(1 for value in results if value < lo or value > hi)
        out_rate = bad / samples

    return MonteCarloResult(
        samples=samples,
        seed=seed,
        mean=statistics.fmean(results),
        std=statistics.stdev(results) if samples > 1 else 0.0,
        minimum=results[0],
        maximum=results[-1],
        percentiles={
            "p1": _percentile(results, 1),
            "p5": _percentile(results, 5),
            "p50": _percentile(results, 50),
            "p95": _percentile(results, 95),
            "p99": _percentile(results, 99),
        },
        spec_min=spec_min,
        spec_max=spec_max,
        out_of_spec_rate=out_rate,
    )


# ---------------------------------------------------------------------------
# Contribution ranking
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Contribution:
    name: str
    sign: int
    variance_share: float  # sigma_i^2 / sum(sigma^2) -- sensitivity ranking
    worst_case_share: float  # total_tol_i / sum(total_tol)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "sign": self.sign,
            "variance_share": self.variance_share,
            "worst_case_share": self.worst_case_share,
        }


def contributions(chain: Chain) -> List[Contribution]:
    """Per-link contribution shares, sorted by variance share descending."""
    total_variance = sum(link.sigma**2 for link in chain.links)
    total_wc = sum(link.total_tolerance for link in chain.links)
    ranked = []
    for link in chain.links:
        ranked.append(
            Contribution(
                name=link.name,
                sign=link.sign,
                variance_share=(link.sigma**2 / total_variance) if total_variance > 0 else 0.0,
                worst_case_share=(link.total_tolerance / total_wc) if total_wc > 0 else 0.0,
            )
        )
    ranked.sort(key=lambda c: c.variance_share, reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Combined analysis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisResult:
    chain: Chain
    worst_case: WorstCaseResult
    rss: RSSResult
    monte_carlo: MonteCarloResult
    contributions: List[Contribution]

    def to_dict(self) -> Dict:
        return {
            "links": [link.to_dict() for link in self.chain.links],
            "worst_case": self.worst_case.to_dict(),
            "rss": self.rss.to_dict(),
            "monte_carlo": self.monte_carlo.to_dict(),
            "contributions": [c.to_dict() for c in self.contributions],
        }


def analyze(
    chain: Chain,
    spec_min: Optional[float] = None,
    spec_max: Optional[float] = None,
    mc_samples: int = 10000,
    seed: int = 42,
) -> AnalysisResult:
    """Run worst-case, RSS, Monte Carlo and contribution analysis at once."""
    return AnalysisResult(
        chain=chain,
        worst_case=worst_case(chain),
        rss=rss(chain),
        monte_carlo=monte_carlo(
            chain, samples=mc_samples, seed=seed, spec_min=spec_min, spec_max=spec_max
        ),
        contributions=contributions(chain),
    )
