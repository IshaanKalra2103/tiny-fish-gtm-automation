"""Trust score (spec §6.3): six evidence signals summed to 0-100, then a badge."""
from .schemas import Signal, Tool, Trust

WEIGHTS = {"identity": 25, "longevity": 15, "data_handling": 20, "pricing": 15, "reviews": 15, "viability": 10}


def score_signals(signals: dict[str, Signal], human_approved: bool) -> Trust:
    clamped: dict[str, Signal] = {}
    for name, weight in WEIGHTS.items():
        s = signals.get(name) or Signal(points=0, max=weight, value="no evidence found")
        clamped[name] = s.model_copy(update={"points": max(0, min(weight, s.points)), "max": weight})
    score = sum(s.points for s in clamped.values())
    if score < 50 or clamped["identity"].points == 0:
        badge = "unknown"
    elif score >= 75 and human_approved:
        badge = "verified"
    else:
        badge = "caution"
    return Trust(score=score, badge=badge, signals=clamped)


def can_agent_setup(tool: Tool) -> bool:
    return tool.trust.badge == "verified" and tool.setup.agent_setup and bool(tool.setup.playbook)
