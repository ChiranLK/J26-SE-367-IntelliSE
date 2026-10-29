"""Template workflow contracts with collection doubles, not model evaluation."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo.errors import DuplicateKeyError, OperationFailure

from test_classifications import client, CollectionDouble, PROJECT  # noqa: F401
from test_label_reviews import ReviewCollection
from intelise_c1.repositories.reviews import ReviewRepository
from intelise_c1.repositories.srs import SrsRepository


class SrsCollection(CollectionDouble):
    async def insert_one(self, document):
        if any(item['_id'] == document['_id'] for item in self.documents):
            raise DuplicateKeyError('duplicate')
        await super().insert_one(document)

    async def replace_one(self, query, document):
        for index, item in enumerate(self.documents):
            if all(item.get(key) == value for key, value in query.items()):
                self.documents[index] = deepcopy(document)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


@pytest.fixture
def srs(client):
    project = client.app.state.projects.get.return_value
    project.name, project.description = 'Reports', 'Source backed requirements'
    client.app.state.srs = SrsRepository(SrsCollection())
    client.app.state.label_reviews = ReviewRepository(ReviewCollection())
    classified = client.post(client.url).json()
    for candidate, label in zip(client.extraction.candidates, ['FR', 'NFR']):
        url = f"{client.url}/{classified['classification_id']}/requirements/{candidate.requirement_id}/reviews"
        response = client.post(url, json=dict(submission_id=str(uuid4()), reviewed_label=label, reviewer_id='Analyst', note=''))
        assert response.status_code == 201
    client.srs_url = f'/api/v1/component-1/projects/{PROJECT}/srs'
    client.draft_body = dict(submission_id=str(uuid4()), expected_revision=0, reviewer_id='Analyst',
        extraction_run_id=client.extraction.run_id, classification_id=classified['classification_id'])
    return client


def initial(client):
    response = client.post(client.srs_url, json=client.draft_body)
    assert response.status_code == 200, response.text
    return response.json()


def action(client, state, operation, **fields):
    body = dict(submission_id=str(uuid4()), expected_revision=state['revision'], reviewer_id='Demo client', **fields)
    response = client.post(client.srs_url + '/' + operation, json=body)
    return response, body


def test_draft_review_revision_approval_and_immutable_sources(srs):
    original_extraction = deepcopy(srs.app.state.extractions.collection.documents)
    original_reviews = deepcopy(srs.app.state.label_reviews.collection.documents)
    assert srs.get(srs.srs_url).json()['versions'] == []
    state = initial(srs)
    assert 'receipts' not in state
    assert srs.post(srs.srs_url, json=srs.draft_body).json() == state
    version = state['versions'][-1]
    assert version['status'] == 'draft' and version['approval'] is None
    assert [r['label'] for r in version['requirements']] == ['FR', 'NFR']
    assert [r['text'] for r in version['requirements']] == [c.requirement_text for c in srs.extraction.candidates]
    failed, _ = action(srs, state, 'approval', version_id=version['version_id'], confirm=True)
    assert failed.status_code == 409
    first = version['requirements'][0]['requirement_id']
    response, feedback_body = action(srs, state, 'feedback', version_id=version['version_id'], requirement_id=first,
                                    decision='request_changes', comment='Restrict upload to members.')
    assert response.status_code == 200
    state = response.json()
    assert srs.post(srs.srs_url + '/feedback', json=feedback_body).json() == state
    prior = deepcopy(state['versions'][0])
    response, _ = action(srs, state, 'revisions', base_version_id=version['version_id'], changes=[dict(
        requirement_id=first, text='Only members shall be able to upload reports.', label='FR', reason='Client requested a permission restriction.')])
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['versions'][0] == prior
    current = state['versions'][-1]
    assert current['version_number'] == 2 and current['parent_version_id'] == prior['version_id']
    assert current['feedback'] == [] and current['approval'] is None
    assert current['requirements'][0]['original_text'] == prior['requirements'][0]['text']
    assert current['requirements'][0]['authored_revision'] is True
    assert current['content_hash'] != prior['content_hash']
    old, _ = action(srs, state, 'feedback', version_id=prior['version_id'], requirement_id=first, decision='accepted')
    assert old.status_code == 409
    for requirement in current['requirements']:
        response, _ = action(srs, state, 'feedback', version_id=current['version_id'], requirement_id=requirement['requirement_id'], decision='accepted')
        assert response.status_code == 200
        state = response.json()
    response, body = action(srs, state, 'approval', version_id=current['version_id'], confirm=True)
    assert response.status_code == 200
    approved = response.json()
    assert approved['versions'][-1]['approval']['content_hash'] == current['content_hash']
    assert approved['versions'][-1]['approval']['identity_status'] == 'self_reported'
    assert srs.post(srs.srs_url + '/approval', json=body).json() == approved
    locked, _ = action(srs, approved, 'feedback', version_id=current['version_id'], requirement_id=first, decision='accepted')
    assert locked.status_code == 409
    assert srs.get(srs.srs_url).json() == approved
    assert srs.app.state.extractions.collection.documents == original_extraction
    assert srs.app.state.label_reviews.collection.documents == original_reviews


def test_stale_conflicting_duplicate_and_missing_reviews(srs):
    state = initial(srs)
    changed = {**srs.draft_body, 'reviewer_id': 'Other'}
    assert srs.post(srs.srs_url, json=changed).status_code == 409
    current = state['versions'][0]
    key = current['requirements'][0]['requirement_id']
    response, _ = action(srs, state, 'feedback', version_id=current['version_id'], requirement_id=key, decision='accepted')
    assert response.status_code == 200
    stale, _ = action(srs, state, 'feedback', version_id=current['version_id'], requirement_id=key, decision='needs_clarification', comment='What formats?')
    assert stale.status_code == 409
    assert len(srs.get(srs.srs_url).json()['versions'][0]['feedback']) == 1


def test_initial_draft_uses_model_labels_with_optional_saved_corrections(srs):
    srs.app.state.label_reviews.collection.documents.pop()
    state = initial(srs)
    requirements = state['versions'][0]['requirements']
    assert requirements[0]['label_review_id'] is not None
    assert requirements[1]['label_review_id'] is None
    assert requirements[1]['label'] == 'NFR'


def test_feedback_validation_and_database_failure_are_atomic(srs):
    state = initial(srs)
    version = state['versions'][0]
    key = version['requirements'][0]['requirement_id']
    for fields in [dict(requirement_id='unknown', decision='accepted'), dict(requirement_id=key, decision='needs_clarification', comment=' '), dict(requirement_id=key, decision='request_changes')]:
        response, _ = action(srs, state, 'feedback', version_id=version['version_id'], **fields)
        assert response.status_code == 409
    srs.app.state.srs.collection.replace_one = AsyncMock(side_effect=OperationFailure('sanitized test'))
    response, _ = action(srs, state, 'feedback', version_id=version['version_id'], requirement_id=key, decision='accepted')
    assert response.status_code == 503 and 'sanitized test' not in response.text
    assert srs.get(srs.srs_url).json() == state


def test_compare_and_swap_conflict_and_noop_revision(srs):
    state = initial(srs)
    version = state['versions'][0]
    item = version['requirements'][0]
    response, _ = action(srs, state, 'revisions', base_version_id=version['version_id'], changes=[dict(requirement_id=item['requirement_id'], text=item['text'], label=item['label'], reason='No change')])
    assert response.status_code == 409
    srs.app.state.srs.collection.replace_one = AsyncMock(return_value=SimpleNamespace(matched_count=0))
    response, _ = action(srs, state, 'feedback', version_id=version['version_id'], requirement_id=item['requirement_id'], decision='accepted')
    assert response.status_code == 409
    assert srs.get(srs.srs_url).json() == state


def test_unavailable_and_invalid_input(srs):
    assert srs.post(srs.srs_url, json={**srs.draft_body, 'reviewer_id': ' '}).status_code == 422
    assert srs.post(srs.srs_url, json={**srs.draft_body, 'extraction_run_id': 'wrong'}).status_code == 422
    srs.app.state.srs = None
    assert srs.get(srs.srs_url).status_code == 503
    assert srs.get('/api/v1/component-1/health').status_code == 200


def test_corrupt_saved_content_is_not_returned_or_overwritten(srs):
    initial(srs)
    collection = srs.app.state.srs.collection
    collection.documents[0]['versions'][0]['requirements'][0]['text'] = 'Untracked mutation'
    assert srs.get(srs.srs_url).status_code == 503
    assert srs.post(srs.srs_url, json=srs.draft_body).status_code == 503
    assert collection.documents[0]['versions'][0]['requirements'][0]['text'] == 'Untracked mutation'


def test_no_label_reviews_required_and_saved_correction_wins(srs):
    srs.app.state.label_reviews.collection.documents.clear()
    state = initial(srs)
    requirements = state['versions'][0]['requirements']
    assert [item['label'] for item in requirements] == ['FR', 'NFR']
    assert all(item['label_review_id'] is None for item in requirements)
    assert state['versions'][0]['feedback'] == [] and state['versions'][0]['approval'] is None


def test_bulk_accept_only_pending_is_atomic_idempotent_and_does_not_approve(srs):
    state = initial(srs)
    version = state['versions'][0]
    key = version['requirements'][0]['requirement_id']
    response, _ = action(srs, state, 'feedback', version_id=version['version_id'], requirement_id=key, decision='request_changes', comment='Please revise.')
    state = response.json()
    response, body = action(srs, state, 'accept-remaining', version_id=version['version_id'], confirm=True)
    assert response.status_code == 200, response.text
    state = response.json()
    version = state['versions'][0]
    assert [item['decision'] for item in version['feedback']] == ['request_changes', 'accepted']
    assert version['status'] == 'draft' and version['approval'] is None
    assert srs.post(srs.srs_url + '/accept-remaining', json=body).json() == state
    assert action(srs, state, 'approval', version_id=version['version_id'], confirm=True)[0].status_code == 409
    assert action(srs, state, 'accept-remaining', version_id=version['version_id'], confirm=True)[0].status_code == 409
    assert action(srs, state, 'accept-remaining', version_id=version['version_id'], confirm=False)[0].status_code == 422


def test_bulk_accept_all_then_approve_and_revision_resets(srs):
    state = initial(srs)
    version = state['versions'][0]
    response, body = action(srs, state, 'accept-remaining', version_id=version['version_id'], confirm=True)
    assert response.status_code == 200
    accepted = response.json()
    assert len(accepted['versions'][0]['feedback']) == 2
    assert action(srs, state, 'accept-remaining', version_id=version['version_id'], confirm=True)[0].status_code == 409
    response, _ = action(srs, accepted, 'approval', version_id=version['version_id'], confirm=True)
    assert response.status_code == 200
    assert action(srs, response.json(), 'accept-remaining', version_id=version['version_id'], confirm=True)[0].status_code == 409


def test_bulk_accept_write_failure_does_not_save_partial_decisions(srs):
    state = initial(srs)
    srs.app.state.srs.collection.replace_one = AsyncMock(side_effect=OperationFailure('safe failure'))
    response, _ = action(srs, state, 'accept-remaining', version_id=state['versions'][0]['version_id'], confirm=True)
    assert response.status_code == 503
    assert srs.get(srs.srs_url).json() == state


def test_saved_correction_overrides_prediction_without_fabricating_other_reviews(srs):
    srs.app.state.label_reviews.collection.documents[0]['reviewed_label'] = 'NFR'
    srs.app.state.label_reviews.collection.documents.pop()
    state = initial(srs)
    first, second = state['versions'][0]['requirements']
    assert first['label'] == 'NFR' and first['label_review_id'] is not None
    assert second['label_review_id'] is None


def test_legacy_srs_hash_is_unchanged_after_loading(srs):
    from intelise_c1.api.srs_schemas import SrsVersion
    from intelise_c1.services.srs import content_hash
    state = initial(srs)
    document = srs.app.state.srs.collection.documents[0]
    document['versions'][0]['generation_method'] = 'reviewed-requirements-template-v1'
    document['versions'][0]['content_hash'] = content_hash(SrsVersion.model_validate(document['versions'][0]))
    before = deepcopy(document)
    assert srs.get(srs.srs_url).status_code == 200
    assert srs.app.state.srs.collection.documents[0] == before
