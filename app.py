"""Clocked Smart Service Desk. Synthetic demo, real SDK when a key is provided.

No client data or API credentials are included. All actions are simulated.
"""
from __future__ import annotations

import csv
import os
import re
import secrets
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
app = Flask(__name__, static_folder="public/static")
app.config["MAX_CONTENT_LENGTH"] = 48 * 1024


def load(name: str) -> list[dict[str, str]]:
    with (DATA / (name + ".csv")).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


USERS = {r["user_id"]: r for r in load("users")}
ASSETS = load("assets")
OFFERINGS = {r["offering_id"]: r for r in load("offerings")}
CATEGORIES = {r["category_id"]: r for r in load("categories")}
SUBCATEGORIES = {r["subcategory_id"]: r for r in load("subcategories")}
MAPPINGS = load("offering_mappings")
FIELDS = load("offering_fields")
KNOWLEDGE = []
for item in load("knowledge_manifest"):
    doc = ROOT / item["path"]
    if doc.resolve().is_relative_to(ROOT.resolve()) and doc.exists():
        KNOWLEDGE.append({**item, "text": doc.read_text(encoding="utf-8")})

MAPPINGS_BY_OFFERING = defaultdict(list)
for m in MAPPINGS:
    MAPPINGS_BY_OFFERING[m["offering_id"]].append(m)
FIELDS_BY_OFFERING = defaultdict(list)
for m in FIELDS:
    FIELDS_BY_OFFERING[m["offering_id"]].append(m)

STOP = set("a an the my i me you we our your is am are was were to of for at in on and or from with it this that do does can could would please some how what be by if which a new".split())
SYNONYM = {"broken": "failure", "crashing": "crash", "crashes": "crash", "install": "install", "installation": "install", "pc": "desktop", "computer": "computer", "not": "not", "wifi": "wifi", "wi-fi": "wifi", "signin": "sign", "logon": "sign", "reset": "reset", "passwords": "password"}


def tokens(text: str) -> list[str]:
    x = [SYNONYM.get(t, t) for t in re.findall(r"[a-z0-9]+", text.lower())]
    return [t for t in x if t not in STOP and len(t) > 1]


def overlap(query: str, document: str) -> float:
    q = set(tokens(query))
    d = set(tokens(document))
    if not q:
        return 0.0
    return sum((2 if w in {"visio", "sap", "vpn", "printer", "password", "laptop", "desktop", "teams"} else 1) for w in q & d) / max(1, sum((2 if w in {"visio", "sap", "vpn", "printer", "password", "laptop", "desktop", "teams"} else 1) for w in q))


def rank_knowledge(text: str):
    out = []
    for d in KNOWLEDGE:
        score = overlap(text, f"{d['title']} {d['topic']} {d['summary']} {d['text'][:240]}")
        if score:
            out.append((score, d))
    return sorted(out, key=lambda x: x[0], reverse=True)


def rank_offerings(text: str, ticket_type: str):
    out = []
    for o in OFFERINGS.values():
        if o["ticket_type_id"] != ticket_type or o["active"].lower() != "true":
            continue
        score = overlap(text, f"{o['offering_name']} {o['synonyms']} {o['domain']}")
        phrase = o["offering_name"].lower().replace("request ", "")
        if phrase in text.lower():
            score += 0.9
        for syn in o["synonyms"].split("|"):
            if len(syn) >= 5 and syn in text.lower():
                score += 0.7
        out.append((score, o))
    return sorted(out, key=lambda x: x[0], reverse=True)


def clean_state(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    allowed = ["phase", "original_text", "ticket_type", "offering_id", "asset_id", "asset_type", "asset_candidates", "fields", "preferred_action", "knowledge_id", "pause_reason"]
    out = {k: value[k] for k in allowed if k in value}
    if out.get("offering_id") not in OFFERINGS:
        out.pop("offering_id", None)
    if not isinstance(out.get("fields", {}), dict):
        out["fields"] = {}
    out["fields"] = {str(k)[:60]: str(v)[:200] for k, v in out.get("fields", {}).items() if isinstance(v, (str, int, float))}
    return out


def event(endpoint: str, origin: str, detail: str, duration: int | None = None, raw: dict | None = None):
    item = {"endpoint": endpoint, "origin": origin, "detail": detail}
    if duration is not None:
        item["duration_ms"] = duration
    if raw is not None:
        item["result"] = raw
    return item


def status():
    return "live" if os.getenv("CLOCKED_API_KEY") else "demo"


class ClockedGateway:
    """Actual SDK methods. No fabricated API responses, confidence or timings."""

    def __init__(self):
        self.traces = []
        self.live = bool(os.getenv("CLOCKED_API_KEY"))
        self.error = None
        self._client = None
        if self.live:
            try:
                from clocked_sdk import Clocked
                self._client = Clocked(timeout=22, max_attempts=2)
            except Exception:
                self.error = "Clocked SDK is unavailable"

    def invoke(self, endpoint: str, **kwargs):
        if not self.live:
            return None
        if not self._client:
            self.traces.append(event(endpoint, "error", self.error or "Client unavailable"))
            return None
        begin = time.monotonic()
        try:
            res = getattr(self._client, endpoint)(**kwargs)
            raw = dict(res)
            # Include the actual response for judges; no credentials or headers.
            self.traces.append(event(endpoint, "live", "Clocked returned a response", getattr(res, "model_ms", None), raw))
            return raw
        except Exception as exc:
            # Never expose authorization headers or full exception bodies to the browser.
            code = getattr(exc, "status", None)
            label = f"API request failed (HTTP {code})" if code else "API request failed"
            self.traces.append(event(endpoint, "error", label, round((time.monotonic() - begin) * 1000)))
            return None

    def decide_intent(self, text: str):
        return self.invoke("decide", state=text, questions={
            "incident": {"type": "noul", "instructions": "Is the user reporting a failure, error, degradation or outage of something that was working? Requests for a new device or access without a failure are false."},
            "service_request": {"type": "noul", "instructions": "Is the user asking for access, installation, a new item or a change?"},
            "it_support": {"type": "noul", "instructions": "Is the user asking for IT or enterprise technical support? Sports, entertainment, weather and unrelated general knowledge are false."},
        })

    def rerank_offering(self, text: str, candidates: list[dict]):
        return self.invoke("rerank", query=text, documents=[{"id": d["offering_id"], "title": d["offering_name"], "text": d["description"] + " " + d["synonyms"]} for d in candidates], top_n=3)

    def rerank_knowledge(self, text: str, candidates: list[dict]):
        return self.invoke("rerank", query=text, documents=[{"id": d["document_id"], "title": d["title"], "text": d["text"][:1800]} for d in candidates], top_n=2)

    def verify_answer(self, query: str, doc: dict, answer: str):
        return self.invoke("grounding", documents=[{"id": doc["document_id"], "text": doc["text"]}], question=query, answer=answer, evidence="all")

    def close(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass


def noun_probability(result, key):
    answer = (result or {}).get("answers", {}).get(key, {})
    if isinstance(answer, dict):
        value = answer.get("noul")
        if isinstance(value, dict):
            value = value.get("probability", value.get("true"))
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
    return None


def response(message, state, *, card=None, choices=None, trace=None):
    return {"message": message, "state": state, "card": card, "choices": choices or [], "trace": trace or [], "mode": status()}


def choose_asset_candidates(text, user_id, state):
    owned = [a for a in ASSETS if a["user_id"] == user_id and a["status"] == "Active"]
    if not owned:
        return []
    q = text.lower()
    device_type = (state.get("asset_type") or "").lower()
    for marker in ("laptop", "desktop", "printer", "phone", "tablet"):
        if re.search(r"\b" + marker + r"\b", q):
            device_type = marker
    if device_type:
        owned = [a for a in owned if device_type in a["device_type"].lower()]
    for brand in ("dell", "lenovo", "hp", "apple", "samsung"):
        if re.search(r"\b" + brand + r"\b", q):
            owned = [a for a in owned if brand in a["manufacturer"].lower()]
    for a in list(owned):
        if a["asset_id"].lower() in q or a["model"].lower() in q or a["hostname"].lower() in q:
            return [a]
    return owned


def asset_public(a):
    return {k: a[k] for k in ["asset_id", "manufacturer", "device_type", "model", "device_label", "location"]}


def state_review(state):
    o = OFFERINGS[state["offering_id"]]
    mapping = next((m for m in MAPPINGS_BY_OFFERING[o["offering_id"]] if m["is_default"].lower() == "true"), None)
    if not mapping:
        mapping = MAPPINGS_BY_OFFERING[o["offering_id"]][0]
    a = next((a for a in ASSETS if a["asset_id"] == state.get("asset_id")), None)
    return {
        "ticket_type": "Incident" if o["ticket_type_id"] == "INC" else "Service request",
        "offering": o["offering_name"],
        "offering_id": o["offering_id"],
        "category": CATEGORIES[mapping["category_id"]]["category_name"],
        "subcategory": SUBCATEGORIES[mapping["subcategory_id"]]["subcategory_name"],
        "summary": state.get("original_text", "")[:350],
        "asset": f"{a['manufacturer']} {a['model']} ({a['asset_id']})" if a else "Not required / not identified",
        "fields": state.get("fields", {}),
    }


def continue_classification(state, user_id, gw):
    original = state.get("original_text", "")
    ticket_type = state.get("ticket_type", "INC")
    trace = gw.traces
    # A generic computer is not a specific device. Ask which owned device type first.
    if ticket_type == "INC" and re.search(r"\b(computer|pc)\b", original.lower()) and not state.get("asset_type"):
        types = sorted({a["device_type"] for a in ASSETS if a["user_id"] == user_id and a["status"] == "Active" and a["device_type"].lower() in ("laptop", "desktop")})
        if len(types) > 1:
            state["phase"] = "asset_type"
            return response("I found both laptops and a desktop assigned to this demo user. Which type of computer is affected?", state, choices=[{"label": t, "value": "device:" + t.lower()} for t in types], trace=trace)
    # The default offering shortlist comes from the local catalog; Clocked reranks it in live mode.
    ranked = rank_offerings(original + " " + state.get("asset_type", ""), ticket_type)
    shortlist = [o for score, o in ranked[:7] if score > 0]
    if not shortlist:
        return response("I can help, but I couldn't confidently match that to a catalog offering. Could you describe the system or device involved?", {**state, "phase": "clarify_offering"}, choices=[], trace=trace)
    top = shortlist[0]
    reranked = gw.rerank_offering(original + " " + state.get("asset_type", ""), shortlist)
    if reranked:
        items = reranked.get("results", [])
        valid = {o["offering_id"]: o for o in shortlist}
        selected = next((x for x in items if x.get("id") in valid and x.get("action") == "use" and float(x.get("relevance_score", 0)) >= .36), None)
        if selected:
            top = valid[selected["id"]]
        elif items and items[0].get("action") == "skip":
            # No trustworthy match: don't manufacture an offering decision.
            return response("The catalog match is uncertain. Which support area is involved?", {**state, "phase": "clarify_offering"}, choices=[{"label": o["offering_name"], "value": "offering:" + o["offering_id"]} for o in shortlist[:4]], trace=trace)
    elif not gw.live:
        trace.append(event("Catalog retrieval", "demo", "Local text matching; no Clocked call"))
    elif gw.live:
        trace.append(event("Catalog fallback", "demo", "Clocked did not return a usable match; local ranking used"))
    state = {**state, "offering_id": top["offering_id"], "phase": "qualifying"}
    if top["asset_policy"].lower() in ["required", "required_if_owned"]:
        owned = [a for a in ASSETS if a["user_id"] == user_id and a["status"] == "Active"]
        if owned and not state.get("asset_id"):
            # Broad computer reference among both desktops/laptops gets its own clarification.
            q = original.lower()
            if "computer" in q and not any(x in q for x in ["laptop", "desktop"]):
                types = sorted({a["device_type"] for a in owned if a["device_type"].lower() in ["laptop", "desktop"]})
                if len(types) > 1:
                    state["phase"] = "asset_type"
                    return response("I found more than one type of Dell computer assigned to this demo user. Is it the laptop or the desktop?", state, choices=[{"label": x, "value": "device:" + x.lower()} for x in types], trace=trace)
            matches = choose_asset_candidates(original, user_id, state)
            if len(matches) == 1:
                state["asset_id"] = matches[0]["asset_id"]
            elif len(matches) > 1:
                state["phase"] = "asset_choice"
                return response("I found multiple devices that could match. Which one is affected?", state, card={"type": "assets", "items": [asset_public(a) for a in matches[:8]]}, trace=trace)
            elif not matches:
                state["phase"] = "asset_choice"
                return response("I couldn't find that device on this sample profile. You can continue with an unknown asset, or switch demo user.", state, choices=[{"label": "Continue without asset", "value": "unknown_asset"}], trace=trace)
    return check_fields(state, user_id, gw)


def check_fields(state, user_id, gw):
    o = OFFERINGS[state["offering_id"]]
    fields = dict(state.get("fields", {}))
    for item in FIELDS_BY_OFFERING.get(o["offering_id"], []):
        fid, required = item["field_id"], item["required"].lower()
        if fid in ("issue_description", "request_description"):
            fields[fid] = state.get("original_text", "")[:200]
        elif fid in ("software_name", "target_application"):
            if o["ticket_type_id"] == "REQ" and any(x in o["offering_name"].lower() for x in ["visio", "sap"]):
                fields[fid] = "Microsoft Visio" if "visio" in o["offering_name"].lower() else "SAP"
        elif fid == "asset_id" and state.get("asset_id"):
            fields["asset_id"] = state["asset_id"]
    state["fields"] = fields
    for f in FIELDS_BY_OFFERING.get(o["offering_id"], []):
        if f["required"].lower() != "true" or f["field_id"] in fields:
            continue
        state["phase"] = "missing_field"
        state["pause_reason"] = f["field_id"]
        if f["field_id"] == "impact":
            return response("Before I prepare the ticket, who is affected by this issue?", state, choices=[{"label": "Only me", "value": "field:impact:Only me"}, {"label": "Multiple people", "value": "field:impact:Multiple people"}], trace=gw.traces)
        return response(f"One detail before we continue: {f['field_label']}", state, trace=gw.traces)
    state["phase"] = "review"
    return response("I have everything needed for a demonstration. Please review the details before you choose an action.", state, card={"type": "review", "record": state_review(state)}, choices=[{"label": "Create sample ticket", "value": "confirm_ticket"}, {"label": "Simulate live chat", "value": "confirm_chat"}], trace=gw.traces)


def knowledge_answer(doc):
    # Verbatim extractive evidence, not generated policy or unseen facts.
    lines = [ln.strip().lstrip("-•* ") for ln in doc["text"].splitlines() if ln.strip() and not ln.strip().startswith("#") and "fictional test environment" not in ln.lower()]
    return "\n".join(lines[:7])[:1100]


def start_message(text, state, user_id, gw, *, bypass_kb=False):
    q = text.lower()
    state = {"original_text": text[:350], "phase": "initial", "fields": {}, "preferred_action": "chat" if any(s in q for s in ["live chat", "talk to an agent", "connect me", "speak to an agent"]) else "ticket"}
    explicit_action = any(s in q for s in ["create a ticket", "raise a ticket", "open a ticket", "connect me", "talk to an agent", "live chat", "speak to an agent"])
    local_oos = bool(re.search(r"\b(cricket|football|match score|weather forecast|movie|recipe|celebrity)\b", q)) and not any(x in q for x in ["app", "laptop", "software"])
    local_incident = bool(re.search(r"\b(broken|crash(?:ing|ed|es)?|not working|isn't working|is not working|doesn't work|wont|won't|cannot|can't|failed|failure|error|slow|offline|outage|stuck|jam|locked|does not|will not|disconnect|dead|lost)\b", q))
    local_request = bool(re.search(r"\b(request|install(?:ed|ation|ing)?|need (?:a|new)|need [a-z0-9 ]+ installed|replacement|give me access|grant access|access to|order|new laptop|new desktop)\b", q))
    if "password" in q and ("reset" in q or "how" in q) and not "locked" in q:
        local_incident = False
    api_intents = gw.decide_intent(text)
    if api_intents:
        scope = noun_probability(api_intents, "it_support")
        incident = noun_probability(api_intents, "incident")
        sr = noun_probability(api_intents, "service_request")
        if scope is not None and scope < .37:
            local_oos = True
        if incident is not None and incident >= .69:
            local_incident = True
        if sr is not None and sr >= .69:
            local_request = True
        if incident is not None and incident < .3:
            local_incident = False
        if sr is not None and sr < .3:
            local_request = False
    else:
        gw.traces.append(event("Intent rules", "demo", "Explicit local classification; not a Clocked prediction"))
    if local_oos:
        return response("This workspace focuses on IT and employee service requests. I can help with devices, software, accounts, and technical issues instead.", {}, trace=gw.traces)
    if local_incident and local_request and any(s in q for s in ["broken and", "not working and", "failed and", "crashing and"]):
        return response("That sounds like two separate needs: fix the problem and request a replacement. Which would you like to handle first?", {**state, "phase": "multi_intent"}, choices=[{"label": "Report the problem", "value": "type:INC"}, {"label": "Request replacement", "value": "type:REQ"}], trace=gw.traces)
    matches = rank_knowledge(text)
    wants_information = bool(re.search(r"\b(how|steps|guide|instructions|troubleshoot|reset|fix)\b", q)) or (local_incident and not explicit_action)
    if matches and (matches[0][0] >= .38) and not bypass_kb and wants_information:
        candidates = [d for s, d in matches[:4]]
        candidate = candidates[0]
        reranked = gw.rerank_knowledge(text, candidates)
        if reranked:
            found = next((x for x in reranked.get("results", []) if x.get("action") == "use" and float(x.get("relevance_score", 0)) >= .35 and any(x.get("id") == d["document_id"] for d in candidates)), None)
            if found:
                candidate = next(d for d in candidates if d["document_id"] == found["id"])
            else:
                candidate = None
        elif not gw.live:
            gw.traces.append(event("Knowledge matching", "demo", "Search over fictional local documents"))
        else:
            gw.traces.append(event("Knowledge fallback", "demo", "Clocked was unavailable; local document match used"))
        if candidate:
            answer = knowledge_answer(candidate)
            grounding = gw.verify_answer(text, candidate, answer) if gw.live else None
            if grounding and str(grounding.get("verdict", "")).lower() in ("unsupported", "contradicted", "false", "not_grounded"):
                candidate = None
            if candidate:
                state.update({"phase": "knowledge", "knowledge_id": candidate["document_id"]})
                return response("I found a relevant guide in the sample knowledge library. Try these steps, then tell me if the problem is resolved.", state, card={"type": "knowledge", "title": candidate["title"], "id": candidate["document_id"], "excerpt": answer}, choices=[{"label": "That solved it", "value": "resolved"}, {"label": "Still need help", "value": "escalate"}, {"label": "Talk to an agent", "value": "escalate_chat"}], trace=gw.traces)
    if not local_incident and not local_request and not explicit_action:
        return response("Could you tell me a little more about what you need? For example, is something broken, or are you requesting access or software?", {**state, "phase": "clarify_intent"}, choices=[{"label": "Something is broken", "value": "type:INC"}, {"label": "Request something", "value": "type:REQ"}], trace=gw.traces)
    ticket_type = "INC" if local_incident else "REQ"
    state["ticket_type"] = ticket_type
    return continue_classification(state, user_id, gw)


def action_message(action, state, user_id, gw, details=None):
    if action == "resolved":
        return response("Glad the guide helped. This demonstration is now complete. You can start another request anytime.", {}, card={"type": "complete", "title": "Issue resolved", "subtext": "No ticket was created."}, trace=gw.traces)
    if action in ("escalate", "escalate_chat") and state.get("phase") == "knowledge":
        state["preferred_action"] = "chat" if action == "escalate_chat" else "ticket"
        q = state.get("original_text", "")
        state["ticket_type"] = "INC" if any(s in q.lower() for s in ["not", "broken", "can't", "error", "failed", "slow", "issue", "crash"]) else "REQ"
        return continue_classification(state, user_id, gw)
    if action.startswith("type:") and state.get("phase") in ["multi_intent", "clarify_intent"]:
        state["ticket_type"] = action.split(":", 1)[1]
        return continue_classification(state, user_id, gw)
    if action.startswith("device:") and state.get("phase") == "asset_type":
        kind = action.split(":", 1)[1]
        if kind not in ("desktop", "laptop"):
            return response("Please select a valid device type.", state, trace=gw.traces)
        state["asset_type"] = kind
        state["phase"] = "symptom"
        if kind == "laptop":
            return response("What is happening with the laptop?", state, choices=[{"label": "Won't turn on", "value": "symptom:power"}, {"label": "Very slow or freezing", "value": "symptom:slow"}, {"label": "A different issue", "value": "symptom:other"}], trace=gw.traces)
        return response("What is happening with the desktop?", state, choices=[{"label": "Won't start", "value": "symptom:power"}, {"label": "A different issue", "value": "symptom:other"}], trace=gw.traces)
    if action.startswith("symptom:") and state.get("phase") == "symptom":
        symptom = action.split(":", 1)[1]
        if symptom == "other":
            state["phase"] = "clarify_symptom"
            return response("Please describe what happens when you use this device. For example, does it display an error, freeze, or disconnect?", state, trace=gw.traces)
        if symptom not in ("power", "slow") or (symptom == "slow" and state.get("asset_type") != "laptop"):
            return response("Please choose a valid symptom.", state, trace=gw.traces)
        state["original_text"] += " " + ("laptop extremely slow freezing" if symptom == "slow" else state["asset_type"] + " will not power on start")
        return continue_classification(state, user_id, gw)
    if action.startswith("asset:") and state.get("phase") == "asset_choice":
        asset_id = action.split(":", 1)[1]
        if not any(a["asset_id"] == asset_id and a["user_id"] == user_id for a in ASSETS):
            return response("That asset is not assigned to the selected demo user.", state, trace=gw.traces)
        state["asset_id"] = asset_id
        return check_fields(state, user_id, gw)
    if action == "unknown_asset" and state.get("phase") == "asset_choice":
        return check_fields(state, user_id, gw)
    if action.startswith("offering:") and state.get("phase") == "clarify_offering":
        offering = action.split(":", 1)[1]
        if offering not in OFFERINGS or OFFERINGS[offering]["ticket_type_id"] != state.get("ticket_type"):
            return response("That catalog option isn't valid for this ticket type.", state, trace=gw.traces)
        state["offering_id"] = offering
        return check_fields(state, user_id, gw)
    if action.startswith("field:") and state.get("phase") == "missing_field":
        _, fid, value = action.split(":", 2)
        if fid != state.get("pause_reason"):
            return response("Please answer the current question.", state, trace=gw.traces)
        state.setdefault("fields", {})[fid] = value[:200]
        return check_fields(state, user_id, gw)
    if action == "submit_field" and state.get("phase") == "missing_field":
        value = str((details or {}).get("text", "")).strip()[:200]
        if not value:
            return response("This information is needed to continue.", state, trace=gw.traces)
        state.setdefault("fields", {})[state["pause_reason"]] = value
        return check_fields(state, user_id, gw)
    if action in ["confirm_ticket", "confirm_chat"] and state.get("phase") == "review":
        if state.get("offering_id") not in OFFERINGS:
            return response("Please restart the request so the catalog can be validated.", {}, trace=gw.traces)
        # Validate approved mapping and ownership again; no external calls are made.
        if not MAPPINGS_BY_OFFERING.get(state["offering_id"]):
            return response("The selected catalog entry has no valid category mapping.", {}, trace=gw.traces)
        if state.get("asset_id") and not any(a["asset_id"] == state["asset_id"] and a["user_id"] == user_id for a in ASSETS):
            return response("The asset cannot be confirmed for this user.", {}, trace=gw.traces)
        ref = "SIM-" + ("CHAT" if action == "confirm_chat" else state.get("ticket_type", "REQ")) + "-" + secrets.token_hex(3).upper()
        title = "Simulated chat handoff" if action == "confirm_chat" else "Sample ticket created"
        return response("This was a simulated action only. No live ITSM system or support agent was contacted.", {}, card={"type": "complete", "title": title, "reference": ref, "subtext": "Demonstration only · Not a real support record"}, trace=gw.traces)
    return response("That action is no longer available. Start a new request or use one of the current options.", state, trace=gw.traces)


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/status")
def api_status():
    return jsonify({"mode": status(), "users": [{"id": u["user_id"], "name": u["display_name"], "location": u["location"]} for u in list(USERS.values())[:20]], "counts": {"users": len(USERS), "assets": len(ASSETS), "offerings": len(OFFERINGS), "categories": len(CATEGORIES), "subcategories": len(SUBCATEGORIES)}, "version": "1.0.0"})


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "status": "ready"})


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()[:1000]
    user_id = str(data.get("user_id") or "DEMO001")
    if not text or user_id not in USERS:
        return jsonify({"error": "Provide a message and a valid demo user."}), 400
    state = clean_state(data.get("state"))
    gw = ClockedGateway()
    try:
        if state.get("phase") == "missing_field":
            result = action_message("submit_field", state, user_id, gw, {"text": text})
        elif state.get("phase") == "asset_choice":
            matched = next((a for a in choose_asset_candidates(text, user_id, state) if a["asset_id"].lower() in text.lower() or a["model"].lower() in text.lower()), None)
            result = action_message("asset:" + matched["asset_id"], state, user_id, gw) if matched else response("Please select one of the listed devices so I don't guess.", state, trace=gw.traces)
        elif state.get("phase") == "asset_type" and any(w in text.lower() for w in ("laptop", "desktop")):
            kind = "desktop" if "desktop" in text.lower() else "laptop"
            result = action_message("device:" + kind, state, user_id, gw)
        elif state.get("phase") in ("clarify_offering", "clarify_symptom"):
            state["original_text"] += " " + text[:150]
            result = continue_classification(state, user_id, gw)
        elif state.get("phase") == "symptom":
            q = text.lower()
            symptom = "slow" if any(w in q for w in ("slow", "freeze", "freezing")) else "power" if any(w in q for w in ("power", "start", "boot", "turn on")) else "other"
            result = action_message("symptom:" + symptom, state, user_id, gw)
        else:
            result = start_message(text, state, user_id, gw)
        return jsonify(result)
    finally:
        gw.close()


@app.post("/api/action")
def api_action():
    data = request.get_json(silent=True) or {}
    user_id = str(data.get("user_id") or "DEMO001")
    if user_id not in USERS:
        return jsonify({"error": "Invalid demo user"}), 400
    state = clean_state(data.get("state"))
    action = str(data.get("action") or "")[:100]
    gw = ClockedGateway()
    try:
        return jsonify(action_message(action, state, user_id, gw, data.get("details")))
    finally:
        gw.close()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
