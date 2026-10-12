"""Tiny synthetic test fixture only; no research training or accuracy claims."""
import json
from pathlib import Path

import pytest

from intelise_c1.baseline.data import DatasetError, inspect_rows, load_prepared, prepare, read_dataset, split_groups, validate_splits

FIXTURE = Path(__file__).parent / 'fixtures' / 'fr_nfr_test.jsonl'
PROVENANCE = FIXTURE.with_suffix('.provenance.json')


def rows():
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


@pytest.mark.parametrize('change', [
    {'text': ''}, {'text': ' \t\n'}, {'text': None}, {'label': 'UNKNOWN'},
    {'label': 'nfr'}, {'source_project_id': ''}, {'source_project_id': None},
    {'source_reference': ''}, {'example_id': ' padded '}, {'extra': True},
])
def test_invalid_annotations_rejected_without_inference(change):
    row = rows()[0]
    row.update(change)
    examples, report = inspect_rows([row])
    assert examples == [] and not report['valid']
    assert report['issues'][0]['code'] == 'invalid_example'


def test_missing_text_and_source_group_are_not_silently_assigned():
    row = rows()[0]
    del row['text']
    del row['source_project_id']
    examples, report = inspect_rows([row])
    assert examples == []
    assert set(report['issues'][0]['fields']) == {'text', 'source_project_id'}


@pytest.mark.parametrize('label, code', [('FR', 'duplicate_text'), ('NFR', 'conflicting_labels')])
def test_normalized_duplicates_and_conflicting_labels(label, code):
    row = rows()[0]
    duplicate = {**row, 'example_id': 'test-duplicate', 'text': '  USERS can   upload documents.  ', 'label': label, 'source_project_id': 'test-only-other-document'}
    _examples, report = inspect_rows([row, duplicate])
    assert not report['valid']
    assert report['issues'][0]['code'] == code
    assert report['duplicates'][0]['conflicting_labels'] == (label == 'NFR')
    assert 'text' not in report['issues'][0]


def test_counts_and_duplicate_ids():
    examples, report = read_dataset(FIXTURE)
    assert report['valid'] and len(examples) == 12
    assert report['class_counts'] == {'FR': 6, 'NFR': 6}
    assert report['source_project_count'] == 6
    _examples, report = inspect_rows([rows()[0], {**rows()[1], 'example_id': rows()[0]['example_id']}])
    assert report['issues'][0]['code'] == 'duplicate_example_ids'


def test_reproducible_group_split_and_saved_assignments(tmp_path):
    a = prepare(FIXTURE, PROVENANCE, tmp_path / 'a')
    b = prepare(FIXTURE, PROVENANCE, tmp_path / 'b')
    assert a['splits'] == b['splits']
    assert a['split_id'] == b['split_id'] and a['dataset_version'] == b['dataset_version']
    assert a['seed'] == 42 and a['purpose'] == 'test'
    groups = [set(a['sizes'][name]['source_groups']) for name in ['train', 'validation', 'test']]
    assert not groups[0] & groups[1] and not groups[0] & groups[2] and not groups[1] & groups[2]
    assert all(size['class_counts']['FR'] > 0 and size['class_counts']['NFR'] > 0 for size in a['sizes'].values())
    examples, loaded, provenance = load_prepared(tmp_path / 'a')
    assert loaded == a and len(examples) == 12 and provenance.purpose == 'test'
    with pytest.raises(FileExistsError):
        prepare(FIXTURE, PROVENANCE, tmp_path / 'a')


def test_leaky_assignments_and_missing_evaluation_classes_are_rejected():
    examples, _report = read_dataset(FIXTURE)
    # Every split has both labels, but pairs from the same documents are dispersed.
    leaky = {'train': [examples[i].example_id for i in [0, 3, 6, 9]],
             'validation': [examples[i].example_id for i in [1, 4, 7, 10]],
             'test': [examples[i].example_id for i in [2, 5, 8, 11]]}
    with pytest.raises(DatasetError, match='overlap'):
        validate_splits(examples, leaky)
    altered = [item.model_copy(update={'label': 'FR'}) for item in examples]
    with pytest.raises(DatasetError, match='both classes'):
        split_groups(altered)


def test_invalid_dataset_saves_report_without_split_or_model(tmp_path):
    source = tmp_path / 'bad.jsonl'
    source.write_text(json.dumps({**rows()[0], 'label': 'bad'}) + '\n')
    output = tmp_path / 'prepared'
    with pytest.raises(DatasetError, match='validation failed'):
        prepare(source, PROVENANCE, output)
    assert (output / 'validation_report.json').exists()
    assert not (output / 'manifest.json').exists()


def test_changed_annotations_invalidate_dataset_version(tmp_path):
    prepare(FIXTURE, PROVENANCE, tmp_path / 'prepared')
    path = tmp_path / 'prepared' / 'examples.jsonl'
    data = path.read_text().replace('Users can upload documents.', 'Users can create folders.')
    path.write_text(data)
    with pytest.raises(DatasetError, match='version'):
        load_prepared(path.parent)
