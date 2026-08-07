
"""
Tests for per-entity image generation history saved to the brain.

Covers POST /api/brain/images (save), GET /api/brain/images (list), and
POST /api/brain/images/delete (remove) - the persistence layer behind the
Knowledge Graph Generate image button.
"""

import pytest


@pytest.fixture
def router():
    from memory_knowledge.brain_api import router
    return router


@pytest.mark.asyncio
async def test_save_and_list_entity_image(client):
    "Saving an image returns an id and it shows up in the scoped listing."
    resp = await client.post(
        '/api/brain/images',
        json={
            'brain_id': 'general',
            'entity': 'Python',
            'prompt': 'cybernetic concept art',
            'image_url': 'https://image.pollinations.ai/prompt/test',
        },
    )
    assert resp.status_code == 200
    saved = resp.json()
    assert saved['entity'] == 'Python'
    assert saved['id'] > 0

    listed = await client.get('/api/brain/images?brain_id=general&entity=Python')
    assert listed.status_code == 200
    items = listed.json()['items']
    assert any(i['id'] == saved['id'] for i in items)
    assert all(i['brain_id'] == 'general' for i in items)

    other = await client.get('/api/brain/images?brain_id=general&entity=Other')
    assert other.status_code == 200
    assert other.json()['count'] == 0


@pytest.mark.asyncio
async def test_delete_entity_image(client):
    "Deleting an image removes it from history."
    resp = await client.post(
        '/api/brain/images',
        json={
            'brain_id': 'general',
            'entity': 'Python',
            'prompt': 'p',
            'image_url': 'https://image.pollinations.ai/prompt/test2',
        },
    )
    assert resp.status_code == 200
    img_id = resp.json()['id']

    deleted = await client.post('/api/brain/images/delete', json={'id': img_id})
    assert deleted.status_code == 200
    assert deleted.json()['deleted'] == 1

    listed = await client.get('/api/brain/images?brain_id=general&entity=Python')
    assert listed.json()['count'] == 0
