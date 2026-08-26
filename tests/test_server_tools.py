"""Tests for MCP tool handlers in server.py, exercised via call_tool()."""

import pytest

from baraja_mcp import server


@pytest.fixture
async def patched_anki(anki_client, monkeypatch):
    """Point the server's module-level AnkiClient at the mock server."""
    monkeypatch.setattr(server, "anki", anki_client)
    return anki_client


class TestAddFlashcardsBatchDuplicates:
    async def test_partial_batch_with_duplicates_adds_new_and_reports_skipped(
        self, patched_anki, test_deck_name
    ):
        # Seed one existing note that will collide with a card in the batch.
        await patched_anki.create_deck(test_deck_name)
        existing_id = await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "el camping", "Back": "campsite"}
        )
        assert existing_id is not None

        result = await server.call_tool(
            "add_flashcards_batch",
            {
                "deck": test_deck_name,
                "cards": [
                    {"front": "el resort", "back": "resort"},
                    {"front": "el camping", "back": "campsite"},  # duplicate
                    {"front": "la tienda", "back": "tent"},
                ],
            },
        )

        text = result[0].text
        assert "Added: 2" in text
        assert "Duplicates skipped: 1" in text
        assert "Total: 3" in text
        assert '"el camping"' in text
        assert str(existing_id) in text

        # The non-duplicate cards must have actually been added, not rolled back.
        note_ids = await patched_anki.find_notes(f'deck:"{test_deck_name}"')
        assert len(note_ids) == 3  # existing + 2 new

    async def test_allow_duplicates_forces_all_cards_in(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "ayer", "Back": "yesterday"}
        )

        result = await server.call_tool(
            "add_flashcards_batch",
            {
                "deck": test_deck_name,
                "cards": [{"front": "ayer", "back": "yesterday"}],
                "allow_duplicates": True,
            },
        )

        text = result[0].text
        assert "Added: 1" in text
        assert "Duplicates skipped: 0" in text

    async def test_no_duplicates_behaves_as_before(self, patched_anki, test_deck_name):
        result = await server.call_tool(
            "add_flashcards_batch",
            {
                "deck": test_deck_name,
                "cards": [
                    {"front": "uno", "back": "one"},
                    {"front": "dos", "back": "two"},
                ],
            },
        )

        text = result[0].text
        assert "Added: 2" in text
        assert "Duplicates skipped: 0" in text
        assert "Skipped duplicates" not in text
