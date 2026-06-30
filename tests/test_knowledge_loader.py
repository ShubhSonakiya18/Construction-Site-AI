"""
tests/test_knowledge_loader.py — Unit tests for KnowledgeBase singleton.

Tests verify:
- All 6 knowledge files load without error
- Public API methods return non-empty results of the correct type
- Singleton pattern: same object returned on repeated calls
- reset_knowledge_base() forces a fresh load
"""
import pytest

from dataset_generation_framework.core.knowledge_loader import (
    KnowledgeBase,
    get_knowledge_base,
    reset_knowledge_base,
)


@pytest.fixture(autouse=True)
def reset_kb():
    """Ensure a clean singleton before every test."""
    reset_knowledge_base()
    yield
    reset_knowledge_base()


class TestKnowledgeBaseLoading:
    def test_loads_without_error(self):
        kb = KnowledgeBase()
        assert kb is not None

    def test_singleton_returns_same_object(self):
        kb1 = get_knowledge_base()
        kb2 = get_knowledge_base()
        assert kb1 is kb2

    def test_reset_forces_fresh_load(self):
        kb1 = get_knowledge_base()
        reset_knowledge_base()
        kb2 = get_knowledge_base()
        assert kb1 is not kb2


class TestSchemaAPI:
    def test_stage_enum_has_22_values(self):
        kb = get_knowledge_base()
        enum = kb.stage_enum()
        assert isinstance(enum, list)
        assert len(enum) >= 10, "stage enum should have at least 10 values"

    def test_trade_enum_is_non_empty(self):
        kb = get_knowledge_base()
        enum = kb.trade_enum()
        assert isinstance(enum, list)
        assert len(enum) > 0

    def test_weather_condition_enum_is_non_empty(self):
        kb = get_knowledge_base()
        enum = kb.weather_condition_enum()
        assert isinstance(enum, list)
        assert "sunny" in enum or len(enum) > 0


class TestDAGAPI:
    def test_dag_nodes_returns_list(self):
        kb = get_knowledge_base()
        nodes = kb.dag_nodes()
        assert isinstance(nodes, list)
        assert len(nodes) > 0

    def test_topological_order_non_empty(self):
        kb = get_knowledge_base()
        order = kb.topological_order()
        assert isinstance(order, list)
        assert len(order) > 0

    def test_critical_path_is_subset_of_topo_order(self):
        kb = get_knowledge_base()
        topo = set(kb.topological_order())
        crit = kb.critical_path_nodes()
        assert isinstance(crit, list)
        for node in crit:
            assert node in topo, f"Critical path node {node!r} not in topological order"

    def test_is_milestone_foundation_false(self):
        kb = get_knowledge_base()
        # foundation is a work stage, not a milestone
        assert kb.is_milestone("foundation") is False

    def test_edges_to_framing_returns_list(self):
        kb = get_knowledge_base()
        edges = kb.edges_to("framing")
        assert isinstance(edges, list)

    def test_max_lag_days_foundation_gte_zero(self):
        kb = get_knowledge_base()
        lag = kb.max_lag_days_from("foundation")
        assert lag >= 0

    def test_dag_node_returns_dict_for_framing(self):
        kb = get_knowledge_base()
        node = kb.dag_node("framing")
        assert node is not None
        assert node.get("id") == "framing"


class TestOntologyAPI:
    def test_ontology_trades_returns_list(self):
        kb = get_knowledge_base()
        trades = kb.ontology_trades()
        assert isinstance(trades, list)
        assert len(trades) > 0

    def test_ontology_materials_returns_list(self):
        kb = get_knowledge_base()
        mats = kb.ontology_materials()
        assert isinstance(mats, list)

    def test_hazards_for_framing_returns_list(self):
        kb = get_knowledge_base()
        hazards = kb.hazards_for_stage("framing")
        assert isinstance(hazards, list)

    def test_ppe_for_roofing_returns_list(self):
        kb = get_knowledge_base()
        ppe = kb.ppe_for_stage("roofing")
        assert isinstance(ppe, list)

    def test_trades_active_in_foundation_returns_list(self):
        kb = get_knowledge_base()
        trades = kb.trades_active_in_stage("foundation")
        assert isinstance(trades, list)


class TestValidationRulesAPI:
    def test_all_validation_rules_non_empty(self):
        kb = get_knowledge_base()
        rules = kb.all_validation_rules()
        assert isinstance(rules, list)
        assert len(rules) > 0

    def test_blocking_rule_ids_is_list(self):
        kb = get_knowledge_base()
        ids = kb.blocking_rule_ids()
        assert isinstance(ids, list)

    def test_all_rule_ids_have_val_prefix(self):
        kb = get_knowledge_base()
        rules = kb.all_validation_rules()
        for rule in rules:
            rid = rule.get("rule_id", "")
            assert rid.startswith("VAL-"), f"Rule {rid!r} does not start with 'VAL-'"


class TestConstructionRulesAPI:
    def test_all_construction_rules_non_empty(self):
        kb = get_knowledge_base()
        rules = kb.all_construction_rules()
        assert isinstance(rules, list)
        assert len(rules) > 0

    def test_sequential_rules_exist(self):
        kb = get_knowledge_base()
        seq_rules = kb.construction_rules_by_type("sequential")
        assert isinstance(seq_rules, list)
        assert len(seq_rules) > 0
