"""Explicit review of a saved prediction; no model inference or source mutation."""
from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Path, Request, Response
from pydantic import ValidationError

from intelise_c1.api.classifications import ProjectId, context
from intelise_c1.api.review_schemas import LabelReview, ReviewInput, ReviewPage
from intelise_c1.core.database import UNAVAILABLE_DETAIL
from intelise_c1.repositories.reviews import ReviewConflict
from intelise_c1.repositories.transcriptions import now

reviews_router = APIRouter(prefix='/projects', tags=['label reviews'])
ROOT = '/{project_id}/extractions/{run_id}/classifications/{classification_id}'
RequirementId = Annotated[str, Path(min_length=1, max_length=200)]


def text_hash(text):
    return sha256(text.encode('utf-8')).hexdigest()


async def review_context(project_id, run_id, classification_id, request):
    try:
        extraction, classifications = await context(project_id, run_id, request)
        classification = await classifications.get(extraction.project_id, extraction.run_id, str(classification_id))
        if classification is None:
            raise HTTPException(404, 'Classification not found for this project and extraction.')
        candidates = {item.requirement_id: item for item in extraction.candidates}
        predictions = {item.requirement_id: item.label for item in classification.predictions}
        if (len(candidates) != len(extraction.candidates) or len(predictions) != len(classification.predictions)
                or set(candidates) != set(predictions)):
            raise HTTPException(409, 'Saved classification does not match the extraction. No review was saved.')
        repository = getattr(request.app.state, 'label_reviews', None)
        if repository is None:
            raise HTTPException(503, UNAVAILABLE_DETAIL)
        return extraction, classification, candidates, predictions, repository
    except ValidationError:
        raise HTTPException(503, 'Saved classification data is invalid. Original records were preserved.') from None


@reviews_router.post(ROOT + '/requirements/{requirement_id}/reviews', response_model=LabelReview, status_code=201,
    responses={200: {'model': LabelReview, 'description': 'Identical submission already saved.'},
               404: {'description': 'Referenced project, extraction, classification or requirement does not exist in this scope.'},
               409: {'description': 'Submission ID reused with different data or inconsistent saved classification.'},
               503: {'description': 'Persistence unavailable or saved data invalid.'}})
async def save_review(project_id: ProjectId, run_id: UUID, classification_id: UUID,
                      requirement_id: RequirementId, body: ReviewInput, request: Request, response: Response):
    extraction, classification, candidates, predictions, repository = await review_context(project_id, run_id, classification_id, request)
    if requirement_id not in candidates:
        raise HTTPException(404, 'Requirement not found in this extraction and classification.')
    review = LabelReview(review_id=str(uuid4()), submission_id=str(body.submission_id),
        project_id=extraction.project_id, extraction_run_id=extraction.run_id,
        classification_id=classification.classification_id, requirement_id=requirement_id,
        original_prediction=predictions[requirement_id], reviewed_label=body.reviewed_label,
        reviewer_id=body.reviewer_id, note=body.note, model_identifier=classification.model_identifier,
        model_version=classification.model_version, source_discussion_hash=extraction.source_discussion_hash,
        requirement_text_hash=text_hash(candidates[requirement_id].requirement_text), reviewed_at=now())
    try:
        saved, created = await repository.create(review)
        if not created:
            response.status_code = 200
        return saved
    except ReviewConflict as error:
        raise HTTPException(409, str(error)) from None
    except ValidationError:
        raise HTTPException(503, 'Saved review data is invalid. Original records were preserved.') from None


@reviews_router.get(ROOT + '/reviews', response_model=ReviewPage)
async def get_reviews(project_id: ProjectId, run_id: UUID, classification_id: UUID, request: Request):
    extraction, classification, candidates, predictions, repository = await review_context(project_id, run_id, classification_id, request)
    try:
        reviews = await repository.latest(extraction.project_id, extraction.run_id, classification.classification_id)
        seen = set()
        for review in reviews:
            if (review.requirement_id in seen or review.requirement_id not in candidates
                    or review.project_id != extraction.project_id or review.extraction_run_id != extraction.run_id
                    or review.classification_id != classification.classification_id
                    or review.original_prediction != predictions[review.requirement_id]
                    or review.model_version != classification.model_version or review.model_identifier != classification.model_identifier
                    or review.source_discussion_hash != extraction.source_discussion_hash
                    or review.requirement_text_hash != text_hash(candidates[review.requirement_id].requirement_text)):
                raise HTTPException(503, 'Saved reviews do not match this classification. Original records were preserved.')
            seen.add(review.requirement_id)
        return ReviewPage(project_id=extraction.project_id, extraction_run_id=extraction.run_id,
                          classification_id=classification.classification_id, reviews=reviews)
    except ValidationError:
        raise HTTPException(503, 'Saved review data is invalid. Original records were preserved.') from None
