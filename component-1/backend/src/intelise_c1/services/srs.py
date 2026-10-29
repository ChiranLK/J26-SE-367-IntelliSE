"""Deterministic draft/revision transitions. No provider calls or source mutation."""
from hashlib import sha256
import json
from uuid import uuid4

from intelise_c1.api.srs_schemas import ClientFeedback, SrsApproval, SrsRequirement, SrsVersion
from intelise_c1.repositories.transcriptions import now


class SrsConflict(Exception):
    pass


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def content_hash(version):
    return digest(version.model_dump(mode='json', exclude={'content_hash', 'feedback', 'approval', 'status'}))


def check_revision(state, expected):
    if state.revision != expected:
        raise SrsConflict('SRS changed since it was loaded. Refresh before submitting again.')


def latest(state, identifier):
    if not state.versions or state.versions[-1].version_id != str(identifier):
        raise SrsConflict('Only the latest SRS version can be reviewed, revised or approved. Refresh the SRS.')
    return state.versions[-1]


def decisions(version):
    return {item.requirement_id: item.decision for item in version.feedback}


def draft(project, extraction, classification, reviews, reviewer):
    if not extraction.candidates:
        raise SrsConflict('A draft requires at least one saved requirement.')
    by_id = {item.requirement_id: item for item in reviews}
    ids = {item.requirement_id for item in extraction.candidates}
    predictions = {item.requirement_id: item.label for item in classification.predictions}
    if len(by_id) != len(reviews) or not set(by_id) <= ids or set(predictions) != ids:
        raise SrsConflict('Saved labels do not match this extraction. Refresh saved results.')
    version = SrsVersion(version_id=str(uuid4()), version_number=1, generation_method='classified-requirements-template-v2', project_title=project.name,
        project_description=project.description, extraction_run_id=extraction.run_id,
        classification_id=classification.classification_id, source_discussion_hash=extraction.source_discussion_hash,
        created_at=now(), created_by=reviewer, content_hash='', requirements=[SrsRequirement(
            requirement_id=item.requirement_id, text=item.requirement_text, original_text=item.requirement_text,
            label=by_id[item.requirement_id].reviewed_label if item.requirement_id in by_id else predictions[item.requirement_id],
            label_review_id=by_id[item.requirement_id].review_id if item.requirement_id in by_id else None,
            source_text_hash=sha256(item.requirement_text.encode()).hexdigest()) for item in extraction.candidates])
    version.content_hash = content_hash(version)
    return version


def feedback(state, body):
    version = latest(state, body.version_id)
    if version.status != 'draft':
        raise SrsConflict('Approved SRS versions are frozen. Create a revision before changing feedback.')
    if body.requirement_id not in {item.requirement_id for item in version.requirements}:
        raise SrsConflict('Requirement does not belong to this SRS version.')
    if body.decision != 'accepted' and not body.comment.strip():
        raise SrsConflict('Explain the requested change or clarification in a comment.')
    if len(version.feedback) >= 500:
        raise SrsConflict('Feedback history limit reached. Create a new version.')
    version.feedback.append(ClientFeedback(feedback_id=str(uuid4()), requirement_id=body.requirement_id,
        decision=body.decision, comment=body.comment, reviewer_id=body.reviewer_id, recorded_at=now()))
    return version


def accept_remaining(state, body):
    version = latest(state, body.version_id)
    if version.status != 'draft':
        raise SrsConflict('Approved SRS versions are frozen.')
    statuses = decisions(version)
    pending = [item for item in version.requirements if item.requirement_id not in statuses]
    if not pending:
        raise SrsConflict('No pending requirements remain. Existing change and clarification requests must be resolved individually.')
    if len(version.feedback) + len(pending) > 500:
        raise SrsConflict('Feedback history limit reached. No decisions were saved.')
    recorded_at = now()
    for item in pending:
        version.feedback.append(ClientFeedback(feedback_id=str(uuid4()), requirement_id=item.requirement_id,
            decision='accepted', comment='Accepted through the explicit accept-remaining action.',
            reviewer_id=body.reviewer_id, recorded_at=recorded_at))
    return version


def revise(state, body):
    base = latest(state, body.base_version_id)
    changes = {item.requirement_id: item for item in body.changes}
    ids = {item.requirement_id for item in base.requirements}
    if len(changes) != len(body.changes) or not set(changes) <= ids:
        raise SrsConflict('Changes must identify distinct requirements in this SRS version.')
    if not any(changes[key].text != item.text or changes[key].label != item.label
               for item in base.requirements if (key := item.requirement_id) in changes):
        raise SrsConflict('A revision must change requirement text or its label.')
    version = base.model_copy(deep=True)
    version.version_id = str(uuid4())
    version.version_number += 1
    version.parent_version_id = base.version_id
    version.created_at = now()
    version.created_by = body.reviewer_id
    version.status = 'draft'
    version.feedback = []
    version.approval = None
    for item in version.requirements:
        if change := changes.get(item.requirement_id):
            item.text, item.label, item.change_reason = change.text, change.label, change.reason
            item.authored_revision = True
    version.content_hash = content_hash(version)
    state.versions.append(version)
    return version


def approve(state, body):
    version = latest(state, body.version_id)
    if version.status != 'draft':
        raise SrsConflict('This version is already approved.')
    statuses = decisions(version)
    if not version.requirements or any(statuses.get(item.requirement_id) != 'accepted' for item in version.requirements):
        raise SrsConflict('Every requirement must have an accepted client decision; resolve all change and clarification requests first.')
    version.status = 'approved'
    version.approval = SrsApproval(reviewer_id=body.reviewer_id, approved_at=now(), content_hash=version.content_hash)
    return version
