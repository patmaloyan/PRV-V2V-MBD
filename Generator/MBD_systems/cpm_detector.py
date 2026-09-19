"""CPM reciprocity detectors used by ``main.py`` types 4 and 6."""

from dataclasses import dataclass
import math
from pathlib import Path

import numpy as np
import pandas as pd

from kalman_detector import (
    CPM_SENSOR_RANGE_M,
    CamCpmKalmanDetector,
    association_prediction_is_fresh,
    combined_message_frame,
    cpm_object_message,
    decision,
    empty_object_counts,
    load_json_list,
    parse_position,
    nis_within_threshold,
    receiver_just_entered,
    sender_just_entered,
    sender_pair_key,
)


EDGE_GRACE_NS = 2_000_000_000
EDGE_TTL_NS = 6_000_000_000
REQUIRED_UNRECIPROCATED_EDGES = 2
INTERVAL_NS = 1_000_000_000
PRV_BOTH_DIRECTIONS_COEFFICIENT = 2.0
PRV_OUTBOUND_ONLY_COEFFICIENT = -1.0
TRUST_ALPHA = 1.0 / 3.0
RECIPROCITY_NIS_THRESHOLD = 18.47


def valid_alias(value):
    try:
        alias = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return alias if alias != 0 else None


class TwoEdgeReciprocityDetector(CamCpmKalmanDetector):
    """Type 4: reject sources with two stale, unreciprocated CPM edges."""

    def __init__(self, catch_params=None, catch_enabled=True):
        super().__init__(catch_params, catch_enabled)
        self.edges = {}
        self.last_unreciprocated_targets = []

    def perceived_object_matches(self, measurement):
        matches = []
        for track in self.tracks:
            if not association_prediction_is_fresh(
                track, int(measurement["rcvTime"])
            ):
                continue
            deviation = track.deviation_against_cam(
                measurement, self.cpm_association_noise
            )
            if nis_within_threshold(deviation.nis):
                matches.append((track, deviation))
        return matches

    def prune_edges(self, now):
        for source in list(self.edges):
            for target in list(self.edges[source]):
                timestamps = [
                    timestamp
                    for timestamp in self.edges[source][target]
                    if now - timestamp <= EDGE_TTL_NS
                ]
                if timestamps:
                    self.edges[source][target] = timestamps
                else:
                    del self.edges[source][target]
            if not self.edges[source]:
                del self.edges[source]

    def add_edge(self, source, target, timestamp):
        source = valid_alias(source)
        target = valid_alias(target)
        if source is None or target is None or source == target:
            return False
        self.edges.setdefault(source, {}).setdefault(target, []).append(int(timestamp))
        return True

    def unreciprocated_targets(self, source, now):
        source = valid_alias(source)
        if source is None:
            return []
        return sorted(
            target
            for target, timestamps in self.edges.get(source, {}).items()
            if now - timestamps[0] >= EDGE_GRACE_NS
            and source not in self.edges.get(target, {})
        )

    def pre_source_decision(self, message):
        now = int(message["rcvTime"])
        self.prune_edges(now)
        self.last_unreciprocated_targets = self.unreciprocated_targets(
            message.get("sender_alias"), now
        )
        if len(self.last_unreciprocated_targets) >= REQUIRED_UNRECIPROCATED_EDGES:
            return decision(False, "reciprocity_reject", None, None, None)
        return None

    def on_perceived_object_match(
        self, cpm, matched_track, deviation=None, perceived_object=None
    ):
        if (
            self.tracks_by_station_alias.get(matched_track.station_alias)
            is not matched_track
        ):
            return {"edge_added": False}
        edge_added = self.add_edge(
            cpm.get("sender_alias"), matched_track.station_alias, cpm["rcvTime"]
        )
        return {"edge_added": edge_added}

    def edge_count(self):
        return sum(len(targets) for targets in self.edges.values())

    def message_debug(self):
        return {
            "edge_count": self.edge_count(),
            "unreciprocated_targets": self.last_unreciprocated_targets,
            "required_unreciprocated_edges": REQUIRED_UNRECIPROCATED_EDGES,
        }


@dataclass
class EdgeEvidence:
    nis: float
    distance: float
    confidence: float
    opportunity: float
    weight: float


@dataclass
class PrvTrust:
    accepted: bool = True
    score: float = 0.0
    evidence_updates: int = 0


def nis_confidence(nis):
    return 1.0 - float(nis) / RECIPROCITY_NIS_THRESHOLD


def distance_opportunity(distance):
    return max(0.0, min(1.0, 1.0 - float(distance) / CPM_SENSOR_RANGE_M))


def edge_evidence(nis, distance):
    confidence = nis_confidence(nis)
    opportunity = distance_opportunity(distance)
    return EdgeEvidence(
        nis=float(nis),
        distance=float(distance),
        confidence=confidence,
        opportunity=opportunity,
        weight=confidence * opportunity,
    )


def prv_pair_score(b_to_a, a_to_b):
    """Score assessed A against counterpart B as mutual/A→B/B→A/absent."""
    if b_to_a is not None and a_to_b is not None:
        return PRV_BOTH_DIRECTIONS_COEFFICIENT * math.sqrt(
            b_to_a.weight * a_to_b.weight
        )
    if b_to_a is not None:
        return 0.0
    if a_to_b is not None:
        return PRV_OUTBOUND_ONLY_COEFFICIENT * a_to_b.weight
    return 0.0


class _PrvDetectorBase(CamCpmKalmanDetector):
    def __init__(self, catch_params=None, catch_enabled=True):
        super().__init__(catch_params, catch_enabled)
        self.current_bucket = None
        self.bucket_edges = {}
        self.track_ids = {}
        self.next_track_id = 1
        self.trust = {}
        self.last_closed_intervals = []
        self.current_source_track_id = None

    def perceived_object_matches(self, measurement):
        best_track, deviation = self.closest_track(measurement)
        if (
            best_track is not None
            and deviation.nis <= self.perceived_object_nis_threshold()
        ):
            return [(best_track, deviation)]
        return []

    def perceived_object_nis_threshold(self):
        return RECIPROCITY_NIS_THRESHOLD

    def advance_to(self, receive_time):
        bucket = int(receive_time) // INTERVAL_NS
        self.last_closed_intervals = []
        if self.current_bucket is None:
            self.current_bucket = bucket
            return
        while self.current_bucket < bucket:
            self.last_closed_intervals.append(self.close_current_bucket())
            self.current_bucket += 1
            self.bucket_edges = {}

    def process_receiver(
        self, cam_path: Path | None, cpm_path: Path | None,
        ego_path: Path | None,
    ):
        messages = self.catch_messages(
            combined_message_frame(cam_path, cpm_path)
        )
        ego_snapshots = sorted(
            load_json_list(ego_path), key=lambda msg: int(msg["sendTime"])
        )
        receiver_id = (cam_path or cpm_path).stem
        rows = []
        paired_source_decisions = {}

        for message in messages.to_dict(orient="records"):
            message_type = str(message["message_type"]).upper()
            pair_key = sender_pair_key(message)
            source_state = None
            self.current_source_track_id = None
            if message_type == "CPM":
                cached = paired_source_decisions.get(pair_key)
                self.advance_to(message.get("effectiveRcvTime", message["rcvTime"]))
                if cached is None:
                    base_decision = None
                    source_decision = decision(
                        False, "missing_paired_cam", None, None, None
                    )
                else:
                    source_decision = dict(cached["source_decision"])
                    base_decision = cached["base_decision"]
                    self.current_source_track_id = cached["source_track_id"]
                    source_state = self.trust.get(self.current_source_track_id)
            else:
                catch_prediction = int(message["catch_prediction"])
                if catch_prediction:
                    base_decision = None
                    source_decision = self.catch_rejection()
                else:
                    self.advance_to(message["rcvTime"])
                    base_decision = self.process_cam(
                        message, ego_snapshots, commit=False
                    )
                    source_track = self.tracks_by_station_alias.get(
                        int(message.get("sender_alias", 0))
                    )
                    if (
                        source_track is None
                        and base_decision["reason"] == "pseudonym_accept"
                    ):
                        source_track = self.tracks_by_station_alias.get(
                            int(base_decision["matched_id"])
                        )
                    if source_track is not None:
                        self.current_source_track_id = self.track_ids.get(
                            id(source_track)
                        )
                        source_state = self.trust.get(self.current_source_track_id)

                    source_decision = dict(base_decision)
                    if base_decision["accepted"]:
                        # PRV trust controls the external decision and whether
                        # this source's CPM may influence other tracks. It must
                        # not stop a CAM already accepted by the base Kalman
                        # detector from maintaining that source's own track.
                        source_decision = self.process_cam(
                            message, ego_snapshots, commit=True
                        )
                        source_track = self.tracks_by_station_alias.get(
                            int(message.get("sender_alias", 0))
                        )
                        if source_track is not None:
                            self.current_source_track_id = self.track_id(
                                source_track, create_trust=True
                            )
                            source_state = self.trust[self.current_source_track_id]
                    if base_decision["accepted"] and (
                        source_state is not None and not source_state.accepted
                    ):
                        source_decision.update(decision(
                            False, "prv_quarantine",
                            base_decision.get("pos_error"),
                            base_decision.get("speed_error"),
                            base_decision.get("matched_id"), base_decision.get("nis"),
                            base_decision.get("nis_threshold"),
                        ))
                paired_source_decisions[pair_key] = {
                    "source_decision": dict(source_decision),
                    "base_decision": dict(base_decision) if base_decision else None,
                    "source_track_id": self.current_source_track_id,
                }

            object_counts = empty_object_counts()
            if message_type == "CPM":
                if source_decision["accepted"]:
                    object_counts = self.process_perceived_objects(
                        cpm_object_message(message)
                    )
                elif source_state is not None and not source_state.accepted:
                    # A quarantined source still needs its own outbound edges
                    # to update its trust and permit recovery. Associate only
                    # against existing tracks: do not refresh, update, or
                    # initialize any track using an untrusted CPM.
                    object_counts = self.process_quarantined_perceived_objects(
                        cpm_object_message(message)
                    )
                else:
                    objects = message.get("perceivedObjects", [])
                    if isinstance(objects, list):
                        object_counts["cpm_objects_observed"] = len(objects)
                        object_counts["cpm_objects_source_rejected"] = len(objects)
                    else:
                        object_counts["cpm_objects_malformed"] = 1

            gate_fields = self.catch_debug(
                message, base_decision or source_decision
            )
            if message_type == "CPM":
                gate_fields["kalman_skipped"] = True
                gate_fields["kalman_prediction"] = None
            rows.append({
                "receiver_id": receiver_id,
                "message_type": message_type,
                "messageID": message.get("messageID"),
                "sender_id": message.get("sender_id"),
                "sender_alias": message.get("sender_alias", 0),
                "sender_just_entered_communication_zone": sender_just_entered(message),
                "receiver_just_entered_communication_zone": receiver_just_entered(message),
                "sendTime": int(message.get("sendTime", 0)),
                "rcvTime": int(message.get("rcvTime", 0)),
                "attacker": int(message.get("attacker", 0)),
                "prediction": 0 if source_decision["accepted"] else 1,
                **source_decision,
                **gate_fields,
                **object_counts,
                "reciprocity_bucket": self.current_bucket,
                "reciprocity_track_id": self.current_source_track_id,
                "reciprocity_state": (
                    "accepted" if source_state is None or source_state.accepted
                    else "quarantined"
                ),
                "reciprocity_score_history": (
                    self.score_history(source_state)
                    if source_state is not None else []
                ),
                "reciprocity_rolling_score": (
                    self.decision_score(source_state)
                    if source_state is not None else 0.0
                ),
                "reciprocity_evidence_updates": (
                    getattr(source_state, "evidence_updates", 0)
                    if source_state is not None else 0
                ),
                "closed_reciprocity_intervals": self.last_closed_intervals,
            })

        if self.current_bucket is not None:
            self.last_closed_intervals = [self.close_current_bucket()]
        return pd.DataFrame(rows)

    def process_quarantined_perceived_objects(self, cpm):
        return super().process_perceived_objects(
            cpm,
            refresh_matched_tracks=False,
            initialize_unmatched_tracks=False,
        )

    def on_perceived_object_match(
        self, cpm, matched_track, deviation=None, perceived_object=None
    ):
        if (
            self.current_source_track_id is None
            or perceived_object is None
            or deviation is None
        ):
            return {"edge_added": False}
        target_id = self.track_id(matched_track)
        if target_id == self.current_source_track_id:
            return {"edge_added": False}
        try:
            distance = float(np.linalg.norm(
                parse_position(perceived_object["rel_pos"])[0:2]
            ))
        except (KeyError, TypeError, ValueError, IndexError):
            return {"edge_added": False}
        evidence = edge_evidence(deviation.nis, distance)
        self.bucket_edges[(self.current_source_track_id, target_id)] = evidence
        return {
            "edge_added": True,
            "edge_weight": evidence.weight,
            "edge_confidence": evidence.confidence,
            "edge_opportunity": evidence.opportunity,
        }


class PrvDetector(_PrvDetectorBase):
    """Type 6 (PRV): EWMA trust over aggregate one-second reciprocity evidence."""

    def track_id(self, track, create_trust=False):
        key = id(track)
        if key not in self.track_ids:
            self.track_ids[key] = self.next_track_id
            self.next_track_id += 1
        track_id = self.track_ids[key]
        if create_trust:
            self.trust.setdefault(track_id, PrvTrust())
        return track_id

    def close_current_bucket(self):
        accepted_snapshot = {
            track_id: state.accepted for track_id, state in self.trust.items()
        }
        aggregate_scores = {track_id: None for track_id in self.trust}
        evidence_counts = {track_id: 0 for track_id in self.trust}

        # Reciprocity is a sparse directed graph. Build the small set of
        # counterparts that actually has an edge in this interval instead of
        # testing the Cartesian product of all trusted tracks. Sorting by trust
        # insertion order preserves the former floating-point summation order.
        trust_order = {
            track_id: index for index, track_id in enumerate(self.trust)
        }
        counterparts_by_subject = {}
        for source_id, target_id in self.bucket_edges:
            if (
                source_id == target_id
                or source_id not in self.trust
                or target_id not in self.trust
            ):
                continue
            counterparts_by_subject.setdefault(source_id, set()).add(target_id)
            counterparts_by_subject.setdefault(target_id, set()).add(source_id)

        for subject_id in self.trust:
            raw_score = 0.0
            evidence_count = 0
            counterparts = sorted(
                counterparts_by_subject.get(subject_id, ()),
                key=trust_order.__getitem__,
            )
            for counterpart_id in counterparts:
                if not accepted_snapshot[counterpart_id]:
                    continue
                # A is the assessed subject and B is this accepted counterpart.
                # B→A is inbound evidence; A→B is outbound evidence.
                b_to_a = self.bucket_edges.get((counterpart_id, subject_id))
                a_to_b = self.bucket_edges.get((subject_id, counterpart_id))
                if b_to_a is None and a_to_b is None:
                    continue
                raw_score += self.pair_score(b_to_a, a_to_b)
                evidence_count += 1

            evidence_counts[subject_id] = evidence_count
            aggregate_scores[subject_id] = raw_score if evidence_count else None

        transitions = []
        trust_scores = {}
        for track_id, aggregate_score in aggregate_scores.items():
            state = self.trust[track_id]
            was_accepted = state.accepted
            if aggregate_score is not None:
                state.score += TRUST_ALPHA * (aggregate_score - state.score)
                state.evidence_updates += 1
                state.accepted = state.score >= 0.0
            trust_scores[track_id] = state.score
            if state.accepted != was_accepted:
                transitions.append({
                    "track_id": track_id,
                    "state": "accepted" if state.accepted else "quarantined",
                })

        return {
            "bucket_id": self.current_bucket,
            "aggregate_scores": aggregate_scores,
            "evidence_counts": evidence_counts,
            "trust_scores": trust_scores,
            "trust_update_counts": {
                track_id: state.evidence_updates
                for track_id, state in self.trust.items()
            },
            "transitions": transitions,
        }

    def score_history(self, state):
        return []

    def decision_score(self, state):
        return state.score

    def pair_score(self, b_to_a, a_to_b):
        return prv_pair_score(b_to_a, a_to_b)
