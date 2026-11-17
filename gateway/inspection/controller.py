"""The sole owner of an operation's stage deadlines and bounded recovery."""
import asyncio
import json
from dataclasses import dataclass, field
from .wire import ProtocolError, Restarted, encode, uint


@dataclass(frozen=True)
class Policy:
    receipt_s: float = 1.0
    acceptance_s: float = 1.0
    completion_allowance_s: float = 2.0
    request_retries: int = 2
    queries: int = 2
    query_window_s: float = 1.0
    absolute_allowance_s: float = 10.0

    def __post_init__(self):
        for name in ("receipt_s", "acceptance_s", "completion_allowance_s",
                     "query_window_s", "absolute_allowance_s"):
            value = getattr(self, name)
            if type(value) not in (float, int) or not 0 < value < float("inf"):
                raise ValueError(f"{name} must be finite and positive")
        for value in (self.request_retries, self.queries):
            if type(value) is not int or not 0 <= value <= 16:
                raise ValueError("recovery attempt limits must be integers in 0..16")


@dataclass
class Evidence:
    received_observed_at: float | None = None
    accepted_observed_at: float | None = None
    completed_observed_at: float | None = None
    delivery_established_by: str | None = None
    acceptance_established_by: str | None = None
    request_attempts: int = 0
    query_attempts: int = 0
    queries: dict = field(default_factory=dict)


@dataclass
class Outcome:
    state: str
    identifier: str
    result: dict | None
    evidence: Evidence
    reason: str | None = None


class Controller:
    def __init__(self, link, ids, policy=None):
        self.link, self.ids = link, ids
        self.policy = policy or Policy()
        self.finished = {}
        self.link.late_handler = self._late

    @staticmethod
    def _signature(state, result, reason=None):
        return json.dumps(result if state == "COMPLETED" else {"error": reason},
                          sort_keys=True, separators=(",", ":"))

    def _late(self, message):
        identifier = message.get("job_id", message.get("cmd_id"))
        prior = self.finished.get(identifier)
        if not prior or message.get("type") not in {"COMPLETED", "REJECTED"}:
            return
        request, state, signature = prior
        if not self._identity(message, request):
            return
        result = message.get("result")
        incoming = self._signature(message["type"], result, message.get("error"))
        if message["type"] != state or incoming != signature:
            self.link.terminal_conflict = (identifier, "conflicting terminal response")
            self.link.log("conflicting_terminal", message)

    @staticmethod
    def _identity(message, request):
        key = "job_id" if request["type"] == "INSPECT" else "cmd_id"
        return (message.get(key) == request[key] and
                message.get("boot_id") == request["boot_id"] and
                message.get("action") == request["type"] and
                message.get("batch_id") == request["batch_id"] and
                type(message.get("run_no")) is int and message["run_no"] == request["run_no"] and
                (request["type"] != "INSPECT" or (
                    type(message.get("part_id")) is int and message["part_id"] == request["part_id"])))

    @staticmethod
    def _result(result, request, duration_ms, expected_settings=None, completion_allowance_ms=None):
        key = "job_id" if request["type"] == "INSPECT" else "cmd_id"
        if not isinstance(result, dict) or not Controller._identity(
                {**result, "boot_id": request["boot_id"]}, request):
            raise ProtocolError("completion result has mismatched operation/part/scope")
        if result.get("state") != "COMPLETED" or not uint(result.get("elapsed_ms"), 2**53 - 1):
            raise ProtocolError("invalid completion state/elapsed duration")
        settings = result.get("settings")
        if request["type"] in {"CONFIGURE", "INSPECT", "CLOSE"}:
            if (not uint(result.get("config_version"), minimum=1) or
                    not isinstance(settings, dict) or set(settings) != {"inspection_time_ms", "N", "K"} or
                    not uint(settings.get("inspection_time_ms"), 600000, 1) or
                    not uint(settings.get("N"), 2147483647, 1) or
                    type(settings.get("K")) is not int or
                    not -2147483648 <= settings["K"] <= 2147483647):
                raise ProtocolError("invalid applied settings/configuration version in result")
        if request["type"] == "INSPECT":
            if result.get("verdict") not in {"PASS", "FAIL"}:
                raise ProtocolError("missing B-calculated verdict")
            if result.get("config_version") != request["config_version"]:
                raise ProtocolError("inspection used a different configuration")
            if result["elapsed_ms"] < duration_ms:
                raise ProtocolError("inspection finished before its configured duration")
            if completion_allowance_ms is not None and result["elapsed_ms"] > duration_ms + completion_allowance_ms:
                raise ProtocolError("inspection exceeded its execution allowance")
            if expected_settings is not None and result.get("settings") != expected_settings:
                raise ProtocolError("inspection did not use the frozen applied settings")
        elif request["type"] == "CONFIGURE":
            settings = result.get("settings")
            if settings != {k: request[k] for k in ("inspection_time_ms", "N", "K")}:
                raise ProtocolError("B did not confirm the requested applied settings")
            if not uint(result.get("config_version"), minimum=1):
                raise ProtocolError("invalid applied configuration version")
        elif request["type"] == "CLOSE" and result.get("closed") is not True:
            raise ProtocolError("B did not confirm the run was closed")
        if result.get(key) != request[key]:
            raise ProtocolError("result changed original ID")
        return result

    async def run(self, request, *, duration_ms=0, expected_settings=None):
        # Snapshot once: every request retransmission uses exactly these bytes.
        request = dict(request)
        payload = encode(request)
        key = "job_id" if request["type"] == "INSPECT" else "cmd_id"
        identifier = request[key]
        policy, clock = self.policy, asyncio.get_running_loop().time
        started = clock()
        absolute = started + duration_ms / 1000 + policy.absolute_allowance_s
        received_at = accepted_at = None  # Local evidence anchors, not device ACK timestamps.
        completion_by = None
        evidence = Evidence()
        events = asyncio.Queue(maxsize=128)
        self.link.route(identifier, events)
        query_requests = {}
        next_action = started
        sent = False

        def validate_result(result):
            return self._result(result, request, duration_ms, expected_settings,
                                int(policy.completion_allowance_s * 1000))

        def establish(source, now, accepted=False):
            nonlocal received_at, accepted_at, completion_by
            if received_at is None:
                received_at = now
                evidence.delivery_established_by = source
            if accepted and accepted_at is None:
                accepted_at = now
                evidence.acceptance_established_by = source
                completion_by = min(absolute, now + duration_ms / 1000 + policy.completion_allowance_s)

        async def transmit(message, wire, window):
            nonlocal next_action
            now = clock()
            next_action = min(absolute, now + window)
            try:
                await asyncio.wait_for(self.link.send(message, wire), max(0.001, min(window, absolute-now)))
            except (OSError, asyncio.TimeoutError, ProtocolError):
                # The attempt is still counted. No adapter-level retry exists.
                if isinstance(self.link.failure, Restarted):
                    raise self.link.failure

        def unresolved(reason):
            return Outcome("UNRESOLVED", identifier, None, evidence, reason)

        def finish(outcome):
            # Only current-run original commands/jobs need late-result
            # comparison; read-only query snapshots have their own IDs/cache.
            if request["type"] != "QUERY":
                signature = self._signature(outcome.state, outcome.result, outcome.reason)
                prior = self.finished.get(identifier)
                if prior and (prior[1], prior[2]) != (outcome.state, signature):
                    self.link.terminal_conflict = (identifier, "conflicting terminal response")
                    return unresolved("conflicting terminal response; original outcome retained")
                self.finished[identifier] = (
                    request, outcome.state, signature)
            return outcome

        try:
            while True:
                now = clock()
                if now >= absolute:
                    return unresolved("absolute operation limit exhausted")
                if isinstance(self.link.failure, Restarted):
                    return unresolved(str(self.link.failure))
                if now >= next_action:
                    if not sent or (accepted_at is None and
                                    evidence.request_attempts < 1 + policy.request_retries):
                        sent = True
                        evidence.request_attempts += 1
                        window = policy.acceptance_s if received_at is not None else policy.receipt_s
                        await transmit(request, payload, window)
                    elif accepted_at is not None and completion_by is not None and now < completion_by:
                        next_action = completion_by
                    elif request["type"] == "QUERY":
                        # A read query never recursively creates recovery queries.
                        return unresolved("query response limit exhausted")
                    elif evidence.query_attempts < policy.queries:
                        query = {
                            "v": 1, "type": "QUERY", "cmd_id": self.ids.new("QUERY"),
                            "boot_id": request["boot_id"], "batch_id": request["batch_id"],
                            "run_no": request["run_no"], "target_id": identifier,
                            "query_no": self.link.next_query_no(),
                        }
                        query_id = query["cmd_id"]
                        self.link.route(query_id, events)
                        query_requests[query_id] = query
                        evidence.queries[query_id] = {"received_observed_at": None,
                                                     "accepted_observed_at": None,
                                                     "completed_observed_at": None}
                        evidence.query_attempts += 1
                        await transmit(query, encode(query), policy.query_window_s)
                    else:
                        return unresolved("bounded recovery attempts exhausted")
                timeout = max(0.001, min(next_action, absolute) - clock())
                try:
                    message = await asyncio.wait_for(events.get(), timeout)
                except asyncio.TimeoutError:
                    continue
                now = clock()
                if now >= absolute:
                    return unresolved("response arrived after absolute limit")
                if message.get("_event") == "disconnected":
                    if isinstance(message.get("error"), Restarted):
                        return unresolved(str(message["error"]))
                    continue
                query = query_requests.get(message.get("cmd_id"))
                if query:
                    if not self._identity(message, query):
                        continue
                    stage = message.get("type")
                    q_evidence = evidence.queries[query["cmd_id"]]
                    observed = {"RECEIVED": "received_observed_at", "ACCEPTED": "accepted_observed_at",
                                "COMPLETED": "completed_observed_at"}.get(stage)
                    if observed and q_evidence[observed] is None:
                        q_evidence[observed] = now
                    if stage != "COMPLETED":
                        continue
                    if (message.get("target_id") != identifier or
                            message.get("query_no") != query["query_no"]):
                        continue
                    target = message.get("target")
                    if target is None:
                        if accepted_at is not None or received_at is not None:
                            return unresolved("B lost a queryable operation record")
                        continue
                    if not isinstance(target, dict):
                        continue
                    translated = {**target, "boot_id": request["boot_id"],
                                  "type": "STATUS", "action": target.get("action")}
                    if not self._identity(translated, request):
                        continue
                    state = target.get("state")
                    if state == "COMPLETED":
                        result = validate_result(target)
                        establish("QUERY_COMPLETED", now, True)
                        # This is observed query evidence, never a fabricated target ACK.
                        return finish(Outcome("COMPLETED", identifier, result, evidence))
                    if state == "REJECTED":
                        if accepted_at is not None:
                            return unresolved("rejection conflicts with accepted evidence")
                        establish("QUERY_REJECTED", now)
                        return finish(Outcome("REJECTED", identifier, target, evidence, target.get("error")))
                    if state == "IN_PROGRESS":
                        establish("QUERY_IN_PROGRESS", now, True)
                        next_action = max(next_action, completion_by)
                    elif state == "RECEIVED":
                        establish("QUERY_PENDING_VALIDATION", now)
                    continue
                if not self._identity(message, request):
                    continue
                stage = message.get("type")
                if stage == "ERROR":
                    return unresolved("B protocol/admission error: " + str(message.get("error")))
                if stage == "RECEIVED":
                    first_receipt = received_at is None
                    if evidence.received_observed_at is None:
                        evidence.received_observed_at = now
                    establish("RECEIVED", now)
                    if accepted_at is None and first_receipt:
                        next_action = min(absolute, received_at + policy.acceptance_s)
                elif stage == "ACCEPTED":
                    first_acceptance = accepted_at is None
                    if evidence.accepted_observed_at is None:
                        evidence.accepted_observed_at = now
                    establish("ACCEPTED", now, True)
                    if first_acceptance:
                        next_action = completion_by
                elif stage == "STATUS":
                    if message.get("state") == "IN_PROGRESS":
                        first_acceptance = accepted_at is None
                        establish("DUPLICATE_IN_PROGRESS", now, True)
                        if first_acceptance:
                            next_action = completion_by
                    elif message.get("state") == "PENDING_VALIDATION":
                        establish("DUPLICATE_PENDING_VALIDATION", now)
                elif stage == "REJECTED":
                    if accepted_at is not None:
                        return unresolved("rejection conflicts with accepted evidence")
                    establish("REJECTED", now)
                    return finish(Outcome("REJECTED", identifier, message, evidence, message.get("error")))
                elif stage == "COMPLETED":
                    if request["type"] == "QUERY":
                        if (message.get("target_id") != request["target_id"] or
                                message.get("query_no") != request["query_no"]):
                            continue
                        result = message
                    else:
                        result = validate_result(message.get("result"))
                    establish("COMPLETED", now, True)
                    evidence.completed_observed_at = now
                    return finish(Outcome("COMPLETED", identifier, result, evidence))
        except (ProtocolError, Restarted) as exc:
            return unresolved(str(exc))
        finally:
            self.link.unroute(identifier)
            for query_id in query_requests:
                self.link.unroute(query_id)
            while not events.empty():
                self._late(events.get_nowait())
