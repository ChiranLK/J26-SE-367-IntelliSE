"""Append-only label-review history, with idempotent individual submissions."""
from pymongo.errors import DuplicateKeyError

from intelise_c1.api.review_schemas import LabelReview


class ReviewConflict(Exception):
    pass


class ReviewRepository:
    def __init__(self, collection):
        self.collection = collection
        self.index_ready = False

    async def ensure_index(self):
        if not self.index_ready:
            await self.collection.create_index('submission_id', unique=True, name='review_submission')
            await self.collection.create_index([('project_id', 1), ('extraction_run_id', 1), ('classification_id', 1),
                                                ('requirement_id', 1), ('reviewed_at', -1), ('_id', -1)], name='reviews_latest')
            self.index_ready = True

    @staticmethod
    def parse(document):
        return LabelReview(**{key: value for key, value in document.items() if key != '_id'})

    def replay(self, document, review):
        saved = self.parse(document)
        # Timestamps/server-generated review IDs differ between identical retries.
        fields = set(LabelReview.model_fields) - {'review_id', 'reviewed_at'}
        if any(getattr(saved, key) != getattr(review, key) for key in fields):
            raise ReviewConflict('Submission ID was already used for a different review. No record was changed.')
        return saved

    async def create(self, review):
        await self.ensure_index()
        saved = await self.collection.find_one({'submission_id': review.submission_id})
        if saved is not None:
            return self.replay(saved, review), False
        try:
            await self.collection.insert_one(review.model_dump())
        except DuplicateKeyError:
            # Concurrent requests for the same UUID must not append duplicates.
            saved = await self.collection.find_one({'submission_id': review.submission_id})
            if saved is None:
                raise
            return self.replay(saved, review), False
        return review, True

    async def latest(self, project_id, extraction_run_id, classification_id):
        await self.ensure_index()
        cursor = await self.collection.aggregate([
            {'$match': {'project_id': project_id, 'extraction_run_id': extraction_run_id, 'classification_id': classification_id}},
            {'$sort': {'reviewed_at': -1, '_id': -1}},
            {'$group': {'_id': '$requirement_id', 'review': {'$first': '$$ROOT'}}},
            {'$replaceRoot': {'newRoot': '$review'}},
            {'$limit': 101},
        ])
        return [self.parse(document) for document in await cursor.to_list(length=101)]
