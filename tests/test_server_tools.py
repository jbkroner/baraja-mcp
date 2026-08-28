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


class TestDuplicateScope:
    async def test_add_flashcard_collection_scope_blocks_cross_deck_duplicate(self, patched_anki):
        """Default scope ('collection') should block a duplicate that only exists in another deck."""
        await patched_anki.create_deck("Español")
        await patched_anki.add_note("Español", "Basic", {"Front": "ayer", "Back": "yesterday"})

        result = await server.call_tool(
            "add_flashcard",
            {"deck": "A2.2 Ch1", "front": "ayer", "back": "yesterday"},
        )

        assert "Duplicate" in result[0].text

    async def test_add_flashcard_deck_scope_allows_cross_deck_duplicate(self, patched_anki):
        """Scoping to 'deck' should let a card through when the collision is in an unrelated deck."""
        await patched_anki.create_deck("Español")
        await patched_anki.add_note("Español", "Basic", {"Front": "ayer", "Back": "yesterday"})

        result = await server.call_tool(
            "add_flashcard",
            {
                "deck": "A2.2 Ch1",
                "front": "ayer",
                "back": "yesterday",
                "duplicate_scope": "deck",
            },
        )

        assert "Added flashcard" in result[0].text

    async def test_add_flashcard_deck_scope_still_blocks_same_deck_duplicate(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        await patched_anki.add_note(test_deck_name, "Basic", {"Front": "ayer", "Back": "yesterday"})

        result = await server.call_tool(
            "add_flashcard",
            {
                "deck": test_deck_name,
                "front": "ayer",
                "back": "yesterday",
                "duplicate_scope": "deck",
            },
        )

        assert "Duplicate" in result[0].text

    async def test_batch_deck_scope_ignores_unrelated_deck_collisions(self, patched_anki):
        """The exact repro from the filed issue: a chapter deck shouldn't be
        blocked by cards living in an unrelated mega-deck."""
        await patched_anki.create_deck("Español")
        await patched_anki.add_note("Español", "Basic", {"Front": "el camping", "Back": "campsite"})

        result = await server.call_tool(
            "add_flashcards_batch",
            {
                "deck": "A2.2 Ch1",
                "cards": [{"front": "el camping", "back": "campsite"}],
                "duplicate_scope": "deck",
            },
        )

        text = result[0].text
        assert "Added: 1" in text
        assert "Duplicates skipped: 0" in text

    async def test_batch_deck_and_subdecks_scope_blocks_child_but_not_sibling(self, patched_anki):
        await patched_anki.create_deck("Español::ch11")
        await patched_anki.add_note("Español::ch11", "Basic", {"Front": "anoche", "Back": "last night"})
        await patched_anki.create_deck("OtroTema")
        await patched_anki.add_note("OtroTema", "Basic", {"Front": "ayer", "Back": "yesterday"})

        result = await server.call_tool(
            "add_flashcards_batch",
            {
                "deck": "Español",
                "cards": [
                    {"front": "anoche", "back": "last night"},  # collides via subdeck
                    {"front": "ayer", "back": "yesterday"},  # unrelated sibling deck, should add
                ],
                "duplicate_scope": "deck_and_subdecks",
            },
        )

        text = result[0].text
        assert "Added: 1" in text
        assert "Duplicates skipped: 1" in text
        assert '"anoche"' in text

    async def test_omitted_duplicate_scope_defaults_to_collection(self, patched_anki):
        """Default (param omitted) must be unchanged from before duplicate_scope existed."""
        await patched_anki.create_deck("Español")
        await patched_anki.add_note("Español", "Basic", {"Front": "anoche", "Back": "last night"})

        result = await server.call_tool(
            "add_flashcards_batch",
            {
                "deck": "A2.2 Ch1",
                "cards": [{"front": "anoche", "back": "last night"}],
            },
        )

        text = result[0].text
        assert "Added: 0" in text
        assert "Duplicates skipped: 1" in text


class TestTagTools:
    async def test_add_tags_by_note_ids(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        note_id = await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "Q", "Back": "A"}, tags=["existing"]
        )

        result = await server.call_tool(
            "add_tags", {"note_ids": [note_id], "tags": ["A2.2-Ch3"]}
        )

        assert "Added tags" in result[0].text
        notes = await patched_anki.notes_info([note_id])
        assert "existing" in notes[0]["tags"]
        assert "A2.2-Ch3" in notes[0]["tags"]

    async def test_add_tags_by_query(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        note_id = await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "Q", "Back": "A"}, tags=["findme"]
        )

        result = await server.call_tool(
            "add_tags", {"query": "tag:findme", "tags": ["tagged-via-query"]}
        )

        assert "Added tags" in result[0].text
        notes = await patched_anki.notes_info([note_id])
        assert "tagged-via-query" in notes[0]["tags"]

    async def test_add_tags_requires_note_ids_or_query(self, patched_anki):
        result = await server.call_tool("add_tags", {"tags": ["x"]})
        assert "Error" in result[0].text

    async def test_replace_tags_scoped_to_notes(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        note_id = await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "Q", "Back": "A"}, tags=["A2.2-Ch3"]
        )

        result = await server.call_tool(
            "replace_tags",
            {"note_ids": [note_id], "tag": "A2.2-Ch3", "new_tag": "A2.2-Ch2"},
        )

        assert "Replaced tag" in result[0].text
        notes = await patched_anki.notes_info([note_id])
        assert "A2.2-Ch2" in notes[0]["tags"]
        assert "A2.2-Ch3" not in notes[0]["tags"]

    async def test_replace_tags_whole_collection(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        note_id = await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "Q", "Back": "A"}, tags=["old-tag"]
        )

        result = await server.call_tool(
            "replace_tags", {"tag": "old-tag", "new_tag": "new-tag"}
        )

        assert "entire collection" in result[0].text
        notes = await patched_anki.notes_info([note_id])
        assert "new-tag" in notes[0]["tags"]


class TestUpdateNoteTags:
    async def test_update_note_tags_only(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        note_id = await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "Q", "Back": "A"}, tags=["old"]
        )

        result = await server.call_tool(
            "update_note", {"note_id": note_id, "tags": ["new"]}
        )

        assert "Updated note" in result[0].text
        notes = await patched_anki.notes_info([note_id])
        assert notes[0]["tags"] == ["new"]

    async def test_update_note_requires_fields_or_tags(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        note_id = await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "Q", "Back": "A"}
        )

        result = await server.call_tool("update_note", {"note_id": note_id})

        assert "Error" in result[0].text


class TestDeckTools:
    async def test_delete_deck_requires_confirm(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)

        result = await server.call_tool(
            "delete_deck", {"decks": [test_deck_name], "confirm": False}
        )

        assert "cancelled" in result[0].text
        decks = await patched_anki.deck_names()
        assert test_deck_name in decks

    async def test_delete_deck_confirmed(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        await patched_anki.add_note(test_deck_name, "Basic", {"Front": "Q", "Back": "A"})

        result = await server.call_tool(
            "delete_deck", {"decks": [test_deck_name], "confirm": True}
        )

        assert "Deleted" in result[0].text
        decks = await patched_anki.deck_names()
        assert test_deck_name not in decks

    async def test_rename_deck_moves_cards_and_deletes_old(self, patched_anki, test_deck_name):
        new_name = f"{test_deck_name} Renamed"
        await patched_anki.create_deck(test_deck_name)
        await patched_anki.add_note(test_deck_name, "Basic", {"Front": "Q", "Back": "A"})

        result = await server.call_tool(
            "rename_deck", {"old_deck": test_deck_name, "new_deck": new_name}
        )

        assert "Renamed deck" in result[0].text
        decks = await patched_anki.deck_names()
        assert test_deck_name not in decks
        assert new_name in decks

        card_ids = await patched_anki.find_cards(f'deck:"{new_name}"')
        assert len(card_ids) == 1

    async def test_get_deck_config(self, patched_anki, mock_anki_server, test_deck_name):
        mock_anki_server.set_deck_config(test_deck_name, new_per_day=25, review_per_day=150)

        result = await server.call_tool("get_deck_config", {"deck": test_deck_name})

        text = result[0].text
        assert "25" in text
        assert "150" in text
