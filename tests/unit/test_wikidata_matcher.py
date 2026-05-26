import pytest
from typing import Dict, Callable


def _make_schema_matcher(schema: Dict) -> Callable[[Dict], bool]:
    """Inline copy of orchestrator.PipelineController._make_schema_matcher."""
    root_qid = schema["root"]

    def matches_schema(entity: Dict) -> bool:
        for prop in ("P31", "P279"):
            for claim in entity.get("claims", {}).get(prop, []):
                try:
                    if claim["mainsnak"]["datavalue"]["value"]["id"] == root_qid:
                        return True
                except (KeyError, TypeError):
                    continue
        return False

    return matches_schema


def _make_entity(qid, claims=None):
    """Helper to create a mock Wikidata entity."""
    return {"id": qid, "claims": claims or {}}


def _make_claim(prop, value_qid):
    """Helper to create a mock Wikidata claim."""
    return {
        "mainsnak": {
            "datavalue": {
                "value": {"id": value_qid, "type": "wikidata-entity"},
                "type": "wikidata-entity",
            }
        }
    }


class TestSchemaMatcher:
    def test_matches_root_qid_in_p31(self):
        schema = {"root": "Q80993", "props": ["P31", "P279"]}
        matcher = _make_schema_matcher(schema)
        entity = _make_entity("Q123", claims={"P31": [_make_claim("P31", "Q80993")]})
        assert matcher(entity) is True

    def test_matches_root_qid_in_p279(self):
        schema = {"root": "Q80993", "props": ["P31", "P279"]}
        matcher = _make_schema_matcher(schema)
        entity = _make_entity("Q456", claims={"P279": [_make_claim("P279", "Q80993")]})
        assert matcher(entity) is True

    def test_no_match_wrong_qid(self):
        schema = {"root": "Q80993", "props": ["P31", "P279"]}
        matcher = _make_schema_matcher(schema)
        entity = _make_entity("Q789", claims={"P31": [_make_claim("P31", "Q11190")]})
        assert matcher(entity) is False

    def test_no_match_empty_claims(self):
        schema = {"root": "Q80993", "props": ["P31", "P279"]}
        matcher = _make_schema_matcher(schema)
        entity = _make_entity("Q999", claims={})
        assert matcher(entity) is False

    def test_no_claims_key(self):
        schema = {"root": "Q395", "props": ["P31"]}
        matcher = _make_schema_matcher(schema)
        entity = {"id": "Q000"}
        assert matcher(entity) is False

    def test_malformed_claim_skipped(self):
        schema = {"root": "Q80993", "props": ["P31", "P279"]}
        matcher = _make_schema_matcher(schema)
        entity = _make_entity("Q123", claims={"P31": [{"mainsnak": {"datavalue": {}}}]})
        assert matcher(entity) is False

    def test_multiple_claims_one_matches(self):
        schema = {"root": "Q80993", "props": ["P31", "P279"]}
        matcher = _make_schema_matcher(schema)
        entity = _make_entity("Q123", claims={
            "P31": [_make_claim("P31", "Q11190"), _make_claim("P31", "Q80993")]
        })
        assert matcher(entity) is True

    def test_different_root_qid(self):
        schema = {"root": "Q11190", "props": ["P31"]}
        matcher = _make_schema_matcher(schema)
        entity = _make_entity("Q999", claims={"P31": [_make_claim("P31", "Q80993")]})
        assert matcher(entity) is False

    def test_all_15_schemas_match(self):
        from orchestrator import WIKIDATA_SCHEMAS
        for domain, schema in WIKIDATA_SCHEMAS.items():
            matcher = _make_schema_matcher(schema)
            entity = _make_entity(f"dummy_{domain}", claims={
                "P31": [_make_claim("P31", schema["root"])]
            })
            assert matcher(entity) is True, f"{domain} ({schema['root']}) should match"
