"""Smoke: session append + persistence."""

from pico_core.session import (
    Session,
    UserPayload,
    AssistantPayload,
    AssistantBlock,
    kb_hit_payload,
    ocr_page_payload,
    router_decision_payload,
    trace_events,
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


def test_trace_subtypes_round_trip_and_projection(tmp_path):
    session = Session()
    root = session.append(None, UserPayload(content="inspect report"))
    r = session.append(root.id, router_decision_payload("ocr", "nuextract", "match"))
    k = session.append(r.id, kb_hit_payload("SOP-3.2", "c1", "p14"))
    o = session.append(k.id, ocr_page_payload(1, "p1.png", "finding"))
    assert r.payload.subtype == "router_decision"
    assert [n.id for n in trace_events(session)] == [r.id, k.id, o.id]
    path = tmp_path / "t.jsonl"
    session.save(path)
    loaded = Session.load(path)
    assert loaded.active_leaf_id == o.id
    assert [n.id for n in trace_events(loaded)] == [r.id, k.id, o.id]
