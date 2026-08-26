"""Tests for search_notes pagination/full-field options and get_notes, via call_tool()."""

import pytest

from baraja_mcp import server


@pytest.fixture
async def patched_anki(anki_client, monkeypatch):
    """Point the server's module-level AnkiClient at the mock server."""
    monkeypatch.setattr(server, "anki", anki_client)
    return anki_client


LONG_BACK = "Ya tenemos que embarcar. " * 5  # well over 50 chars


class TestGetNotes:
    async def test_returns_complete_untruncated_fields(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        note_id = await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "boarding pass", "Back": LONG_BACK}, tags=["travel"]
        )

        result = await server.call_tool("get_notes", {"note_ids": [note_id]})

        text = result[0].text
        assert f"Note ID: {note_id}" in text
        assert "Model: Basic" in text
        assert LONG_BACK in text  # not truncated
        assert "travel" in text

    async def test_multiple_ids_all_returned_untruncated(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        id1 = await patched_anki.add_note(test_deck_name, "Basic", {"Front": "uno", "Back": LONG_BACK})
        id2 = await patched_anki.add_note(test_deck_name, "Basic", {"Front": "dos", "Back": LONG_BACK})

        result = await server.call_tool("get_notes", {"note_ids": [id1, id2]})

        text = result[0].text
        assert text.count(LONG_BACK) == 2
        assert f"Note ID: {id1}" in text
        assert f"Note ID: {id2}" in text

    async def test_unknown_id_omitted_not_erroring(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        note_id = await patched_anki.add_note(test_deck_name, "Basic", {"Front": "a", "Back": "b"})

        result = await server.call_tool("get_notes", {"note_ids": [note_id, 999999999]})

        text = result[0].text
        assert "Found 1 notes" in text


class TestSearchNotesPaginationAndFullFields:
    async def test_default_output_truncates_like_before(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "boarding pass", "Back": LONG_BACK}, tags=["travel"]
        )

        result = await server.call_tool("search_notes", {"query": f'deck:"{test_deck_name}"'})

        text = result[0].text
        assert LONG_BACK not in text  # still truncated by default
        assert LONG_BACK[:50] in text

    async def test_full_returns_untruncated_values(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "boarding pass", "Back": LONG_BACK}
        )

        result = await server.call_tool(
            "search_notes", {"query": f'deck:"{test_deck_name}"', "full": True}
        )

        assert LONG_BACK in result[0].text

    async def test_fields_filter_limits_and_expands_values(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        await patched_anki.add_note(
            test_deck_name, "Basic", {"Front": "boarding pass", "Back": LONG_BACK}
        )

        result = await server.call_tool(
            "search_notes", {"query": f'deck:"{test_deck_name}"', "fields": ["Back"]}
        )

        text = result[0].text
        assert LONG_BACK in text  # implied full values
        assert "Front:" not in text
        assert "Back:" in text

    async def test_pagination_pages_without_dropping_or_duplicating_notes(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        for i in range(5):
            await patched_anki.add_note(test_deck_name, "Basic", {"Front": f"word{i}", "Back": f"meaning{i}"})

        page1 = await server.call_tool(
            "search_notes", {"query": f'deck:"{test_deck_name}"', "limit": 2, "offset": 0}
        )
        page2 = await server.call_tool(
            "search_notes", {"query": f'deck:"{test_deck_name}"', "limit": 2, "offset": 2}
        )
        page3 = await server.call_tool(
            "search_notes", {"query": f'deck:"{test_deck_name}"', "limit": 2, "offset": 4}
        )

        all_words = set()
        for page in (page1, page2, page3):
            text = page[0].text
            for i in range(5):
                if f"word{i}" in text:
                    all_words.add(f"word{i}")

        assert all_words == {f"word{i}" for i in range(5)}
        assert "5 notes matching query" in page1[0].text

    async def test_offset_past_end_reports_no_notes_without_erroring(self, patched_anki, test_deck_name):
        await patched_anki.create_deck(test_deck_name)
        await patched_anki.add_note(test_deck_name, "Basic", {"Front": "a", "Back": "b"})

        result = await server.call_tool(
            "search_notes", {"query": f'deck:"{test_deck_name}"', "offset": 10}
        )

        assert "No notes at offset 10" in result[0].text
