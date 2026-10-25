"""Tests for the command line interface."""

import json
import subprocess
import sys

import pytest

from tolstack.cli import main

CHAIN_JSON = {
    "links": [
        {"name": "A", "nominal": 10.0, "tol_plus": 0.10, "tol_minus": 0.10, "sign": 1},
        {"name": "B", "nominal": 20.0, "tol_plus": 0.20, "tol_minus": 0.20, "sign": 1},
        {"name": "C", "nominal": 5.0, "tol_plus": 0.05, "tol_minus": 0.05, "sign": -1},
    ]
}


@pytest.fixture()
def chain_file(tmp_path):
    path = tmp_path / "chain.json"
    path.write_text(json.dumps(CHAIN_JSON), encoding="utf-8")
    return path


def test_cli_table_report(chain_file, capsys):
    assert main(["analyze", str(chain_file)]) == 0
    out = capsys.readouterr().out
    assert "Worst case" in out
    assert "25.3500" in out  # hand-computed worst-case maximum
    assert "24.6500" in out  # hand-computed worst-case minimum
    assert "RSS" in out
    assert "Monte Carlo" in out
    assert "Contributions" in out


def test_cli_json_output(chain_file, capsys):
    assert main(["analyze", str(chain_file), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worst_case"]["maximum"] == pytest.approx(25.35)
    assert payload["worst_case"]["minimum"] == pytest.approx(24.65)
    assert payload["rss"]["sigma"] == pytest.approx(0.07637626158259733)
    assert payload["contributions"][0]["name"] == "B"
    assert payload["monte_carlo"]["samples"] == 10000


def test_cli_spec_flags_add_out_of_spec(chain_file, capsys):
    rc = main(
        [
            "analyze",
            str(chain_file),
            "--spec-min",
            "24.65",
            "--spec-max",
            "25.35",
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["monte_carlo"]["spec_min"] == pytest.approx(24.65)
    assert payload["monte_carlo"]["out_of_spec_rate"] < 0.005


def test_cli_mc_flag_controls_sample_count(chain_file, capsys):
    assert main(["analyze", str(chain_file), "--mc", "500", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["monte_carlo"]["samples"] == 500


def test_cli_seed_flag_is_recorded(chain_file, capsys):
    assert main(["analyze", str(chain_file), "--seed", "7", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["monte_carlo"]["seed"] == 7


def test_cli_csv_input(tmp_path, capsys):
    csv_file = tmp_path / "chain.csv"
    csv_file.write_text(
        "name,nominal,tol_plus,tol_minus,sign\n"
        "A,10.0,0.10,0.10,1\n"
        "C,5.0,0.05,0.05,-1\n",
        encoding="utf-8",
    )
    assert main(["analyze", str(csv_file), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["worst_case"]["nominal"] == pytest.approx(5.0)


def test_cli_missing_file_returns_error(capsys):
    assert main(["analyze", "no/such/file.json"]) == 1
    assert "error" in capsys.readouterr().err


def test_cli_invalid_chain_returns_error(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"links": []}', encoding="utf-8")
    assert main(["analyze", str(bad)]) == 1
    assert "error" in capsys.readouterr().err


def test_cli_module_subprocess(chain_file):
    proc = subprocess.run(
        [sys.executable, "-m", "tolstack", "analyze", str(chain_file), "--json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["worst_case"]["maximum"] == pytest.approx(25.35)
