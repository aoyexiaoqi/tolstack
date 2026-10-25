"""Tests for JSON / CSV chain loading."""

import pytest

from tolstack import load_chain
from tolstack.io import load_csv_text, loads_json

JSON_OBJECT = """
{
  "links": [
    {"name": "A", "nominal": 10.0, "tol_plus": 0.10, "tol_minus": 0.10, "sign": 1},
    {"name": "B", "nominal": 20.0, "tol_plus": 0.20, "sign": 1},
    {"name": "C", "nominal": 5.0, "tol_plus": 0.05, "tol_minus": 0.05, "sign": -1}
  ]
}
"""

JSON_LIST = """
[
  {"name": "A", "nominal": 10.0, "tol_plus": 0.10},
  {"name": "C", "nominal": 5.0, "tol_plus": 0.05, "sign": -1}
]
"""

CSV_FULL = """name,nominal,tol_plus,tol_minus,sign
A,10.0,0.10,0.10,1
B,20.0,0.20,0.20,1
C,5.0,0.05,0.05,-1
"""

CSV_MINIMAL = """name,nominal,tol_plus
A,10.0,0.10
C,5.0,0.05
"""


def test_load_json_object_format():
    chain = loads_json(JSON_OBJECT)
    assert len(chain) == 3
    assert chain.nominal == pytest.approx(25.0)
    # B omitted tol_minus -> defaults to tol_plus (symmetric).
    assert chain.links[1].tol_minus == pytest.approx(0.20)


def test_load_json_bare_list_format():
    chain = loads_json(JSON_LIST)
    assert len(chain) == 2
    assert chain.nominal == pytest.approx(5.0)
    assert chain.links[0].sign == 1  # sign defaults to +1


def test_load_json_missing_field_rejected():
    with pytest.raises(ValueError):
        loads_json('{"links": [{"name": "A", "tol_plus": 0.1}]}')


def test_load_json_invalid_text_rejected():
    with pytest.raises(ValueError):
        loads_json("{not json")


def test_load_json_empty_links_rejected():
    with pytest.raises(ValueError):
        loads_json('{"links": []}')


def test_load_json_negative_tolerance_rejected():
    with pytest.raises(ValueError):
        loads_json('{"links": [{"name": "A", "nominal": 1.0, "tol_plus": -0.1}]}')


def test_load_csv_full_columns():
    chain = load_csv_text(CSV_FULL)
    assert len(chain) == 3
    assert chain.nominal == pytest.approx(25.0)
    assert chain.links[2].sign == -1


def test_load_csv_optional_columns_default():
    chain = load_csv_text(CSV_MINIMAL)
    assert chain.links[0].tol_minus == pytest.approx(0.10)
    assert chain.links[0].sign == 1
    assert chain.links[1].sign == 1


def test_load_csv_missing_required_column_rejected():
    with pytest.raises(ValueError):
        load_csv_text("name,tol_plus\nA,0.1\n")


def test_load_csv_bad_number_rejected():
    with pytest.raises(ValueError):
        load_csv_text("name,nominal,tol_plus\nA,ten,0.1\n")


def test_load_csv_no_rows_rejected():
    with pytest.raises(ValueError):
        load_csv_text("name,nominal,tol_plus\n")


def test_load_chain_from_files(tmp_path):
    json_file = tmp_path / "chain.json"
    json_file.write_text(JSON_OBJECT, encoding="utf-8")
    csv_file = tmp_path / "chain.csv"
    csv_file.write_text(CSV_FULL, encoding="utf-8")
    assert load_chain(json_file).nominal == pytest.approx(25.0)
    assert load_chain(csv_file).nominal == pytest.approx(25.0)


def test_load_chain_unsupported_extension_rejected(tmp_path):
    bad = tmp_path / "chain.txt"
    bad.write_text("whatever", encoding="utf-8")
    with pytest.raises(ValueError):
        load_chain(bad)


def test_load_chain_missing_file_raises():
    with pytest.raises(OSError):
        load_chain("definitely/not/a/real/file.json")


def test_example_files_agree_with_each_other():
    # The shipped JSON and CSV examples describe the same gap chain:
    # 50 (+1) - 30 (-1) - 19 (-1) = 1.0 nominal gap.
    from pathlib import Path

    examples = Path(__file__).resolve().parent.parent / "examples"
    json_chain = load_chain(examples / "gap_chain.json")
    csv_chain = load_chain(examples / "gap_chain.csv")
    assert json_chain.nominal == pytest.approx(1.0)
    assert csv_chain.nominal == pytest.approx(1.0)
    assert [link.to_dict() for link in json_chain.links] == [
        link.to_dict() for link in csv_chain.links
    ]
