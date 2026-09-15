import pytest
from pydantic import ValidationError

from notes12.schema import Notes12Document


def make_valid_payload(**overrides):
    payload = {
        "title": "Photosynthesis",
        "summary": "How plants convert light into energy.",
        "map_type": "hierarchy",
        "nodes": [
            {
                "id": "photosynthesis",
                "label": "Photosynthesis",
                "type": "process",
                "description": "Converts light energy into chemical energy.",
            },
            {
                "id": "chlorophyll",
                "label": "Chlorophyll",
                "type": "pigment",
                "description": "Absorbs light for photosynthesis.",
            },
        ],
        "relationships": [
            {
                "source": "chlorophyll",
                "target": "photosynthesis",
                "type": "enables",
                "directed": True,
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_valid_complete_object():
    doc = Notes12Document.model_validate(make_valid_payload())
    assert doc.title == "Photosynthesis"
    assert len(doc.nodes) == 2
    assert len(doc.relationships) == 1


@pytest.mark.parametrize(
    "map_type", ["hierarchy", "timeline", "cause_effect", "comparison", "graph"]
)
def test_each_allowed_map_type(map_type):
    doc = Notes12Document.model_validate(make_valid_payload(map_type=map_type))
    assert doc.map_type == map_type


def test_duplicate_node_ids_rejected():
    payload = make_valid_payload()
    payload["nodes"] = [
        {"id": "dup", "label": "A", "type": "x", "description": "First."},
        {"id": "dup", "label": "B", "type": "y", "description": "Second."},
    ]
    payload["relationships"] = []
    with pytest.raises(ValidationError):
        Notes12Document.model_validate(payload)


def test_relationship_source_missing_rejected():
    payload = make_valid_payload()
    payload["relationships"] = [
        {"source": "missing", "target": "photosynthesis", "type": "x", "directed": True}
    ]
    with pytest.raises(ValidationError):
        Notes12Document.model_validate(payload)


def test_relationship_target_missing_rejected():
    payload = make_valid_payload()
    payload["relationships"] = [
        {"source": "photosynthesis", "target": "missing", "type": "x", "directed": True}
    ]
    with pytest.raises(ValidationError):
        Notes12Document.model_validate(payload)


def test_invalid_map_type_rejected():
    with pytest.raises(ValidationError):
        Notes12Document.model_validate(make_valid_payload(map_type="mindmap"))


def test_free_form_node_types_accepted():
    payload = make_valid_payload()
    payload["nodes"][0]["type"] = "totally-custom-node-kind-123"
    doc = Notes12Document.model_validate(payload)
    assert doc.nodes[0].type == "totally-custom-node-kind-123"


def test_free_form_relationship_types_accepted():
    payload = make_valid_payload()
    payload["relationships"][0]["type"] = "another-custom-relation-xyz"
    doc = Notes12Document.model_validate(payload)
    assert doc.relationships[0].type == "another-custom-relation-xyz"


@pytest.mark.parametrize("directed", [True, False])
def test_directed_accepts_booleans(directed):
    payload = make_valid_payload()
    payload["relationships"][0]["directed"] = directed
    doc = Notes12Document.model_validate(payload)
    assert doc.relationships[0].directed is directed


def test_serialization_dict_round_trip():
    doc = Notes12Document.model_validate(make_valid_payload())
    data = doc.model_dump()
    assert data["title"] == "Photosynthesis"
    assert data["map_type"] == "hierarchy"
    assert data["nodes"][0]["id"] == "photosynthesis"
    assert set(data.keys()) == {"title", "summary", "map_type", "nodes", "relationships"}
    assert Notes12Document.model_validate(data) == doc


def test_serialization_json_round_trip():
    doc = Notes12Document.model_validate(make_valid_payload())
    raw = doc.model_dump_json()
    assert '"map_type":"hierarchy"' in raw.replace(" ", "")
    assert Notes12Document.model_validate_json(raw) == doc
