"""Mechanical fits on test-only data in temporary directories, never research models."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from intelise_c1.baseline.data import DatasetError, prepare, read_dataset
from intelise_c1.baseline.model import BaselineConfig, evaluate, fit_pipeline, freeze, load_artifact, metrics, save_artifact, train
from intelise_c1.services.classifier import ClassifierUnavailable, LocalClassifier

pytestmark = pytest.mark.skipif(importlib.util.find_spec('sklearn') is None or importlib.util.find_spec('skops') is None, reason='Install requirements-baseline.lock for mechanical baseline tests')
FIXTURE = Path(__file__).parent / 'fixtures' / 'fr_nfr_test.jsonl'
PROVENANCE = FIXTURE.with_suffix('.provenance.json')


@pytest.fixture
def mechanical_artifact(tmp_path):
    manifest = prepare(FIXTURE, PROVENANCE, tmp_path / 'prepared')
    examples, _report = read_dataset(FIXTURE)
    by_id = {item.example_id: item for item in examples}
    training = [by_id[key] for key in manifest['splits']['train']]
    config = BaselineConfig()
    pipeline = fit_pipeline(training, config)
    artifact = tmp_path / 'test-model'
    save_artifact(pipeline, artifact, manifest, config)
    return pipeline, artifact, examples, manifest


def test_pipeline_fit_train_only_and_save_load(mechanical_artifact):
    pipeline, directory, examples, manifest = mechanical_artifact
    loaded, metadata = load_artifact(directory, allow_test=True)
    assert metadata.purpose == 'test'
    assert metadata.model_identifier == 'tfidf-logistic-regression'
    assert metadata.label_mapping == {'FR': 'Functional Requirement', 'NFR': 'Non-Functional Requirement'}
    assert metadata.dependencies['scikit-learn']
    assert metadata.split_id == manifest['split_id']
    texts = [item.text for item in examples]
    assert loaded.predict(texts).tolist() == pipeline.predict(texts).tolist()
    # Actual tokens exclusive to held-out source documents must not enter IDF/vocabulary.
    vectorizer = loaded.named_steps['tfidf']
    analyze = vectorizer.build_analyzer()
    training_ids = set(manifest['splits']['train'])
    training_terms = {term for item in examples if item.example_id in training_ids for term in analyze(item.text)}
    heldout_terms = {term for item in examples if item.example_id not in training_ids for term in analyze(item.text)} - training_terms
    assert heldout_terms and not heldout_terms & set(vectorizer.vocabulary_)
    before = dict(vectorizer.vocabulary_)
    loaded.predict(texts)
    assert vectorizer.vocabulary_ == before
    assert loaded.named_steps['classifier'].class_weight == 'balanced'


def test_fixture_cannot_train_research_model_or_serve_api(mechanical_artifact, tmp_path):
    _pipeline, directory, _examples, _manifest = mechanical_artifact
    with pytest.raises(DatasetError, match='Test fixtures cannot train'):
        train(tmp_path / 'prepared', tmp_path / 'research-model', BaselineConfig())
    assert not (tmp_path / 'research-model').exists()
    with pytest.raises(DatasetError, match='research-purpose'):
        load_artifact(directory)
    with pytest.raises(ClassifierUnavailable):
        LocalClassifier(directory).predict(['Any text'])
    with pytest.raises(DatasetError):
        freeze(directory)
    with pytest.raises(DatasetError):
        evaluate(tmp_path / 'prepared', directory)
    assert not (directory / 'test_metrics.json').exists()


@pytest.mark.parametrize('corruption', ['hash', 'versions', 'labels', 'symlink', 'types'])
def test_artifact_corruption_and_untrusted_types_rejected(mechanical_artifact, corruption, monkeypatch):
    _pipeline, directory, _examples, _manifest = mechanical_artifact
    path = directory / 'metadata.json'
    metadata = json.loads(path.read_text())
    if corruption == 'hash':
        metadata['model_version'] = '0' * 64
    elif corruption == 'versions':
        metadata['dependencies']['scikit-learn'] = 'wrong-version'
    elif corruption == 'labels':
        metadata['label_mapping'] = {'FR': 'Approved'}
    elif corruption == 'symlink':
        original = directory / 'pipeline.skops'
        renamed = directory.parent / 'external.skops'
        original.rename(renamed)
        original.symlink_to(renamed)
    else:
        import skops.io
        monkeypatch.setattr(skops.io, 'get_untrusted_types', lambda **kwargs: ['evil.CustomEstimator'])
    path.write_text(json.dumps(metadata))
    with pytest.raises(DatasetError):
        load_artifact(directory, allow_test=True)


def test_metric_structure_on_fixed_predictions_not_research_evaluation():
    examples, _report = read_dataset(FIXTURE)
    fixture = examples[:4]  # true label order FR,NFR,FR,NFR
    pipeline = Mock(predict=Mock(return_value=['FR', 'FR', 'FR', 'NFR']))
    report = metrics(pipeline, fixture)
    assert report['confusion_matrix']['values'] == [[2, 0], [1, 1]]
    assert report['per_class']['FR']['precision'] == pytest.approx(2 / 3)
    assert report['per_class']['NFR']['recall'] == .5
    assert report['macro_f1'] == pytest.approx((.8 + 2 / 3) / 2)
    assert report['examples'] == 4 and report['source_project_count'] == 2


def test_final_test_cannot_be_read_before_freeze(tmp_path, monkeypatch):
    # Mock control-flow check only; no fitted research model or evaluation results.
    from intelise_c1.baseline import model
    metadata = SimpleNamespace(dataset_version='dataset', split_id='split')
    manifest = {'purpose': 'research', 'dataset_version': 'dataset', 'split_id': 'split'}
    monkeypatch.setattr(model, 'load_artifact', lambda _: (None, metadata))
    monkeypatch.setattr(model, 'load_prepared', lambda _: ([], manifest, None))
    evaluate_metrics = Mock(side_effect=AssertionError('Test prediction must not run before freeze'))
    monkeypatch.setattr(model, 'metrics', evaluate_metrics)
    with pytest.raises(DatasetError, match='Freeze settings'):
        evaluate(tmp_path, tmp_path)
    evaluate_metrics.assert_not_called()


def test_training_orchestration_fits_train_and_evaluates_validation_only(tmp_path, monkeypatch):
    """Mocked control-flow test: no research fit, artifact, or metric is produced."""
    from intelise_c1.baseline import model
    examples, _report = read_dataset(FIXTURE)
    manifest = {'purpose': 'research', 'seed': 42, 'dataset_version': 'test-control-flow', 'split_id': 'test-control-flow',
                'sizes': {}, 'splits': {'train': [item.example_id for item in examples[:4]],
                                       'validation': [item.example_id for item in examples[4:8]],
                                       'test': [item.example_id for item in examples[8:]]}}
    monkeypatch.setattr(model, 'load_prepared', lambda _: (examples, manifest, None))
    fit = Mock(return_value='mock-pipeline')
    measure = Mock(return_value={'mocked-control-flow-only': True})
    save = Mock(return_value='mock-metadata')
    write = Mock()
    monkeypatch.setattr(model, 'fit_pipeline', fit)
    monkeypatch.setattr(model, 'metrics', measure)
    monkeypatch.setattr(model, 'save_artifact', save)
    monkeypatch.setattr(model, 'write_json', write)
    assert train(tmp_path, tmp_path / 'unused', BaselineConfig()) == 'mock-metadata'
    assert fit.call_args.args[0] == examples[:4]
    assert measure.call_args.args == ('mock-pipeline', examples[4:8])
    assert write.call_args.args[1]['evaluation_split'] == 'validation'
