"""LangGraph wiring — Supervisor-routed multi-agent topology.

   START
     │
     ▼
   query_preprocess   (rewrite, intent, compression-ready)
     │
     ▼
   supervisor         (decides which specialists to run)
     │
     ▼
   retrieve           (hybrid: Chroma + BM25 + RRF + rerank + compression)
     │
     ├──► supplier_agent  ─┐
     ├──► shipment_agent  ─┼──► recommendation ──► judge ──► report ──► END
     └──► inventory_agent ─┘

Specialists no-op cheaply when the supervisor turns them off.
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    inventory_agent,
    judge_agent,
    query_preprocess_node,
    recommendation_agent,
    report_agent,
    retrieve_node,
    shipment_agent,
    supervisor_node,
    supplier_agent,
)
from app.agents.state import AgentState
from app.core.logging import logger


def build_graph(with_memory: bool = True):
    g = StateGraph(AgentState)
    g.add_node("query_preprocess",       query_preprocess_node)
    g.add_node("supervisor",             supervisor_node)
    g.add_node("retrieve",               retrieve_node)
    g.add_node("supplier_agent",         supplier_agent)
    g.add_node("shipment_agent",         shipment_agent)
    g.add_node("inventory_agent",        inventory_agent)
    g.add_node("recommendation_agent",   recommendation_agent)
    g.add_node("judge_agent",            judge_agent)
    g.add_node("report_agent",           report_agent)

    g.add_edge(START, "query_preprocess")
    g.add_edge("query_preprocess", "supervisor")
    g.add_edge("supervisor", "retrieve")

    g.add_edge("retrieve", "supplier_agent")
    g.add_edge("retrieve", "shipment_agent")
    g.add_edge("retrieve", "inventory_agent")

    g.add_edge("supplier_agent", "recommendation_agent")
    g.add_edge("shipment_agent", "recommendation_agent")
    g.add_edge("inventory_agent", "recommendation_agent")
    g.add_edge("recommendation_agent", "judge_agent")
    g.add_edge("judge_agent", "report_agent")
    g.add_edge("report_agent", END)

    checkpointer = MemorySaver() if with_memory else None
    return g.compile(checkpointer=checkpointer)


@lru_cache
def get_graph():
    g = build_graph()
    logger.info("LangGraph supervisor-routed multi-agent graph compiled.")
    return g


__all__ = ["build_graph", "get_graph"]
