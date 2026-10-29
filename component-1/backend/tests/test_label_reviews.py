"""Mocked persistence/classifier contract tests; no model evaluation."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo.errors import DuplicateKeyError, OperationFailure

from test_classifications import client, CollectionDouble  # noqa: F401
from intelise_c1.repositories.reviews import ReviewRepository


class ReviewCollection(CollectionDouble):
    async def insert_one(self, document):
        if any(item['submission_id'] == document['submission_id'] for item in self.documents):
            raise DuplicateKeyError('duplicate submission')
        await super().insert_one(document)

    async def aggregate(self, pipeline):
        query = pipeline[0]['$match']
        matches = [item for item in self.documents if all(item[key] == value for key, value in query.items())]
        latest = {}
        for item in sorted(matches, key=lambda item: (item['reviewed_at'], item['_id']), reverse=True):
            latest.setdefault(item['requirement_id'], item)
        return SimpleNamespace(to_list=AsyncMock(return_value=list(latest.values())[:101]))


@pytest.fixture
def reviews(client):
    client.app.state.label_reviews = ReviewRepository(ReviewCollection())
    classified = client.post(client.url).json()
    client.review_url = f"{client.url}/{classified['classification_id']}/reviews"
    client.save_url = f"{client.url}/{classified['classification_id']}/requirements/{client.extraction.candidates[0].requirement_id}/reviews"
    client.payload = dict(submission_id=str(uuid4()), reviewed_label='NFR', reviewer_id='Research reviewer', note='Reviewed example')
    return client


def test_save_retrieve_separate_prediction_idempotence_and_history(reviews):
    before = deepcopy(reviews.app.state.classifications.collection.documents)
    original = deepcopy(reviews.app.state.extractions.collection.documents)
    assert reviews.get(reviews.review_url).json()['reviews'] == []
    response = reviews.post(reviews.save_url, json=reviews.payload)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['original_prediction'] == 'FR' and saved['reviewed_label'] == 'NFR'
    assert saved['model_identifier'] == 'mock-baseline' and saved['model_version'] == 'a' * 64
    assert saved['review_status'] == 'user_reviewed' and saved['reviewer_identity_status'] == 'self_reported'
    assert saved['requirement_text_hash'] == sha256(reviews.extraction.candidates[0].requirement_text.encode()).hexdigest()
    assert saved['source_discussion_hash'] == reviews.extraction.source_discussion_hash
    assert saved['reviewed_at'].endswith('Z')
    again = reviews.post(reviews.save_url, json=reviews.payload)
    assert again.status_code == 200 and again.json() == saved
    assert reviews.get(reviews.review_url).json()['reviews'] == [saved]
    conflict = reviews.post(reviews.save_url, json={**reviews.payload, 'note': 'Changed'})
    assert conflict.status_code == 409
    updated = reviews.post(reviews.save_url, json={**reviews.payload, 'submission_id': str(uuid4()), 'reviewed_label': 'FR'})
    assert updated.status_code == 201
    assert reviews.get(reviews.review_url).json()['reviews'] == [updated.json()]
    assert len(reviews.app.state.label_reviews.collection.documents) == 2
    assert reviews.app.state.classifications.collection.documents == before
    assert reviews.app.state.extractions.collection.documents == original
    assert reviews.app.state.classifier.predict.call_count == 1  # Classification only.


@pytest.mark.parametrize('change', [dict(reviewed_label='FN'), dict(reviewer_id=' '), dict(note='x'*2001), dict(model_version='forged'), dict(submission_id='bad')])
def test_invalid_input_saves_nothing(reviews, change):
    assert reviews.post(reviews.save_url, json={**reviews.payload, **change}).status_code == 422
    assert not reviews.app.state.label_reviews.collection.documents


def test_other_runs_requirements_and_missing_classification(reviews):
    assert reviews.post(reviews.save_url.replace(reviews.extraction.candidates[0].requirement_id, str(uuid4())), json=reviews.payload).status_code == 404
    assert reviews.post(reviews.save_url.replace(reviews.extraction.run_id, str(uuid4())), json=reviews.payload).status_code == 404
    assert reviews.post(reviews.save_url.replace(reviews.save_url.split('/classifications/')[1].split('/')[0], str(uuid4())), json=reviews.payload).status_code == 404
    assert reviews.post(reviews.save_url, json=reviews.payload).status_code == 201
    newer = reviews.post(reviews.url).json()
    assert reviews.get(f"{reviews.url}/{newer['classification_id']}/reviews").json()['reviews'] == []
    assert len(reviews.get(reviews.review_url).json()['reviews']) == 1
    assert reviews.post(f"{reviews.url}/{newer['classification_id']}/requirements/{reviews.extraction.candidates[0].requirement_id}/reviews", json=reviews.payload).status_code == 409


@pytest.mark.parametrize('operation', ['insert', 'read', 'index', 'unconfigured'])
def test_database_error_is_sanitized(reviews, caplog, operation):
    failure = AsyncMock(side_effect=OperationFailure('private credentials and discussion'))
    if operation == 'unconfigured':
        reviews.app.state.label_reviews = None
    else:
        setattr(reviews.app.state.label_reviews.collection, {'insert':'insert_one', 'read':'aggregate', 'index':'create_index'}[operation], failure)
    response = reviews.get(reviews.review_url) if operation == 'read' else reviews.post(reviews.save_url, json=reviews.payload)
    assert response.status_code == 503
    assert 'private credentials and discussion' not in response.text + caplog.text
    assert reviews.get('/api/v1/component-1/health').status_code == 200


def test_mismatched_stored_review_fails_closed(reviews):
    reviews.post(reviews.save_url, json=reviews.payload)
    reviews.app.state.label_reviews.collection.documents[0]['requirement_text_hash'] = 'b' * 64
    assert reviews.get(reviews.review_url).status_code == 503


def test_inconsistent_classification_rejected_before_save(reviews):
    reviews.app.state.classifications.collection.documents[0]['predictions'] = []
    assert reviews.post(reviews.save_url, json=reviews.payload).status_code == 409
    assert not reviews.app.state.label_reviews.collection.documents


def test_concurrent_duplicate_key_returns_existing_review(reviews):
    collection = reviews.app.state.label_reviews.collection
    original_insert = collection.insert_one

    async def competing_insert(document):
        await original_insert(document)
        raise DuplicateKeyError('simulated competing insert already committed')

    collection.insert_one = competing_insert
    response = reviews.post(reviews.save_url, json=reviews.payload)
    assert response.status_code == 200
    assert len(collection.documents) == 1
    assert reviews.get(reviews.review_url).json()['reviews'] == [response.json()]


def test_latest_review_per_requirement_preserves_other_reviews(reviews):
    first = reviews.post(reviews.save_url, json=reviews.payload).json()
    other_url = reviews.save_url.replace(reviews.extraction.candidates[0].requirement_id, reviews.extraction.candidates[1].requirement_id)
    other = reviews.post(other_url, json={**reviews.payload, 'submission_id': str(uuid4())}).json()
    assert other['original_prediction'] == 'NFR'
    updated = reviews.post(reviews.save_url, json={**reviews.payload, 'submission_id': str(uuid4()), 'reviewed_label': 'FR'}).json()
    actual = {item['review_id'] for item in reviews.get(reviews.review_url).json()['reviews']}
    assert actual == {other['review_id'], updated['review_id']}
    assert first['review_id'] not in actual
