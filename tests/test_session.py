"""Smoke: session append + persistence."""

from pico_core.session import (
    Session,
    UserPayload,
    AssistantPayload,
    AssistantBlock,
)


def _assistant(text: str) -> AssistantPayload:
    return AssistantPayload(blocks=[AssistantBlock(kind="text", text=text)])


def test_append_creates_node_with_shape():
    session = Session()
    node = session.append(None, UserPayload(content="hello"))
    assert node.id
    assert node.parent_id is None
    assert node.timestamp
    assert node.payload == UserPayload(content="hello")
    assert session.active_leaf_id == node.id


def test_save_load_round_trip(tmp_path):
    session = Session()
    root = session.append(None, UserPayload(content="hi"))
    a = session.append(root.id, _assistant("hello"))
    path = tmp_path / "s.jsonl"
    session.save(path)
    loaded = Session.load(path)
    assert loaded.id == session.id
    assert loaded.active_leaf_id == a.id
    assert set(loaded.nodes) == set(session.nodes)
