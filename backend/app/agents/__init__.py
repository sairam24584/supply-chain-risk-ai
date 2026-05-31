"""Supply Chain Risk Intelligence — multi-agent package.

Agent modules
─────────────
supervisor_node.py      query_preprocess_node + supervisor_node
retrieve_node.py        hybrid retrieval + analytics snapshot
supplier_agent.py       Supplier Risk Agent
shipment_agent.py       Shipment Analysis Agent
inventory_agent.py      Inventory Intelligence Agent
recommendation_agent.py Recommendation Agent (plan synthesis)
judge_agent.py          Quality Judge Agent (LLM-as-judge)
report_agent.py         Report Generation Agent

Support modules
───────────────
graph.py               LangGraph wiring (build_graph / get_graph)
state.py               AgentState TypedDict
output_schemas.py      Pydantic output schemas
prompts.py             Prompt templates
llm.py                 LLM factory (gateway → Groq fallback)
query_preprocessor.py  Query rewriting, intent classification, compression
base.py                Shared helpers (_format_hits, _run_specialist, …)
"""
from app.agents.graph import build_graph, get_graph

__all__ = ["build_graph", "get_graph"]
