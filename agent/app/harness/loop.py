"""Agent Loop limits (PDF table 6-3 minimum: 8 turns, 120 s per task, same tool 3 times)."""
from dataclasses import dataclass


class LimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Limits:
    max_graph_steps: int = 8  # LangGraph recursion_limit per task
    task_timeout_s: float = 120.0
    max_same_tool: int = 3
    max_model_calls: int = 16  # director + observer + 2 personas (with one RAG round each) + beat, with headroom

    def check_tool(self, counts, name: str) -> None:
        counts[name] += 1
        if counts[name] > self.max_same_tool and not name.startswith("business."):
            raise LimitExceeded(f"tool {name} called more than {self.max_same_tool} times in one task")

    def check_model_call(self, n: int) -> None:
        if n > self.max_model_calls:
            raise LimitExceeded(f"more than {self.max_model_calls} model calls in one task")
