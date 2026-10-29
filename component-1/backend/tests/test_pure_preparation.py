import csv
import json
from types import SimpleNamespace

import pytest

from intelise_c1.baseline.pure import prepare_pure, requirements, sha256


def test_xml_character_data_and_no_inferred_labels(tmp_path):
    source = tmp_path / "source.xml"
    source.write_text('<doc><req id="a">Only administrators <b>must not</b> delete &amp; archive.</req><p>Hello</p></doc>')
    assert requirements(source) == [("a", "Only administrators must not delete & archive.")]
    source.write_text('<doc><p>Not explicitly marked</p></doc>')
    assert requirements(source) == []


@pytest.mark.parametrize("content", ['<!DOCTYPE doc [<!ENTITY e "expanded">]><doc/>', '<doc><req>broken'])
def test_untrusted_or_malformed_xml_rejected(tmp_path, content):
    path = tmp_path / "bad.xml"
    path.write_text(content)
    with pytest.raises(Exception):
        requirements(path)


def test_preparation_preserves_sources_separates_suggestions_and_flags_overlap(tmp_path, monkeypatch):
    documents, xml, prepared, model = [tmp_path / name for name in ("docs", "xml", "dcai", "model")]
    for directory in (documents, xml, prepared, model):
        directory.mkdir()
    (documents / "original.pdf").write_bytes(b"unchanged original")
    (xml / "a.xml").write_text('<doc><req id="r1">Only admins can delete.</req><req>  ONLY  ADMINS CAN DELETE. </req><req>Search takes two seconds.</req><req> </req></doc>')
    (xml / "empty.xml").write_text('<doc><p>No req tags</p></doc>')
    (model / "pipeline.skops").write_bytes(b"test artifact")
    old = tmp_path / "old.csv"
    old.write_text('Requirement,Type,Dataset_Name\nOnly admins can delete.,FR,source family\nOnly admins can delete.,NFR,another family\n')
    (prepared / "manifest.json").write_text(json.dumps({"split_id": "saved-split", "splits": {"test": ["old-id"]}}))
    (prepared / "examples.jsonl").write_text(json.dumps({"example_id": "old-id", "text": "Only admins can delete."}) + "\n")
    seen = []

    class Model:
        def predict(self, texts):
            seen.extend(texts)
            return ["FR"] * len(texts)

    monkeypatch.setattr("intelise_c1.baseline.model.load_artifact", lambda path: (Model(), SimpleNamespace(model_version="existing-model")))
    raw, output = tmp_path / "snapshot", tmp_path / "output"
    args = dict(documents=documents, xml=xml, raw_output=raw, output=output, dcai_csv=old, dcai_prepared=prepared, model_dir=model)
    before = sha256(model / "pipeline.skops")
    result = prepare_pure(**args)
    assert result["unique_candidates"] == 2
    assert result["redundant_duplicate_occurrences"] == 1
    assert result["excluded_blocks"] == 1
    assert result["new_unique_candidates"] == 1
    assert result["overlap_split_counts"] == {"test": 1}
    assert result["pure_accuracy"] is None and result["pure_macro_f1"] is None
    assert result["reviewed_labels"] == 0 and result["new_model_trained"] is False
    assert seen == ["Only admins can delete.", "Search takes two seconds."]
    matches = json.loads((output / "dcai_overlap.json").read_text())
    assert matches[0]["conflicting_labels"] is True
    assert matches[0]["eligible_as_new_independent_data"] is False
    candidates = [json.loads(line) for line in (output / "unlabelled_candidates.jsonl").read_text().splitlines()]
    assert all("label" not in item and item["source_project_id"] is None for item in candidates)
    with (output / "annotation_review.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2 and all(row["reviewed_label"] == "" for row in rows)
    with (output / "new_only_review.csv").open(newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 1
    assert (raw / "documents/original.pdf").read_bytes() == (documents / "original.pdf").read_bytes()
    assert (raw / "xml/a.xml").read_bytes() == (xml / "a.xml").read_bytes()
    assert sha256(model / "pipeline.skops") == before
    with pytest.raises(ValueError, match="already exists"):
        prepare_pure(**args)
