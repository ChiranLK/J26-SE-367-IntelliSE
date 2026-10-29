"""Synthetic CSV checks; these fixtures are not evaluation results."""
import csv
import json
from hashlib import sha256

import pytest

from intelise_c1.baseline.data import DatasetError, load_prepared, prepare, read_dataset, validate_splits
from intelise_c1.baseline.dcai import REQUIRED_COLUMNS, import_dcai
from test_baseline_data import rows, PROVENANCE


def write_csv(path, texts):
    with path.open('w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=sorted(REQUIRED_COLUMNS))
        writer.writeheader()
        for text, label in texts:
            writer.writerow({'Requirement': text, 'Type': label, 'Specific_Type': 'original',
                             'Security_Category': 'unchanged', 'Dataset_Name': 'collection-not-project'})


def test_lossless_import_quarantine_duplicates_conflicts_and_metadata(tmp_path):
    source = tmp_path / 'dcai.csv'
    write_csv(source, [('Members can book.\n', 'FR'), (' MEMBERS  CAN book. ', 'FR'),
                       ('Conflicting text.', 'FR'), ('conflicting TEXT.', 'NFR'),
                       ('No target.', '#N/A'), ('Response within 2 seconds.', 'NFR'),
                       ('  ', 'FR'), ('Unsupported label.', 'other')])
    raw = source.read_bytes()
    report = import_dcai(source, tmp_path / 'imported')
    assert report['raw_rows'] == 8 and report['usable_rows'] == 2
    assert report['final_class_counts'] == {'FR': 1, 'NFR': 1}
    assert report['disposition_counts'] == {'included': 2, 'same_label_duplicate': 1,
                                          'conflicting_labels': 2, 'invalid_label': 2, 'invalid_text': 1}
    assert report['genuine_project_ids_recovered'] == 0
    assert report['raw_sha256'] == sha256(raw).hexdigest()
    assert source.read_bytes() == (tmp_path / 'imported' / 'dcai.csv').read_bytes() == raw
    examples, valid = read_dataset(tmp_path / 'imported' / 'examples.jsonl', allow_missing_projects=True)
    assert valid['valid'] and examples[0].text == 'Members can book.\n'
    assert all(item.source_project_id is None for item in examples)
    metadata = [json.loads(line) for line in (tmp_path / 'imported' / 'source_metadata.jsonl').read_text().splitlines()]
    assert len(metadata[0]['source_records']) == 2
    assert metadata[0]['source_records'][1]['original_fields']['Requirement'] == ' MEMBERS  CAN book. '
    assert metadata[0]['source_records'][0]['original_fields']['Dataset_Name'] == 'collection-not-project'
    quarantine = [json.loads(line) for line in (tmp_path / 'imported' / 'quarantine.jsonl').read_text().splitlines()]
    assert len(quarantine) == 6
    assert any(item['original_fields']['Type'] == '#N/A' for item in quarantine)
    with pytest.raises(FileExistsError):
        import_dcai(source, tmp_path / 'imported')


def test_normalized_fallback_is_explicit_reproducible_and_not_project_separated(tmp_path):
    source = tmp_path / 'unknown-projects.jsonl'
    data = [{**row, 'source_project_id': None} for row in rows()]
    source.write_text(''.join(json.dumps(row) + '\n' for row in data))
    with pytest.raises(DatasetError, match='validation failed'):
        prepare(source, PROVENANCE, tmp_path / 'rejected')
    a = prepare(source, PROVENANCE, tmp_path / 'a', grouping='normalized_text')
    b = prepare(source, PROVENANCE, tmp_path / 'b', grouping='normalized_text')
    assert a['splits'] == b['splits']
    assert a['group_key'] == 'normalized_text'
    assert a['evaluation_method'] == 'stratified_normalized_text_holdout'
    assert 'unseen-project' in a['grouping_limitation']
    examples, manifest, _ = load_prepared(tmp_path / 'a')
    assert manifest == a and all(item.source_project_id is None for item in examples)
    hashes = [set(size['source_groups']) for size in a['sizes'].values()]
    assert all(not hashes[i] & hashes[j] for i in range(3) for j in range(i))
    a.pop('grouping_limitation')
    (tmp_path / 'a' / 'manifest.json').write_text(json.dumps(a))
    with pytest.raises(DatasetError, match='limitation'):
        load_prepared(tmp_path / 'a')


def test_identical_text_cannot_cross_even_different_genuine_project_splits(tmp_path):
    source = tmp_path / 'examples.jsonl'
    source.write_text(''.join(json.dumps(row) + '\n' for row in rows()))
    manifest = prepare(source, PROVENANCE, tmp_path / 'prepared')
    examples, _ = read_dataset(source)
    training_id = manifest['splits']['train'][0]
    test_id = manifest['splits']['test'][0]
    text = next(item.text for item in examples if item.example_id == training_id)
    altered = [item.model_copy(update={'text': '  ' + text.upper() + '  '}) if item.example_id == test_id else item for item in examples]
    with pytest.raises(DatasetError, match='Identical normalized'):
        validate_splits(altered, manifest['splits'])


def test_project_column_is_not_silently_discarded(tmp_path):
    source = tmp_path / 'projects.csv'
    source.write_text('Requirement,Type,Specific_Type,Security_Category,Dataset_Name,Project_ID\nText,FR,,,Collection,real-project\n')
    with pytest.raises(DatasetError, match='Project metadata'):
        import_dcai(source, tmp_path / 'imported')
    assert not (tmp_path / 'imported').exists()
