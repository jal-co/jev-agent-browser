import math
import os
import time

import httpx

from .questions import NEXT_ACTION, TARGET


class TypeSafePolicy:
    def __init__(self, api_key=None, model=None, client=None):
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY")
        if not self.api_key:
            raise ValueError("TYPESAFE_API_KEY is required")
        self.model = model or os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self.client = client or httpx.Client(http2=True, timeout=25)

    def choose(self, state, goal, history):
        elements, targets, controls = action_space(state["actions"])
        labels = {
            "CLICK": "Click an element, button, menu option, autocomplete suggestion, or calendar day.",
            "TYPE_TEXT": "Enter or replace text in an editable field. The driving model will supply the value.",
            "SELECT": "Select an observed dropdown value.",
        }
        operations = {key: labels[key] for key in targets}
        operations.update({key: value["label"] for key, value in controls.items()})
        operations.update(
            DONE="Every requirement is visibly satisfied.",
            BLOCKED="No supported operation can progress.",
        )
        questions = {
            "operation": {
                "type": "choice",
                "criteria": operations,
                "instructions": {"goal": goal, "rules": NEXT_ACTION},
            }
        }
        for operation, candidates in targets.items():
            questions[operation.lower() + "_target"] = {
                "type": "choice",
                "criteria": {
                    index: {
                        "element": f"[{index}] {action['label']}",
                        "current_value": action.get("current_value", action.get("value", "")),
                        **{
                            key: action[key]
                            for key in ("role", "checked", "selected", "expanded")
                            if key in action
                        },
                    }
                    for index, action in candidates.items()
                },
                "instructions": {"goal": goal, "operation": operation, "rules": [NEXT_ACTION, TARGET]},
            }
        body = {
            "model": self.model,
            "state": {
                "page": {key: state[key] for key in ("url", "title", "text")},
                "elements": elements,
                "recent_actions": [
                    {key: item.get(key) for key in ("action", "kind", "text", "page_changed")}
                    for item in history[-10:]
                ],
            },
            "questions": questions,
        }
        started = time.perf_counter()
        result = self._post(body)
        operation_answer = validate_choice(result["answers"].get("operation", {}), operations)
        operation = operation_answer["choice"]
        target = None
        target_answer = None
        probabilities = {}
        if operation in targets:
            target_answer = validate_choice(
                result["answers"].get(operation.lower() + "_target", {}), targets[operation]
            )
            target = target_answer["choice"]
            choice = targets[operation][target]["id"]
            probabilities = {
                action["id"]: target_answer["probabilities"][index]
                for index, action in targets[operation].items()
            }
        else:
            choice = controls[operation]["id"] if operation in controls else operation
            probabilities[choice] = operation_answer["probabilities"][operation]
        return {
            "choice": choice,
            "operation": operation,
            "target": target,
            "confidence": operation_answer["confidence"],
            "probabilities": probabilities,
            "operation_probabilities": operation_answer["probabilities"],
            "target_probabilities": target_answer["probabilities"] if target_answer else {},
            "target_confidence": target_answer["confidence"] if target_answer else None,
            "model": result["model"],
            "usage": result.get("usage", {}),
            "latency_ms": round((time.perf_counter() - started) * 1000),
        }

    def _post(self, body):
        for attempt in range(3):
            try:
                response = self.client.post(
                    "https://api.typesafe.ai/v1/systemone",
                    json=body,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.HTTPError:
                raise RuntimeError("TypeSafe connection failed; no action executed") from None
            if response.status_code in {429, 529, 503} and attempt < 2:
                time.sleep(0.5 * 2**attempt)
                continue
            if response.is_error:
                raise RuntimeError(f"TypeSafe returned HTTP {response.status_code}; no action executed")
            return response.json()
        raise RuntimeError("TypeSafe is unavailable")


def validate_choice(answer, ids):
    try:
        probabilities = answer["probabilities"]
        numbers = [*probabilities.values(), answer["confidence"]]
        valid = (
            answer["choice"] in ids
            and set(probabilities) == set(ids)
            and all(type(number) in (int, float) and math.isfinite(number) and 0 <= number <= 1 for number in numbers)
            and abs(sum(probabilities.values()) - 1) < 0.02
            and probabilities[answer["choice"]] >= max(probabilities.values()) - 1e-6
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Invalid TypeSafe response; no action executed")
    return answer


def action_space(actions):
    elements = []
    indices = {}
    targets = {}
    controls = {}
    operations = {"click": "CLICK", "fill": "TYPE_TEXT", "select": "SELECT"}
    for action in actions:
        kind = action["kind"]
        if kind not in operations:
            controls[action["id"].upper()] = action
            continue
        node = action["node"]
        if node not in indices:
            index = str(len(elements) + 1)
            indices[node] = index
            element = {
                key: action[key]
                for key in ("role", "value", "checked", "selected", "expanded")
                if key in action
            }
            element.update(index=index, label=action["label"].split(" → ")[0], operations=[])
            if kind == "select":
                element["value"] = action.get("current_value", "")
                element["options"] = []
            elements.append(element)
        index = indices[node]
        operation = operations[kind]
        group = targets.setdefault(operation, {})
        element = elements[int(index) - 1]
        if operation not in element["operations"]:
            element["operations"].append(operation)
        target = index
        if kind == "select":
            target = f"{index}:{len(element['options']) + 1}"
            element["options"].append({"index": target, "label": action["label"], "value": action["value"]})
        group[target] = action
    return elements, targets, controls


def field_context(goal, action, page, history):
    return {
        "goal": goal,
        "field": {key: action.get(key) for key in ("label", "role", "value")},
        "page": {"title": page["title"], "text": page["text"][:6000]},
        "recent_actions": [{key: item.get(key) for key in ("action", "text")} for item in history[-6:]],
    }
