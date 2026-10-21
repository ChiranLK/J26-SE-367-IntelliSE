"""One bounded project aggregate: atomic compare-and-swap protects all versions."""
from bson import BSON
from pymongo.errors import DuplicateKeyError

from intelise_c1.api.srs_schemas import Receipt, SrsState
from intelise_c1.services.srs import SrsConflict, check_revision, content_hash, decisions, digest


class InvalidSrs(ValueError):
    pass


class SrsRepository:
    def __init__(self, collection):
        self.collection = collection

    async def get(self, project_id):
        document = await self.collection.find_one({'_id': project_id})
        state = SrsState.model_validate({key: value for key, value in document.items() if key != '_id'}) if document else SrsState(project_id=project_id)
        if state.project_id != project_id:
            raise InvalidSrs('Saved project identity mismatch')
        for index, version in enumerate(state.versions):
            if (version.version_number != index + 1 or version.content_hash != content_hash(version)
                or version.parent_version_id != (state.versions[index - 1].version_id if index else None)
                or (version.status == 'draft' and version.approval is not None)
                or (version.status == 'approved' and (version.approval is None
                    or version.approval.content_hash != version.content_hash
                    or any(decisions(version).get(item.requirement_id) != 'accepted' for item in version.requirements)))):
                raise InvalidSrs('Saved SRS integrity mismatch')
        return state

    async def apply(self, project_id, operation, body, transform):
        state = await self.get(project_id)
        fingerprint = digest({'operation': operation, 'body': body.model_dump(mode='json')})
        for receipt in state.receipts:
            if receipt.submission_id == str(body.submission_id):
                if receipt.request_hash != fingerprint:
                    raise SrsConflict('Submission ID was already used for different data. Original SRS preserved.')
                return state
        check_revision(state, body.expected_revision)
        if len(state.receipts) >= 1000:
            raise SrsConflict('SRS action limit reached; no records were changed.')
        old_revision = state.revision
        version = transform(state)
        if len(state.versions) > 20:
            raise SrsConflict('SRS version limit reached; no records were changed.')
        state.receipts.append(Receipt(submission_id=str(body.submission_id), request_hash=fingerprint, version_id=version.version_id))
        state.revision += 1
        document = state.model_dump()
        # Receipts are internal, excluded from all API responses.
        document['receipts'] = [item.model_dump() for item in state.receipts]
        document['_id'] = project_id
        if len(BSON.encode(document)) > 4_000_000:
            raise SrsConflict('SRS history size limit reached; no records were changed.')
        try:
            if old_revision == 0:
                await self.collection.insert_one(document)
            else:
                result = await self.collection.replace_one({'_id': project_id, 'revision': old_revision}, document)
                if result.matched_count != 1:
                    raise SrsConflict('Another SRS action completed first. Refresh before submitting again.')
        except DuplicateKeyError:
            raise SrsConflict('Another SRS draft was saved first. Refresh before submitting again.') from None
        return state
