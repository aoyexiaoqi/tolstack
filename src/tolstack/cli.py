"""Command line interface: ``tolstack analyze chain.json [options]``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from .core import AnalysisResult, analyze
from .io import load_chain

__all__ = ["main", "format_report"]


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def format_report(result: AnalysisResult) -> str:
    """Render an analysis result as a human-readable text report."""
    wc = result.worst_case
    rs = result.rss
    mc = result.monte_carlo
    lines: List[str] = []
    lines.append(f"Dimension chain: {len(result.chain.links)} link(s)")
    for link in result.chain.links:
        lines.append(
            f"  {link.name:<16} nominal {_fmt(link.nominal):>10} "
            f"+{_fmt(link.tol_plus)}/-{_fmt(link.tol_minus)}  sign {link.sign:+d}"
        )
    lines.append("")
    lines.append(f"Closed dimension (nominal): {_fmt(wc.nominal)}")
    lines.append("")
    lines.append("Worst case (extreme value):")
    lines.append(f"  Range:        [{_fmt(wc.minimum)}, {_fmt(wc.maximum)}]")
    lines.append(
        f"  Deviations:   +{_fmt(wc.deviation_plus)} / -{_fmt(wc.deviation_minus)}"
        f"  (total tolerance {_fmt(wc.total_tolerance)})"
    )
    lines.append("")
    lines.append("RSS (root sum square, +/-3 sigma model):")
    lines.append(f"  Mean:         {_fmt(rs.mean)}   sigma: {_fmt(rs.sigma)}")
    lines.append(
        f"  +/-3 sigma:   [{_fmt(rs.lower_3sigma)}, {_fmt(rs.upper_3sigma)}]"
        f"  (total tolerance {_fmt(rs.total_tolerance)})"
    )
    lines.append("")
    lines.append(f"Monte Carlo (n={mc.samples}, seed={mc.seed}):")
    lines.append(f"  Mean:         {_fmt(mc.mean)}   std: {_fmt(mc.std)}")
    lines.append(f"  Range:        [{_fmt(mc.minimum)}, {_fmt(mc.maximum)}]")
    pct = mc.percentiles
    lines.append(
        "  Percentiles:  "
        f"P1 {_fmt(pct['p1'])}  P5 {_fmt(pct['p5'])}  P50 {_fmt(pct['p50'])}  "
        f"P95 {_fmt(pct['p95'])}  P99 {_fmt(pct['p99'])}"
    )
    if mc.out_of_spec_rate is not None:
        lo = "-inf" if mc.spec_min is None else _fmt(mc.spec_min)
        hi = "+inf" if mc.spec_max is None else _fmt(mc.spec_max)
        lines.append(
            f"  Spec [{lo}, {hi}]: out-of-spec {mc.out_of_spec_rate * 100:.4f}%"
            f" ({mc.out_of_spec_ppm:,.0f} ppm)"
        )
    lines.append("")
    lines.append("Contributions (ranked by variance share):")
    lines.append(f"  {'#':<4}{'link':<18}{'variance %':>12}{'worst-case %':>14}")
    for rank, contrib in enumerate(result.contributions, start=1):
        lines.append(
            f"  {rank:<4}{contrib.name:<18}"
            f"{contrib.variance_share * 100:>12.2f}"
            f"{contrib.worst_case_share * 100:>14.2f}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tolstack",
        description="Tolerance stack-up (dimension chain) analysis: "
        "worst case, RSS and Monte Carlo.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze_parser = subparsers.add_parser(
        "analyze", help="analyze a dimension chain file (.json or .csv)"
    )
    analyze_parser.add_argument("chain", help="path to the chain file (.json or .csv)")
    analyze_parser.add_argument(
        "--spec-min", type=float, default=None, help="lower spec limit of the closed dimension"
    )
    analyze_parser.add_argument(
        "--spec-max", type=float, default=None, help="upper spec limit of the closed dimension"
    )
    analyze_parser.add_argument(
        "--mc", type=int, default=10000, help="Monte Carlo sample count (default: 10000)"
    )
    analyze_parser.add_argument(
        "--seed", type=int, default=42, help="Monte Carlo random seed (default: 42)"
    )
    analyze_parser.add_argument(
        "--json", action="store_true", help="emit the full result as JSON"
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "analyze":
        try:
            chain = load_chain(args.chain)
            result = analyze(
                chain,
                spec_min=args.spec_min,
                spec_max=args.spec_max,
                mc_samples=args.mc,
                seed=args.seed,
            )
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(format_report(result))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
