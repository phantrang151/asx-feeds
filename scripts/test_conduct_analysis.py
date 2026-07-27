"""
Manual test for the memory-aware conduct_analysis node.

Run this, then look at the second response - it should reference the first run's
insight as a past example (episodic memory), and any facts the agent chose to store
via manage_memory during the first run should be retrievable in the second (semantic
memory). Procedural instructions are the same both times unless you call
update_procedural_instructions() in between.
"""

from langchain_core.messages import HumanMessage

from agent.chat.graph import graph
from config import TEST_USER_ID

config = {
    "configurable": {
        "thread_id": "test-analysis-1",
        "langgraph_user_id": TEST_USER_ID,
    }
}

print("=== First question ===")
response = graph.invoke(
    {"messages": [HumanMessage(content="Why is Telstra's profit increasing? TLS.AX")]},
    config=config,
)
for m in response["messages"]:
    m.pretty_print()

print("\n=== Second, similar question (should surface episodic memory) ===")
response = graph.invoke(
    {"messages": [HumanMessage(content="Is Telstra's profit growth sustainable? TLS.AX")]},
    config=config,
)
for m in response["messages"]:
    m.pretty_print()
