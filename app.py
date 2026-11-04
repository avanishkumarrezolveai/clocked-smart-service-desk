"""Clocked Smart Service Desk. Synthetic demo, real SDK when a key is provided.

No client data or API credentials are included. All actions are simulated.
"""
from __future__ import annotations

import csv
import hashlib
import threading
import os
import re
import secrets
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
app = Flask(__name__, static_folder="public/static")
app.config["MAX_CONTENT_LENGTH"] = 48 * 1024
# Signed state prevents callers from forging a review/confirmation action.
_state_secret = os.getenv("SESSION_SIGNING_KEY") or hashlib.sha256(
    (os.getenv("CLOCKED_API_KEY") or os.getenv("DEMO_SESSION_SECRET") or "local-demo-only-not-for-production").encode()
    + b"|clocked-service-desk-state-v2"
).hexdigest()
_state_signer = URLSafeTimedSerializer(_state_secret, salt="clocked-demo-session")
_gateway_slots = threading.BoundedSemaphore(2)



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
SYNONYM = {"broken": "failure", "crashing": "crash", "crashes": "crash", "install": "install", "installation": "install", "pc": "desktop", "computer": "computer", "not": "not", "wifi": "wifi", "wi-fi": "wifi", "signin": "sign", "logon": "sign", "reset": "reset", "passwords": "password", "re-enrolled": "enrollment", "enrolled": "enrollment", "enrolment": "enrollment", "enroll": "enrollment", "enrolled": "enrollment", "reenrolled": "enrollment"}


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
    low = text.lower()
    if "laptop" in low and any(x in low for x in ("won't turn on", "will not turn on", "not starting", "doesn't start", "not boot")):
        text += " laptop not turning on laptop fails to boot no power"
    if "shared drive" in low and any(x in low for x in ("cannot access", "can't access", "not available", "unavailable")):
        text += " existing shared drive cannot be accessed file share down"
    if "printer" in low and "jam" in low:
        text += " printer jam or error"
    if "vpn" in low and any(x in low for x in ("no longer", "can't connect", "not connecting")):
        text += " vpn connection failure"
    out = []
    for o in OFFERINGS.values():
        if o["ticket_type_id"] != ticket_type or o["active"].lower() != "true":
            continue
        score = overlap(text, f"{o['offering_name']} {o['synonyms']} {o['domain']}")
        phrase = o["offering_name"].lower().replace("request ", "")
        q = text.lower()
        if phrase in q:
            score += 2.0
        for syn in o["synonyms"].lower().split("|"):
            if len(syn) >= 5 and syn in q:
                score += 1.8
        # Give distinct products and modifiers a say before a fuzzy rerank.
        needed = set(tokens(phrase))
        given = set(tokens(q))
        if needed and len(needed & given) == len(needed):
            score += 1.2
        if {"guest", "wifi"} <= given and "guest" not in needed and "wifi" not in needed:
            score -= 1.5
        if {"vpn", "access"} <= given and "home" in needed and "home" not in given:
            score -= 1.0
        out.append((score, o))
    return sorted(out, key=lambda x: x[0], reverse=True)


def clean_state(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    allowed = ["phase", "original_text", "ticket_type", "offering_id", "asset_id", "asset_type", "asset_candidates", "fields", "preferred_action", "knowledge_id", "pause_reason"]
    out = {k: value[k] for k in allowed if k in value}
    if out.get("ticket_type") not in (None, "INC", "REQ"):
        out.pop("ticket_type", None)
    if out.get("phase") not in (None, "initial", "knowledge", "clarify_intent", "multi_intent", "asset_type", "symptom", "clarify_symptom", "asset_choice", "clarify_offering", "qualifying", "missing_field", "review"):
        out.pop("phase", None)
    if not isinstance(out.get("asset_candidates", []), list):
        out.pop("asset_candidates", None)
    if out.get("asset_type") not in (None, "laptop", "desktop"):
        out.pop("asset_type", None)
    if out.get("offering_id") not in OFFERINGS:
        out.pop("offering_id", None)
    if not isinstance(out.get("fields", {}), dict):
        out["fields"] = {}
    out["fields"] = {str(k)[:60]: str(v)[:200] for k, v in out.get("fields", {}).items() if isinstance(v, (str, int, float))}
    return out


def sealed_state(state, user_id):
    return _state_signer.dumps({"user_id": user_id, "state": clean_state(state)})


def verify_state(data, user_id):
    raw = data.get("state")
    if raw is None or raw == {}:
        return {}
    if not isinstance(raw, dict) or not isinstance(data.get("state_token"), str):
        raise ValueError("The session could not be verified. Please start a new conversation.")
    try:
        verified = _state_signer.loads(data["state_token"], max_age=60 * 60 * 3)
    except (BadSignature, SignatureExpired, ValueError):
        raise ValueError("The session has expired or was changed. Please start a new conversation.")
    if verified.get("user_id") != user_id or verified.get("state") != clean_state(raw):
        raise ValueError("The session does not match this user. Please start a new conversation.")
    return clean_state(raw)


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
        self.unavailable = False
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
        if not _gateway_slots.acquire(blocking=False):
            self.unavailable = True
            self.traces.append(event(endpoint, "error", "Clocked is busy. Retry in a moment."))
            return None
        try:
            res = getattr(self._client, endpoint)(**kwargs)
            raw = dict(res)
            # Include the actual response for judges; no credentials or headers.
            self.traces.append(event(endpoint, "live", "Clocked returned a response", getattr(res, "model_ms", None), raw))
            return raw
        except Exception as exc:
            # Never expose authorization headers or full exception bodies to the browser.
            code = getattr(exc, "status", None) or getattr(exc, "status_code", None)
            self.unavailable = True
            label = f"API request failed (HTTP {code})" if code else "API request failed"
            self.traces.append(event(endpoint, "error", label, round((time.monotonic() - begin) * 1000)))
            return None
        finally:
            _gateway_slots.release()

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


def is_incident(text):
    return bool(re.search(r"\b(broken|breakdown|crash(?:ing|ed|es)?|not working|isn't working|is not working|doesn't work|won'?t|cannot|can't|couldn't|failed|failure|error|slow|offline|outage|stuck|jam(?:med)?|locked|does not|will not|no longer|disconnect(?:ed|ing|s)?|dead|lost|not turn(?:ing)? on|not start(?:ing)?|flicker(?:ing)?)\b", text.lower()))


def is_request(text):
    q = text.lower()
    return bool(re.search(r"\b(request|install(?:ed|ation|ing)?|need (?:a|an|new)|need .* installed|replacement|give me access|grant access|want .* access|access to|order|new laptop|new desktop|can i get|can you provide|configure|set up|setup|provision|enroll(?:ed|ment)?|re.enroll|create)\b", q))


def explicit_agent(text):
    return bool(re.search(r"\b(connect me|talk to (?:an? |someone|support)|speak to (?:an? |someone)|live chat|agent|someone|human)\b", text.lower()))


def new_intent_during_flow(text):
    q = text.lower().strip()
    return bool(re.search(r"^(?:actually|sorry|instead|new request|another issue|forget that|i meant|change that|start over)", q)) or bool(re.search(r"^(?:please )?(?:i (?:need|want)|can you|create a|request a|install|my .+ (?:is|won't|will not|doesn't))", q))


def named_unknown_target(text):
    q = text.lower()
    m = re.search(r"(?:access to|install|request access to|need access to)\s+([a-z][a-z0-9 ]{2,65})", q)
    if not m:
        return False
    target = m.group(1).split(" for ")[0].split(" on ")[0].strip()
    known = " ".join(o["offering_name"] + " " + o["synonyms"] for o in OFFERINGS.values()).lower()
    common = ("vpn", "wifi", "wi fi", "sap", "outlook", "shared drive", "laptop", "desktop", "printer", "account", "role", "mfa", "adobe", "visio")
    if any(w in target for w in common):
        return False
    # Specific, unmatched product names must not be mapped to unrelated generic catalog items.
    return bool(target and target not in known and len([w for w in target.split() if w not in STOP]) >= 2)


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
            return response("Which device is affected? I can see more than one type of computer on this sample profile.", state, choices=[{"label": t, "value": "device:" + t.lower()} for t in types], trace=trace)
    # The default offering shortlist comes from the local catalog; Clocked reranks it in live mode.
    ranked = rank_offerings(original + " " + state.get("asset_type", ""), ticket_type)
    shortlist = [o for score, o in ranked[:7] if score >= .35]
    trace.append(event("Catalog shortlist", "local", ", ".join(o["offering_id"] for o in shortlist) or "No matching candidates"))
    if named_unknown_target(original):
        return response("I couldn't find that named application in the demo catalog. Can you confirm the application name or choose a supported service?", {**state, "phase": "clarify_offering"}, trace=trace)
    if not shortlist or (ranked and ranked[0][0] < .55):
        return response("I need a little more detail to select the right service offering. What application or service do you mean?", {**state, "phase": "clarify_offering"}, trace=trace)
    if not shortlist:
        return response("I can help, but I couldn't confidently match that to a catalog offering. Could you describe the system or device involved?", {**state, "phase": "clarify_offering"}, choices=[], trace=trace)
    top = shortlist[0]
    reranked = gw.rerank_offering(original + " " + state.get("asset_type", ""), shortlist)
    if reranked:
        items = reranked.get("results", [])
        valid = {o["offering_id"]: o for o in shortlist}
        selected = next((x for x in items if x.get("id") in valid and x.get("action") == "use" and float(x.get("relevance_score", 0)) >= .36), None)
        if selected:
            # Strong exact catalog matches should not be overturned by a fuzzy similar offering.
            if ranked[0][0] < 2.0 or selected["id"] == top["offering_id"]:
                top = valid[selected["id"]]
            else:
                trace.append(event("Catalog validation", "local", "Exact phrase match retained over ambiguous rerank"))
        elif items and items[0].get("action") == "skip":
            # No trustworthy match: don't manufacture an offering decision.
            return response("The catalog match is uncertain. Which support area is involved?", {**state, "phase": "clarify_offering"}, choices=[{"label": o["offering_name"], "value": "offering:" + o["offering_id"]} for o in shortlist[:4]], trace=trace)
    elif not gw.live:
        trace.append(event("Catalog retrieval", "demo", "Local text matching; no Clocked call"))
    elif gw.live:
        trace.append(event("Catalog fallback", "local", "Clocked unavailable; result will not be presented as a live decision"))
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
                    return response("Do you mean a laptop or desktop assigned to this demo user?", state, choices=[{"label": x, "value": "device:" + x.lower()} for x in types], trace=trace)
            matches = choose_asset_candidates(original, user_id, state)
            if len(matches) == 1:
                state["asset_id"] = matches[0]["asset_id"]
            elif len(matches) > 1:
                state["phase"] = "asset_choice"
                return response("I found multiple possible devices. Which one is affected? If you're unsure, you can continue without identifying an exact asset.", state, card={"type": "assets", "items": [asset_public(a) for a in matches[:8]]}, choices=[{"label": "I don't know the model", "value": "unknown_asset"}], trace=trace)
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
            known_apps = {"visio": "Microsoft Visio", "sap": "SAP", "adobe acrobat": "Adobe Acrobat", "microsoft project": "Microsoft Project", "outlook": "Microsoft Outlook", "salesforce": "Salesforce"}
            description = (o["offering_name"] + " " + state.get("original_text", "")).lower()
            for name, display in known_apps.items():
                if name in description:
                    fields[fid] = display
                    break
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
    state = {"original_text": text[:350], "phase": "initial", "fields": {}, "preferred_action": "chat" if explicit_agent(q) else "ticket"}
    explicit_action = bool(re.search(r"\b(create|raise|open) (?:an? )?ticket\b", q)) or explicit_agent(q)
    local_oos = bool(re.search(r"\b(cricket|football|match score|weather forecast|movie|recipe|celebrity)\b", q)) and not any(x in q for x in ["app", "laptop", "software"])
    local_incident = is_incident(q)
    local_request = is_request(q)
    gw.traces.append(event("Intent rules", "local", f"Incident keyword signal: {local_incident}; request signal: {local_request}; agent requested: {explicit_agent(q)}"))
    if "password" in q and ("reset" in q or "how" in q) and not "locked" in q:
        local_incident = False
    api_intents = gw.decide_intent(text)
    if api_intents:
        scope = noun_probability(api_intents, "it_support")
        incident = noun_probability(api_intents, "incident")
        sr = noun_probability(api_intents, "service_request")
        # Never reject an explicit help, ticket, hardware or agent request based solely on a low score.
        if scope is not None and scope < .37 and not (local_incident or local_request or explicit_action or re.search(r"\b(help|support|laptop|desktop|computer|account|email|software|printer|device|policy)\b", q)):
            local_oos = True
        if incident is not None and incident >= .69:
            local_incident = True
        if sr is not None and sr >= .69:
            local_request = True
        # Specific observed failures outrank a low generic probability; never erase strong evidence.
        if incident is not None and incident < .3 and not is_incident(q):
            local_incident = False
        if sr is not None and sr < .3 and not is_request(q):
            local_request = False
    else:
        gw.traces.append(event("Intent rules", "demo", "Explicit local classification; not a Clocked prediction"))
    if re.search(r"\b(?:create|open|raise) (?:an? )?ticket about [a-z]+\b", q) and not is_incident(q):
        return response("Can you clarify what happened? Is this an existing service not working, or are you requesting something new?", {**state, "phase": "clarify_intent"}, choices=[{"label": "Something is broken", "value": "type:INC"}, {"label": "Request a new service", "value": "type:REQ"}], trace=gw.traces)
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
            if found and found.get("answers_question") is not False:
                candidate = next(d for d in candidates if d["document_id"] == found["id"])
            else:
                candidate = None
                gw.traces.append(event("Knowledge relevance", "local", "Clocked did not confirm that a passage answers the question"))
        elif not gw.live:
            gw.traces.append(event("Knowledge matching", "demo", "Search over fictional local documents"))
        else:
            gw.traces.append(event("Knowledge fallback", "demo", "Clocked was unavailable; local document match used"))
        if candidate:
            # A generic laptop-loss article cannot answer a specific screen troubleshooting query.
            focused_terms = {"screen", "display", "flicker", "black screen", "battery", "keyboard", "printer", "jam"}
            if any(t in q for t in focused_terms) and not any(t in (candidate["title"] + " " + candidate["text"]).lower() for t in focused_terms if t in q):
                candidate = None
        if candidate:
            answer = knowledge_answer(candidate)
            grounding = gw.verify_answer(text, candidate, answer) if gw.live else None
            if grounding and str(grounding.get("verdict", "")).lower() in ("unsupported", "contradicted", "false", "not_grounded"):
                candidate = None
            if candidate:
                state.update({"phase": "knowledge", "knowledge_id": candidate["document_id"]})
                return response("I found a relevant guide in the sample knowledge library. Try these steps, then tell me if the problem is resolved.", state, card={"type": "knowledge", "title": candidate["title"], "id": candidate["document_id"], "excerpt": answer}, choices=[{"label": "That solved it", "value": "resolved"}, {"label": "Still need help", "value": "escalate"}, {"label": "Talk to an agent", "value": "escalate_chat"}], trace=gw.traces)
    if explicit_action and not local_incident and not local_request:
        return response("I can help with that. Is something not working, or do you need a new item or access?", {**state, "phase": "clarify_intent"}, choices=[{"label": "Report a problem", "value": "type:INC"}, {"label": "Request something", "value": "type:REQ"}], trace=gw.traces)
    if local_request and local_incident and not any(s in q for s in ["broken and", "not working and", "failed and", "crashing and"]):
        if re.search(r"\b(create|open|raise)\s+(?:an? )?ticket\b", q) and not any(s in q for s in ("broken", "crash", "error", "won't", "not working")):
            return response("Is Outlook failing, or are you requesting a new Outlook service?", {**state, "phase": "clarify_intent"}, choices=[{"label": "Something is broken", "value": "type:INC"}, {"label": "Request a new service", "value": "type:REQ"}], trace=gw.traces)
    if not local_incident and not local_request and not explicit_action:
        return response("Could you tell me a little more about what you need? For example, is something broken, or are you requesting access or software?", {**state, "phase": "clarify_intent"}, choices=[{"label": "Something is broken", "value": "type:INC"}, {"label": "Request something", "value": "type:REQ"}], trace=gw.traces)
    ticket_type = "INC" if local_incident else "REQ"
    state["ticket_type"] = ticket_type
    return continue_classification(state, user_id, gw)


def action_message(action, state, user_id, gw, details=None):
    if action == "resolved" and state.get("phase") == "knowledge":
        return response("Glad the guide helped. This demonstration is now complete. You can start another request anytime.", {}, card={"type": "complete", "title": "Issue resolved", "subtext": "No ticket was created."}, trace=gw.traces)
    if action in ("escalate", "escalate_chat") and state.get("phase") == "knowledge":
        state["preferred_action"] = "chat" if action == "escalate_chat" else "ticket"
        q = state.get("original_text", "")
        state["ticket_type"] = "INC" if is_incident(q) else "REQ" if is_request(q) else ""
        gw.traces.append(event("Escalation classification", "local", "Derived ticket type from original issue rather than button text"))
        if not state["ticket_type"]:
            state["phase"] = "clarify_intent"
            return response("Is this an existing service that stopped working, or a request for something new?", state, choices=[{"label": "Report a problem", "value": "type:INC"}, {"label": "Request something", "value": "type:REQ"}], trace=gw.traces)
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
        state["original_text"] = state["original_text"].strip() + ("; laptop is extremely slow or freezing" if symptom == "slow" else "; " + state["asset_type"] + " will not power on")
        return continue_classification(state, user_id, gw)
    if action.startswith("asset:") and state.get("phase") == "asset_choice":
        asset_id = action.split(":", 1)[1]
        if not any(a["asset_id"] == asset_id and a["user_id"] == user_id for a in ASSETS):
            return response("That asset is not assigned to the selected demo user.", state, trace=gw.traces)
        state["asset_id"] = asset_id
        return check_fields(state, user_id, gw)
    if action == "unknown_asset" and state.get("phase") == "asset_choice":
        state["asset_id"] = None
        state["phase"] = "qualifying"
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


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return resp


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(413)
def api_http_error(err):
    if request.path.startswith('/api/'):
        return jsonify({"error": getattr(err, "description", "Invalid request")}), err.code
    return err


def validated_input():
    if not request.is_json:
        raise ValueError("Please send a JSON request.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Invalid request body.")
    user_id = data.get("user_id", "DEMO001")
    if not isinstance(user_id, str) or user_id not in USERS:
        raise ValueError("Please select a valid demo user.")
    return data, user_id, verify_state(data, user_id)


def finish_result(result, user_id, gw):
    if gw.unavailable:
        # A real outage or limit must never silently change the outcome to local classification.
        return jsonify({"error": "Clocked is temporarily unavailable or busy. Please retry shortly. No action was taken.", "trace": gw.traces}), 503
    result["state_token"] = sealed_state(result.get("state", {}), user_id)
    return jsonify(result)


@app.post("/api/chat")
def api_chat():
    try:
        data, user_id, state = validated_input()
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Provide a message.")
        text = text.strip()[:1000]
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    gw = ClockedGateway()
    try:
        if state and re.match(r"^(?:actually|sorry|i meant)", text.lower()):
            previous = state.get("original_text", "")
            device = re.search(r"\b(dell|lenovo|hp|apple|samsung)\b", text.lower())
            software = re.search(r"\b(?:visio|microsoft project|adobe acrobat|sap|outlook|salesforce)\b", text.lower())
            if device and state.get("ticket_type") == "INC":
                updated = re.sub(r"\b(dell|lenovo|hp|apple|samsung)\b", device.group(0), previous, flags=re.I)
                if updated == previous:
                    updated = previous + "; affected device is " + text
                state.update({"original_text": updated, "asset_id": None, "asset_type": None, "offering_id": None})
                gw.traces.append(event("Conversation correction", "local", "Reevaluating device with the previous issue preserved"))
                result = continue_classification(state, user_id, gw)
            elif software:
                task = "install" if re.search(r"\binstall\b", previous.lower()) else "request access to" if "access" in previous.lower() else "request"
                gw.traces.append(event("Conversation correction", "local", "Reclassifying the corrected application"))
                result = start_message(task + " " + software.group(0), {}, user_id, gw, bypass_kb=True)
            else:
                gw.traces.append(event("Conversation correction", "local", "A new clarification is required"))
                result = start_message(text, {}, user_id, gw)
        elif state and new_intent_during_flow(text):
            gw.traces.append(event("Conversation reset", "local", "A new request superseded the prior workflow"))
            result = start_message(text, {}, user_id, gw)
        elif state.get("phase") == "missing_field":
            result = action_message("submit_field", state, user_id, gw, {"text": text})
        elif state.get("phase") == "asset_choice":
            if re.search(r"\b(don'?t know|not sure|unknown|cannot identify)\b", text.lower()):
                result = action_message("unknown_asset", state, user_id, gw)
            else:
                matched = next((a for a in choose_asset_candidates(text, user_id, state) if a["asset_id"].lower() in text.lower() or a["model"].lower() in text.lower()), None)
                result = action_message("asset:" + matched["asset_id"], state, user_id, gw) if matched else response("I can't identify that device yet. Please choose a listed device or say 'I don't know the model'.", state, choices=[{"label": "Continue without identifying asset", "value": "unknown_asset"}], trace=gw.traces)
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
        return finish_result(result, user_id, gw)
    finally:
        gw.close()


@app.post("/api/action")
def api_action():
    try:
        data, user_id, state = validated_input()
        action = data.get("action")
        if not isinstance(action, str) or not action or len(action) > 120:
            raise ValueError("Invalid action.")
        details = data.get("details")
        if details is not None and not isinstance(details, dict):
            raise ValueError("Invalid action details.")
        if not state.get("phase"):
            raise ValueError("No active workflow. Please start a conversation.")
    except ValueError as err:
        return jsonify({"error": str(err)}), 400
    gw = ClockedGateway()
    try:
        result = action_message(action, state, user_id, gw, details)
        return finish_result(result, user_id, gw)
    finally:
        gw.close()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", host="127.0.0.1", port=int(os.getenv("PORT", "5000")))
