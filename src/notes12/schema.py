"""Locked Notes12 data contract (V0).

Exact JSON field names are preserved. No extra fields are allowed.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

MapType = Literal["hierarchy", "timeline", "cause_effect", "comparison", "graph"]


class Notes12Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    type: str
    description: str


class Notes12Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    type: str
    directed: bool


class Notes12Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    map_type: MapType
    nodes: list[Notes12Node]
    relationships: list[Notes12Relationship]

    @model_validator(mode="after")
    def check_node_and_relationship_invariants(self) -> "Notes12Document":
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("node ids must be unique")
        known_ids = set(node_ids)
        for rel in self.relationships:
            if rel.source not in known_ids:
                raise ValueError(f"relationship source {rel.source!r} is not a known node id")
            if rel.target not in known_ids:
                raise ValueError(f"relationship target {rel.target!r} is not a known node id")
        return self
