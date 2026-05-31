"""LangGraph wiring — Supervisor-routed multi-agent topology.

   START
     │
     ▼
   query_preprocess_node   (rewrite, intent detection)
     │
     ▼
   supervisor_node         (decides which specialists to run)
     │
     ▼
   retrieve_node           (hybrid: Chroma + BM25 + RRF + rerank + compression)
     │
     ├──► supplier_agent   ─┐
     ├──► shipment_agent   ─┼──► recommendation_agent ──► judge_agent ──► report_agent ──► END
     └──► inventory_agent  ─┘

Specialists no-op cheaply when the supervisor turns them off.
Each agent lives in its own module under app/agents/.
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.inventory_agent import inventory_agent
from app.agents.judge_agent import judge_agent
from app.agents.recommendation_agent import recommendation_agent
from app.agents.report_agent import report_agent
from app.agents.retrieve_node import retrieve_node
from app.agents.shipment_agent import shipment_agent
from app.agents.state import AgentState
from app.agents.supervisor_node import query_preprocess_node, supervisor_node
from app.agents.supplier_agent import supplier_agent
from app.core.logging import logger


def build_graph(with_memory: bool = True):
    g = StateGraph(AgentState)

    # Register all nodes
    g.add_node("query_preprocess",      query_preprocess_node)
    g.add_node("supervisor",            supervisor_node)
    g.add_node("retrieve",              retrieve_node)
    g.add_node("supplier_agent",        supplier_agent)
    g.add_node("shipment_agent",        shipment_agent)
    g.add_node("inventory_agent",       inventory_agent)
    g.add_node("recommendation_agent",  recommendation_agent)
    g.add_node("judge_agent",           judge_agent)
    g.add_node("report_agent",          report_agent)

    # Pipeline edges
    g.add_edge(START,              "query_preprocess")
    g.add_edge("query_preprocess", "supervisor")
    g.add_edge("supervisor",       "retrieve")

    # Parallel specialist fan-out
    g.add_edge("retrieve",         "supplier_agent")
    g.add_edge("retrieve",         "shipment_agent")
    g.add_edge("retrieve",         "inventory_agent")

    # Fan-in → synthesis → quality check → report
    g.add_edge("supplier_agent",        "recommendation_agent")
    g.add_edge("shipment_agent",        "recommendation_agent")
    g.add_edge("inventory_agent",       "recommendation_agent")
    g.add_edge("recommendation_agent",  "judge_agent")
    g.add_edge("judge_agent",           "report_agent")
    g.add_edge("report_agent",          END)

    checkpointer = MemorySaver() if with_memory else None
    return g.compile(checkpointer=checkpointer)


@lru_cache
def get_graph():
    g = build_graph()
    logger.info("LangGraph multi-agent graph compiled successfully.")
    return g


__all__ = ["build_graph", "get_graph"]
