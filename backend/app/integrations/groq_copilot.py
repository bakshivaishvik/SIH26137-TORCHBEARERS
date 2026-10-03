"""
GenAI Dispatcher Copilot (Section 4.1).

Integrates an LLM via the Groq API with real function/tool calling against
the optimizer's live state (the explainability log + current routes), so a
dispatcher can ask e.g. "Why was Incident #42 delayed?" and get an answer
grounded in the actual routing log -- not canned text. Requires
GROQ_API_KEY to be set; the tool-calling loop itself is fully real and
runs against your live `explainability.logger` DB and current route state
regardless of which Groq model you point it at.
"""
from __future__ import annotations
import os
import json
from groq import Groq

from app.explainability.logger import query_decisions

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_decision_log",
            "description": "Query the routing/rerouting decision log for a vehicle or event type, "
                            "returning triggering events, before/after routes, and cost deltas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vehicle_id": {"type": "integer", "description": "Filter by vehicle/ambulance id"},
                    "event_type": {"type": "string",
                                   "enum": ["new_request", "hazard", "forecast_update", "insertion"]},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_routes",
            "description": "Get the current live route assignment for every vehicle in the fleet, "
                            "as computed by the QPSO optimizer.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _tool_query_decision_log(vehicle_id=None, event_type=None, limit=10):
    return query_decisions(vehicle_id=vehicle_id, event_type=event_type, limit=limit)


def _tool_get_current_routes(live_state_provider):
    return live_state_provider()


class DispatcherCopilot:
    def __init__(self, live_state_provider, api_key: str | None = None, model: str = GROQ_MODEL):
        if not (api_key or GROQ_API_KEY):
            raise RuntimeError("GROQ_API_KEY not set. Export it or pass api_key= to DispatcherCopilot.")
        self.client = Groq(api_key=api_key or GROQ_API_KEY)
        self.model = model
        self.live_state_provider = live_state_provider

    def ask(self, question: str) -> str:
        messages = [
            {"role": "system", "content": "You are a dispatcher copilot for an ambulance fleet routing "
             "system. Answer using only facts returned by your tools -- the decision log and live "
             "route state. Be concise and cite specific vehicle IDs, links, and cost numbers."},
            {"role": "user", "content": question},
        ]
        for _ in range(4):  # bounded tool-calling loop
            resp = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=TOOLS, tool_choice="auto",
            )
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return msg.content
            messages.append(msg)
            for call in msg.tool_calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                if name == "query_decision_log":
                    result = _tool_query_decision_log(**args)
                elif name == "get_current_routes":
                    result = _tool_get_current_routes(self.live_state_provider)
                else:
                    result = {"error": f"unknown tool {name}"}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)})
        return "I couldn't resolve that within the tool-call budget -- try narrowing the question."
