import json
import math
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from .event_logic import direction_from_raw_event, label_from_raw_event


MODEL_RDS_PATH = os.getenv("MODEL_RDS_PATH", "./attendance_anomaly_model.rds")

def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}

@dataclass
class PredictResult:
    label: str
    confidence: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None

class RDSModel:
    def __init__(self, rds_path: str):
        self.rds_path = rds_path
        self.enabled = False
        self._model = None
        self._robjects = None
        self._params: Dict[str, Any] = {}

        try:
            from rpy2 import robjects
            from rpy2.robjects.packages import importr

            base = importr("base")
            obj = base.readRDS(rds_path)

            # ✅ set robjects dulu baru unwrap
            self._robjects = robjects
            self._model = self._unwrap_if_list(obj)
            self._params = self._extract_params(self._model)

            self.enabled = True
            print(f"[RDS] Loaded model from {rds_path}")
        except Exception as e:
            self.enabled = False
            import traceback
            print(f"[RDS] Disabled (failed to load): {e}")
            traceback.print_exc()

    def predict(self, features: Dict[str, Any]) -> PredictResult:
        """
        RDS ini adalah list parameter scoring:
        - weights
        - threshold_95 / threshold_99
        - baseline_person / baseline_person_day
        Jadi kita TIDAK pakai R predict().
        """
        if not self.enabled or self._model is None:
            return self._fallback(features)

        try:
            score_info = self.score(features)
            score = score_info["score"]
            thr95 = score_info["threshold_95"]
            thr99 = score_info["threshold_99"]

            raw_event = str(features.get("raw_event", ""))

            # arah event (keluar vs masuk)
            direction = direction_from_raw_event(raw_event)

            if score is None:
                label = self._fallback_label(raw_event)
                conf = 0.0
                debug_payload = {
                    "score": score,
                    "score_reason": score_info.get("score_reason"),
                    "missing_features": score_info.get("missing_features"),
                    "partial_score": score_info.get("partial_score"),
                    "threshold_95": thr95,
                    "threshold_99": thr99,
                    "hour": int(features.get("hour", 0)),
                    "dow": int(features.get("dow", 1)),
                    "baseline_day": score_info.get("baseline_day"),
                    "baseline_person": score_info.get("baseline_person"),
                    "feature_debug": score_info.get("feature_debug"),
                    "features": score_info.get("features"),
                    "raw_features": score_info.get("raw_features"),
                    "who": None,
                    "direction": direction,
                    "label": label,
                    "confidence": conf,
                }
                self._debug_log(debug_payload)
                return PredictResult(label=label, confidence=conf, raw=debug_payload)

            # klasifikasi "ANDA" vs "ORANG" berdasarkan score
            # jika score >= thr99 → anomali kuat → ORANG
            # jika score >= thr95 → anomali sedang → ORANG (tapi confidence lebih rendah)
            if score >= thr95:
                who = "ORANG"
            else:
                who = "ANDA"

            conf = self._compute_confidence(score, thr95, thr99)

            if direction == "OUT":
                label = "ANDA_PERGI" if who == "ANDA" else "ORANG_KELUAR"
            elif direction == "IN":
                label = "ANDA_PULANG" if who == "ANDA" else "ORANG_MASUK"
            else:
                label = "UNKNOWN"

            debug_payload = {
                "score": score,
                "score_reason": score_info.get("score_reason"),
                "missing_features": score_info.get("missing_features"),
                "partial_score": score_info.get("partial_score"),
                "threshold_95": thr95,
                "threshold_99": thr99,
                "hour": int(features.get("hour", 0)),
                "dow": int(features.get("dow", 1)),
                "baseline_day": score_info.get("baseline_day"),
                "baseline_person": score_info.get("baseline_person"),
                "feature_debug": score_info.get("feature_debug"),
                "features": score_info.get("features"),
                "raw_features": score_info.get("raw_features"),
                "who": who,
                "direction": direction,
                "label": label,
                "confidence": conf,
            }

            self._debug_log(debug_payload)
            return PredictResult(label=label, confidence=conf, raw=debug_payload)
        except Exception as e:
            print(f"[RDS] scoring predict failed: {e}")
            return self._fallback(features)

    def debug_score(self, features: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled or self._model is None:
            return {"enabled": False, "error": "model disabled", "features": features}

        score_info = self.score(features)
        score = score_info["score"]
        thr95 = score_info["threshold_95"]
        thr99 = score_info["threshold_99"]

        raw_event = str(features.get("raw_event", ""))
        direction = direction_from_raw_event(raw_event)
        if score is None:
            label = self._fallback_label(raw_event)
            return {
                "enabled": True,
                "features": score_info.get("features"),
                "extracted_features": score_info.get("features"),
                "anomaly_score": None,
                "score_reason": score_info.get("score_reason"),
                "missing_features": score_info.get("missing_features"),
                "partial_score": score_info.get("partial_score"),
                "thresholds": {"threshold_95": thr95, "threshold_99": thr99},
                "who": None,
                "direction": direction,
                "label": label,
                "confidence": 0.0,
                "baseline_day": score_info.get("baseline_day"),
                "baseline_person": score_info.get("baseline_person"),
                "feature_debug": score_info.get("feature_debug"),
                "raw_features": score_info.get("raw_features"),
            }

        who = "ORANG" if score >= thr95 else "ANDA"
        if direction == "OUT":
            label = "ANDA_PERGI" if who == "ANDA" else "ORANG_KELUAR"
        elif direction == "IN":
            label = "ANDA_PULANG" if who == "ANDA" else "ORANG_MASUK"
        else:
            label = "UNKNOWN"

        confidence = self._compute_confidence(score, thr95, thr99)

        return {
            "enabled": True,
            "features": score_info.get("features"),
            "extracted_features": score_info.get("features"),
            "anomaly_score": score,
            "score_reason": score_info.get("score_reason"),
            "missing_features": score_info.get("missing_features"),
            "partial_score": score_info.get("partial_score"),
            "thresholds": {"threshold_95": thr95, "threshold_99": thr99},
            "who": who,
            "direction": direction,
            "label": label,
            "confidence": confidence,
            "baseline_day": score_info.get("baseline_day"),
            "baseline_person": score_info.get("baseline_person"),
            "feature_debug": score_info.get("feature_debug"),
            "raw_features": score_info.get("raw_features"),
        }

    def _compute_confidence(self, score: float, thr95: float, thr99: float) -> float:
        thr95 = float(thr95) if thr95 is not None else 0.0
        thr99 = float(thr99) if thr99 is not None else thr95

        if thr95 <= 0:
            thr95 = 1.0
        if thr99 < thr95:
            thr99 = thr95

        if score < thr95:
            conf = 1.0 - (score / thr95)
        else:
            denom = thr99 - thr95
            if denom <= 0:
                conf = 1.0
            else:
                conf = (score - thr95) / denom

        if conf < 0:
            return 0.0
        if conf > 1:
            return 1.0
        return float(conf)

    def score(self, features: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled or self._model is None:
            return {
                "score": None,
                "score_reason": "model_disabled",
                "missing_features": [],
                "partial_score": None,
                "threshold_95": 0.0,
                "threshold_99": 0.0,
                "features": {},
                "raw_features": {},
                "baseline_day": None,
                "baseline_person": None,
                "feature_debug": {},
            }
        return self._score_with_params(features)

    def _debug_enabled(self) -> bool:
        flag = os.getenv("DEBUG", "")
        return str(flag).lower() in {"1", "true", "yes", "on"}

    def _debug_log(self, payload: Dict[str, Any]) -> None:
        if not self._debug_enabled():
            return
        print("[RDS_DEBUG]", json.dumps(payload, ensure_ascii=False, default=str))

    def _score_with_params(self, features: Dict[str, Any]) -> Dict[str, Any]:
        params = self._params or {}
        weights = params.get("weights", {})
        min_scale = params.get("min_scale", {})
        baseline_person = params.get("baseline_person", [])
        baseline_person_day = params.get("baseline_person_day", [])
        thr95 = float(params.get("threshold_95", 0.0) or 0.0)
        thr99 = float(params.get("threshold_99", thr95) or thr95)

        if thr95 <= 0:
            thr95 = 1.0
        if thr99 <= 0:
            thr99 = thr95

        hour = int(features.get("hour", 0))
        dow = int(features.get("dow", 1))
        person = int(features.get("person", 0)) if features.get("person") is not None else 0

        score, feature_values, feature_debug, row_day, row_person = self.compute_anomaly_score(
            features=features,
            weights=weights,
            min_scale=min_scale,
            baseline_person=baseline_person,
            baseline_person_day=baseline_person_day,
        )

        missing_features = [name for name, value in feature_values.items() if value is None]
        missing_attendance = [name for name in missing_features if name in {"go", "home", "work"}]
        allow_partial = _bool_env("ANOMALY_SCORE_PARTIAL", "0")
        score_reason = None
        final_score: Optional[float] = float(score)
        if missing_attendance and not allow_partial:
            score_reason = "incomplete_attendance_pair"
            final_score = None

        return {
            "score": final_score,
            "score_reason": score_reason,
            "missing_features": missing_features,
            "partial_score": float(score),
            "threshold_95": thr95,
            "threshold_99": thr99,
            "features": feature_values,
            "raw_features": {
                "distance1_cm": features.get("distance1_cm"),
                "distance2_cm": features.get("distance2_cm"),
                "rssi": features.get("rssi"),
                "hour": hour,
                "dow": dow,
                "minute_of_day": features.get("minute_of_day"),
                "raw_event": features.get("raw_event"),
                "go": features.get("go"),
                "home": features.get("home"),
                "work": features.get("work"),
            },
            "baseline_day": row_day,
            "baseline_person": row_person,
            "feature_debug": feature_debug,
        }

    def compute_anomaly_score(
        self,
        features: Dict[str, Any],
        weights: Dict[str, float],
        min_scale: Dict[str, float],
        baseline_person: List[Dict[str, Any]],
        baseline_person_day: List[Dict[str, Any]],
    ) -> tuple[float, Dict[str, Optional[float]], Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        person = int(features.get("person", 0)) if features.get("person") is not None else 0
        dow = int(features.get("dow", 1))

        row_day = self._select_baseline_row(baseline_person_day, person=person, day_of_week=dow)
        row_person = self._select_baseline_row(baseline_person, person=person, day_of_week=None)

        feature_values = self._extract_feature_values(features, weights)
        feature_debug: Dict[str, Any] = {}

        score = 0.0
        for name, weight in weights.items():
            value = feature_values.get(name)
            if value is None:
                feature_debug[name] = {
                    "value": None,
                    "weight": float(weight),
                    "missing": True,
                }
                continue
            med, mad = self._get_baseline_stats(name, row_day, row_person)
            min_s = float(min_scale.get(name, 0.0) or 0.0)
            scale = mad if mad is not None else min_s
            if scale is None or scale <= 0:
                scale = min_s if min_s > 0 else 1.0

            if med is None:
                d = 0.0
                z = 0.0
                s = 0.0
            else:
                d = abs(value - med)
                s = scale
                z = 1.0 - math.exp(-(d / s)) if s > 0 else 0.0

            score += float(weight) * z

            feature_debug[name] = {
                "value": value,
                "weight": float(weight),
                "median": med,
                "mad": mad,
                "min_scale": min_s,
                "scale_used": scale,
                "distance": d,
                "score_component": z,
            }

        return score, feature_values, feature_debug, row_day, row_person


    def _normalize_label(self, label: str) -> str:
        l = label.strip().upper()
        mapping = {
            "ANDA_PERGI": "ANDA_PERGI",
            "ANDA_PULANG": "ANDA_PULANG",
            "ORANG_MASUK": "ORANG_MASUK",
            "ORANG_KELUAR": "ORANG_KELUAR",
            "PERGI": "ANDA_PERGI",
            "PULANG": "ANDA_PULANG",
            "MASUK": "ORANG_MASUK",
            "KELUAR": "ORANG_KELUAR",
        }
        return mapping.get(l, "UNKNOWN")

    def _fallback_label(self, raw_event: str) -> str:
        return label_from_raw_event(raw_event)

    def _fallback(self, features: Dict[str, Any]) -> PredictResult:
        return PredictResult(label=self._fallback_label(features.get("raw_event", "")))
    
    def _unwrap_if_list(self, obj):
        # cek class
        cls = [str(x) for x in list(self._robjects.r["class"](obj))]
        if "list" not in cls:
            return obj

        # ambil nama elemen list kalau ada
        try:
            names = list(self._robjects.r["names"](obj))
            names = [str(n) for n in names]
        except Exception:
            names = []

        # kandidat key yang sering dipakai menyimpan model
        candidates = ["model", "fit", "finalModel", "learner", "clf", "estimator"]

        for key in candidates:
            if key in names:
                picked = obj.rx2(key)
                picked_cls = [str(x) for x in list(self._robjects.r["class"](picked))]
                print(f"[RDS] Unwrapped list -> key='{key}', class={picked_cls}")
                return picked

        # kalau list 1 elemen, ambil elemen pertama
        try:
            if len(obj) == 1:
                picked = obj[0]
                picked_cls = [str(x) for x in list(self._robjects.r["class"](picked))]
                print(f"[RDS] Unwrapped list -> first element, class={picked_cls}")
                return picked
        except Exception:
            pass

        print(f"[RDS] RDS object is a list but no known key found. names={names}. Using fallback.")
        # biarin predict gagal lalu fallback, tapi sekarang lognya jelas
        return obj

    def _extract_params(self, m) -> Dict[str, Any]:
        params: Dict[str, Any] = {}

        try:
            names = list(self._robjects.r["names"](m))
            names = [str(n) for n in names]
        except Exception:
            names = []

        if "weights" in names:
            params["weights"] = self._named_vector_to_dict(m.rx2("weights"))
        if "min_scale" in names:
            params["min_scale"] = self._named_list_to_dict(m.rx2("min_scale"))
        if "baseline_person" in names:
            params["baseline_person"] = self._data_frame_to_rows(m.rx2("baseline_person"))
        if "baseline_person_day" in names:
            params["baseline_person_day"] = self._data_frame_to_rows(m.rx2("baseline_person_day"))
        if "threshold_95" in names:
            params["threshold_95"] = float(m.rx2("threshold_95")[0])
        if "threshold_99" in names:
            params["threshold_99"] = float(m.rx2("threshold_99")[0])

        return params

    def _named_vector_to_dict(self, vec) -> Dict[str, float]:
        try:
            names = list(self._robjects.r["names"](vec))
            names = [str(n) for n in names]
        except Exception:
            names = []

        result: Dict[str, float] = {}
        if names:
            for i, name in enumerate(names):
                result[name] = float(vec[i])
        else:
            for i in range(len(vec)):
                result[str(i)] = float(vec[i])
        return result

    def _named_list_to_dict(self, lst) -> Dict[str, float]:
        try:
            names = list(self._robjects.r["names"](lst))
            names = [str(n) for n in names]
        except Exception:
            names = []

        result: Dict[str, float] = {}
        for name in names:
            try:
                val = float(lst.rx2(name)[0])
            except Exception:
                try:
                    val = float(list(lst.rx2(name))[0])
                except Exception:
                    val = 0.0
            result[name] = val
        return result

    def _data_frame_to_rows(self, df) -> List[Dict[str, Any]]:
        try:
            colnames = list(self._robjects.r["names"](df))
            colnames = [str(c) for c in colnames]
        except Exception:
            return []

        if not colnames:
            return []

        length = len(df.rx2(colnames[0]))
        rows: List[Dict[str, Any]] = []
        int_cols = {"person", "day_of_week", "n_p", "n_pd"}

        for i in range(length):
            row: Dict[str, Any] = {}
            for col in colnames:
                val = df.rx2(col)[i]
                try:
                    if col in int_cols:
                        row[col] = int(val)
                    else:
                        row[col] = float(val)
                except Exception:
                    row[col] = val
            rows.append(row)

        return rows

    def _select_baseline_row(
        self,
        rows: List[Dict[str, Any]],
        person: Optional[int] = None,
        day_of_week: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        if not rows:
            return None

        def match(r: Dict[str, Any]) -> bool:
            if person is not None and "person" in r and int(r.get("person", -1)) != person:
                return False
            if day_of_week is not None and "day_of_week" in r and int(r.get("day_of_week", -1)) != day_of_week:
                return False
            return True

        if day_of_week is not None:
            for r in rows:
                if match(r):
                    return r

        if person is not None:
            for r in rows:
                if "person" in r and int(r.get("person", -1)) == person:
                    return r

        return rows[0]

    def _get_baseline_stats(
        self,
        name: str,
        row_day: Optional[Dict[str, Any]],
        row_person: Optional[Dict[str, Any]],
    ) -> tuple[Optional[float], Optional[float]]:
        # gunakan baseline per-day hanya jika n_pd cukup (>=5)
        candidates = []
        if row_day and int(row_day.get("n_pd", 0)) >= 5:
            candidates.append((row_day, f"med_{name}", f"mad_{name}"))
        candidates.extend(
            [
                (row_person, f"med_{name}_p", f"mad_{name}_p"),
                (row_person, f"med_{name}", f"mad_{name}"),
            ]
        )

        for row, med_key, mad_key in candidates:
            if row and med_key in row:
                med = float(row.get(med_key)) if row.get(med_key) is not None else None
                mad = float(row.get(mad_key)) if row.get(mad_key) is not None else None
                return med, mad

        return None, None

    def _extract_feature_values(self, features: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Optional[float]]:
        aliases = {
            "go": ["go", "go_min", "go_minutes"],
            "home": ["home", "home_min", "home_minutes"],
            "work": ["work", "work_min", "work_minutes"],
        }

        result: Dict[str, float] = {}
        for name in weights.keys():
            value_provided = name in features
            value = features.get(name) if value_provided else None

            if not value_provided:
                for key in aliases.get(name, []):
                    if key in features:
                        value = features.get(key)
                        value_provided = True
                        break

            # derive from event time if not explicitly provided
            if value is None and not value_provided and name in {"go", "home"}:
                minute_of_day = features.get("minute_of_day")
                direction = direction_from_raw_event(str(features.get("raw_event", "")))
                if minute_of_day is not None:
                    if name == "go" and direction == "OUT":
                        value = minute_of_day
                    if name == "home" and direction == "IN":
                        value = minute_of_day

            if value is None and not value_provided and name == "work":
                go_val = features.get("go") or features.get("go_min")
                home_val = features.get("home") or features.get("home_min")
                if go_val is not None and home_val is not None:
                    value = float(home_val) - float(go_val)
                    if value < 0:
                        value += 24 * 60

            if value is None:
                if name in {"go", "home", "work"}:
                    result[name] = None
                    continue
                value = 0.0

            try:
                result[name] = float(value)
            except Exception:
                result[name] = None

        return result


_model_singleton: Optional[RDSModel] = None

def get_model() -> RDSModel:
    global _model_singleton
    if _model_singleton is None:
        _model_singleton = RDSModel(MODEL_RDS_PATH)
    return _model_singleton
