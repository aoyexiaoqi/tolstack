"""Tests for the core stack-up mathematics.

Reference chain used by many tests (all expectations computed by hand):

    A: nominal 10, +/-0.10, sign +1
    B: nominal 20, +/-0.20, sign +1
    C: nominal  5, +/-0.05, sign -1

Closed dimension nominal = 10 + 20 - 5 = 25.
Worst case: max = 10.10 + 20.20 - 4.95 = 25.35
            min =  9.90 + 19.80 - 5.05 = 24.65
            total spread = 0.20 + 0.40 + 0.10 = 0.70
RSS: half-tolerances 0.10 / 0.20 / 0.05 ->
     sqrt(0.10^2 + 0.20^2 + 0.05^2) = sqrt(0.0525) = 0.229129 (3 sigma)
     sigma = sqrt(0.0525) / 3 = 0.0763763
Variance shares: A 0.0100/0.0525, B 0.0400/0.0525, C 0.0025/0.0525.
"""

import math

import pytest

from tolstack import (
    Chain,
    Link,
    analyze,
    contributions,
    monte_carlo,
    rss,
    worst_case,
)


def abc_chain() -> Chain:
    return Chain(
        [
            Link("A", 10.0, 0.10),
            Link("B", 20.0, 0.20),
            Link("C", 5.0, 0.05, sign=-1),
        ]
    )


# ---------------------------------------------------------------------------
# Link basics
# ---------------------------------------------------------------------------


def test_link_defaults_symmetric_and_positive_sign():
    link = Link("A", 10.0, 0.1)
    assert link.tol_minus == pytest.approx(0.1)
    assert link.sign == 1


def test_link_derived_quantities_asymmetric():
    # Band [9.9, 10.3]: midpoint 10.1, half width 0.2, sigma = 0.2/3.
    link = Link("D", 10.0, 0.3, 0.1)
    assert link.upper == pytest.approx(10.3)
    assert link.lower == pytest.approx(9.9)
    assert link.total_tolerance == pytest.approx(0.4)
    assert link.half_tolerance == pytest.approx(0.2)
    assert link.mean == pytest.approx(10.1)
    assert link.sigma == pytest.approx(0.2 / 3)


def test_negative_tol_plus_rejected():
    with pytest.raises(ValueError):
        Link("X", 1.0, -0.1)


def test_negative_tol_minus_rejected():
    with pytest.raises(ValueError):
        Link("X", 1.0, 0.1, -0.05)


def test_invalid_sign_rejected():
    with pytest.raises(ValueError):
        Link("X", 1.0, 0.1, sign=0)
    with pytest.raises(ValueError):
        Link("X", 1.0, 0.1, sign=2)


def test_empty_chain_rejected():
    with pytest.raises(ValueError):
        Chain([])
    with pytest.raises(ValueError):
        Chain.from_dict({"links": []})


# ---------------------------------------------------------------------------
# Worst case
# ---------------------------------------------------------------------------


def test_chain_nominal():
    assert abc_chain().nominal == pytest.approx(25.0)


def test_worst_case_limits_hand_computed():
    result = worst_case(abc_chain())
    assert result.maximum == pytest.approx(25.35)
    assert result.minimum == pytest.approx(24.65)
    assert result.total_tolerance == pytest.approx(0.70)
    assert result.deviation_plus == pytest.approx(0.35)
    assert result.deviation_minus == pytest.approx(0.35)


def test_worst_case_single_asymmetric_link():
    result = worst_case(Chain([Link("D", 10.0, 0.3, 0.1)]))
    assert result.maximum == pytest.approx(10.3)
    assert result.minimum == pytest.approx(9.9)
    assert result.deviation_plus == pytest.approx(0.3)
    assert result.deviation_minus == pytest.approx(0.1)


def test_worst_case_negative_sign_uses_opposite_extreme():
    # Closed = -x with x in [9.9, 10.3] -> closed in [-10.3, -9.9].
    result = worst_case(Chain([Link("D", 10.0, 0.3, 0.1, sign=-1)]))
    assert result.nominal == pytest.approx(-10.0)
    assert result.maximum == pytest.approx(-9.9)
    assert result.minimum == pytest.approx(-10.3)


def test_worst_case_two_links_asymmetric():
    # D in [9.9, 10.3] (+1), E in [3.9, 4.1] (-1):
    # max = 10.3 - 3.9 = 6.4 ; min = 9.9 - 4.1 = 5.8
    chain = Chain([Link("D", 10.0, 0.3, 0.1), Link("E", 4.0, 0.1, sign=-1)])
    result = worst_case(chain)
    assert result.nominal == pytest.approx(6.0)
    assert result.maximum == pytest.approx(6.4)
    assert result.minimum == pytest.approx(5.8)


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------


def test_rss_hand_computed():
    result = rss(abc_chain())
    assert result.mean == pytest.approx(25.0)
    assert result.sigma == pytest.approx(math.sqrt(0.0525) / 3)
    assert result.upper_3sigma == pytest.approx(25.0 + math.sqrt(0.0525))
    assert result.lower_3sigma == pytest.approx(25.0 - math.sqrt(0.0525))
    assert result.total_tolerance == pytest.approx(2 * math.sqrt(0.0525))


def test_rss_asymmetric_link_mean_shift():
    # Band midpoint shifts the statistical mean to 10.1.
    result = rss(Chain([Link("D", 10.0, 0.3, 0.1)]))
    assert result.mean == pytest.approx(10.1)
    assert result.sigma == pytest.approx(0.2 / 3)
    assert result.nominal == pytest.approx(10.0)


def test_rss_is_tighter_than_worst_case():
    chain = abc_chain()
    assert rss(chain).total_tolerance < worst_case(chain).total_tolerance


# ---------------------------------------------------------------------------
# Contributions
# ---------------------------------------------------------------------------


def test_contributions_variance_shares_hand_computed():
    shares = {c.name: c.variance_share for c in contributions(abc_chain())}
    assert shares["A"] == pytest.approx(0.0100 / 0.0525)
    assert shares["B"] == pytest.approx(0.0400 / 0.0525)
    assert shares["C"] == pytest.approx(0.0025 / 0.0525)


def test_contributions_worst_case_shares_hand_computed():
    shares = {c.name: c.worst_case_share for c in contributions(abc_chain())}
    assert shares["A"] == pytest.approx(0.2 / 0.7)
    assert shares["B"] == pytest.approx(0.4 / 0.7)
    assert shares["C"] == pytest.approx(0.1 / 0.7)


def test_contributions_sum_to_one():
    ranked = contributions(abc_chain())
    assert sum(c.variance_share for c in ranked) == pytest.approx(1.0)
    assert sum(c.worst_case_share for c in ranked) == pytest.approx(1.0)


def test_contributions_ranked_by_variance_descending():
    ranked = contributions(abc_chain())
    assert [c.name for c in ranked] == ["B", "A", "C"]


def test_zero_tolerance_link_contributes_nothing():
    chain = Chain([Link("A", 10.0, 0.1), Link("RIGID", 5.0, 0.0)])
    ranked = {c.name: c for c in contributions(chain)}
    assert ranked["RIGID"].variance_share == 0.0
    assert ranked["RIGID"].worst_case_share == 0.0
    assert ranked["A"].variance_share == pytest.approx(1.0)
    assert worst_case(chain).total_tolerance == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Monte Carlo (fixed seed, tolerance bands -- never exact equality)
# ---------------------------------------------------------------------------


def test_monte_carlo_mean_and_std_match_rss_within_bands():
    result = monte_carlo(abc_chain(), samples=20000, seed=42)
    assert result.mean == pytest.approx(25.0, abs=0.01)
    expected_sigma = math.sqrt(0.0525) / 3
    assert result.std == pytest.approx(expected_sigma, rel=0.08)


def test_monte_carlo_reproducible_with_same_seed():
    first = monte_carlo(abc_chain(), samples=2000, seed=7)
    second = monte_carlo(abc_chain(), samples=2000, seed=7)
    assert first.mean == second.mean
    assert first.std == second.std
    assert first.percentiles == second.percentiles


def test_monte_carlo_different_seed_gives_different_result():
    first = monte_carlo(abc_chain(), samples=2000, seed=7)
    second = monte_carlo(abc_chain(), samples=2000, seed=8)
    assert first.mean != second.mean


def test_monte_carlo_percentiles_ordered_and_centred():
    result = monte_carlo(abc_chain(), samples=20000, seed=42)
    pct = result.percentiles
    assert pct["p1"] < pct["p5"] < pct["p50"] < pct["p95"] < pct["p99"]
    assert pct["p50"] == pytest.approx(25.0, abs=0.01)
    # P1 / P99 sit near mean -/+ 2.326 sigma under the normal model.
    sigma = math.sqrt(0.0525) / 3
    assert pct["p1"] == pytest.approx(25.0 - 2.326 * sigma, abs=0.02)
    assert pct["p99"] == pytest.approx(25.0 + 2.326 * sigma, abs=0.02)


def test_monte_carlo_out_of_spec_near_zero_for_wide_spec():
    # Spec equal to the worst-case limits = +/-4.58 sigma -> almost never out.
    result = monte_carlo(
        abc_chain(), samples=20000, seed=42, spec_min=24.65, spec_max=25.35
    )
    assert result.out_of_spec_rate is not None
    assert result.out_of_spec_rate < 0.005
    assert result.out_of_spec_ppm == pytest.approx(result.out_of_spec_rate * 1e6)


def test_monte_carlo_out_of_spec_high_for_tight_spec():
    # Spec of +/-0.01 around the mean = +/-0.13 sigma -> ~90% out of spec.
    result = monte_carlo(
        abc_chain(), samples=20000, seed=42, spec_min=24.99, spec_max=25.01
    )
    assert result.out_of_spec_rate > 0.80


def test_monte_carlo_no_spec_means_no_rate():
    result = monte_carlo(abc_chain(), samples=100, seed=1)
    assert result.out_of_spec_rate is None
    assert result.out_of_spec_ppm is None


def test_monte_carlo_invalid_samples_rejected():
    with pytest.raises(ValueError):
        monte_carlo(abc_chain(), samples=0)
    with pytest.raises(ValueError):
        monte_carlo(abc_chain(), samples=-5)


def test_monte_carlo_inverted_spec_rejected():
    with pytest.raises(ValueError):
        monte_carlo(abc_chain(), samples=10, spec_min=26.0, spec_max=25.0)


# ---------------------------------------------------------------------------
# Combined analysis + serialisation
# ---------------------------------------------------------------------------


def test_analyze_bundles_all_methods():
    result = analyze(abc_chain(), spec_min=24.65, spec_max=25.35, mc_samples=1000, seed=3)
    assert result.worst_case.maximum == pytest.approx(25.35)
    assert result.rss.sigma == pytest.approx(math.sqrt(0.0525) / 3)
    assert result.monte_carlo.samples == 1000
    assert result.monte_carlo.out_of_spec_rate is not None
    assert len(result.contributions) == 3


def test_chain_dict_round_trip():
    chain = abc_chain()
    clone = Chain.from_dict(chain.to_dict())
    assert clone.nominal == pytest.approx(chain.nominal)
    assert [link.to_dict() for link in clone.links] == [
        link.to_dict() for link in chain.links
    ]


def test_analysis_dict_is_json_serializable():
    import json

    payload = analyze(abc_chain(), mc_samples=100, seed=1).to_dict()
    text = json.dumps(payload)
    restored = json.loads(text)
    assert restored["worst_case"]["maximum"] == pytest.approx(25.35)
    assert restored["contributions"][0]["name"] == "B"
