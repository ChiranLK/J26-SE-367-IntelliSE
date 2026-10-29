"""Real MongoDB jobs, with guarded state transitions and restart recovery."""
from datetime import datetime, timezone
from intelise_c1.api.transcription_schemas import TranscriptionJob


def now():
    value = datetime.now(timezone.utc)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


class TranscriptionRepository:
    def __init__(self, collection):
        self.collection = collection
        self.index_ready = False

    async def ensure_index(self):
        if not self.index_ready:
            await self.collection.create_index('transcription_id', unique=True)
            await self.collection.create_index('status')
            self.index_ready = True

    async def create(self, job):
        await self.ensure_index()
        await self.collection.insert_one(job.model_dump())

    async def get(self, identifier):
        data = await self.collection.find_one({'transcription_id': identifier})
        return TranscriptionJob(**{k: v for k, v in data.items() if k != '_id'}) if data else None

    async def transition(self, identifier, expected, fields):
        result = await self.collection.update_one(
            {'transcription_id': identifier, 'status': {'$in': expected}},
            {'$set': {**fields, 'updated_at': now()}},
        )
        return result.modified_count == 1

    async def recover(self):
        await self.ensure_index()
        rows = await self.collection.find({'status': {'$in': ['queued', 'processing']}},
                                          {'transcription_id': 1}).to_list(length=None)
        await self.collection.update_many({'status': {'$in': ['queued', 'processing']}}, {'$set': {
            'status': 'failed', 'error_code': 'interrupted',
            'error_message': 'Transcription was interrupted by an application restart. Upload again after reviewing this job.',
            'updated_at': now(),
        }})
        return [row['transcription_id'] for row in rows]
