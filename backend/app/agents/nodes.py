"""Backward-compatibility re-exports.

Each agent now lives in its own module. This shim re-exports everything so
any code that previously imported from ``app.agents.nodes`` continues to work.
"""
from app.agents.supervisor_node import query_preprocess_node, supervisor_node  # noqa: F401
from app.agents.retrieve_node import retrieve_node                              # noqa: F401
from app.agents.supplier_agent import supplier_agent                            # noqa: F401
from app.agents.shipment_agent import shipment_agent                            # noqa: F401
from app.agents.inventory_agent import inventory_agent                          # noqa: F401
from app.agents.recommendation_agent import recommendation_agent                # noqa: F401
from app.agents.judge_agent import judge_agent                                  # noqa: F401
from app.agents.report_agent import report_agent                                # noqa: F401

__all__ = [
    "query_preprocess_node",
    "supervisor_node",
    "retrieve_node",
    "supplier_agent",
    "shipment_agent",
    "inventory_agent",
    "recommendation_agent",
    "judge_agent",
    "report_agent",
]
