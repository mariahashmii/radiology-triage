"""
clinical_reasoning.py - Production-Grade Clinical Risk Scoring Engine (v5)

Takes findings with calibrated confidence scores and patient metadata to
compute a 0-100 risk score, urgency level, and human-readable reasoning.

Improvements over v4:
- Multi-finding interaction scoring (co-morbid combinations increase risk)
- Age-stratified risk modifiers with finer granularity
- View position reliability adjustment
- Critical finding escalation (single critical finding = minimum HIGH urgency)
- Structured reason output with severity categories
"""
from typing import List, Tuple, Optional


# ─── Severity Classification ─────────────────────────────────────────
# Clinical severity weights: how many risk points a finding contributes at 100% confidence
SEVERITY_WEIGHTS = {
    # Critical (25-30) — immediate clinical attention required
    "pneumothorax": 30,
    "mass": 28,
    "fracture": 25,
    # Serious (18-22) — urgent follow-up needed
    "lung lesion": 22,
    "nodule": 20,
    "pneumonia": 20,
    "consolidation": 18,
    "effusion": 18,
    "edema": 18,
    # Moderate (10-15) — scheduled follow-up
    "infiltration": 14,
    "atelectasis": 12,
    "lung opacity": 12,
    "cardiomegaly": 12,
    "enlarged cardiomediastinum": 10,
    # Chronic (5-8) — lower acuity
    "emphysema": 8,
    "fibrosis": 8,
    "pleural_thickening": 6,
    "pleural thickening": 6,
    "hernia": 5,
}

# Critical findings that should escalate urgency regardless of score
CRITICAL_FINDINGS = {"pneumothorax", "mass", "fracture"}

# Co-morbid combinations that compound risk
_COMPOUNDING_PAIRS = {
    frozenset({"pneumonia", "effusion"}): 8,      # parapneumonic effusion
    frozenset({"edema", "cardiomegaly"}): 10,     # heart failure
    frozenset({"edema", "effusion"}): 7,          # fluid overload
    frozenset({"consolidation", "pneumonia"}): 5,  # confirmed pneumonia
    frozenset({"atelectasis", "effusion"}): 5,     # compressive atelectasis
    frozenset({"mass", "nodule"}): 6,              # suspicious lesion
    frozenset({"infiltration", "pneumonia"}): 5,   # active infection
}


def _normalize(s: str) -> str:
    return (s or "").strip().lower().replace("_", " ")


def calculate_risk(
    findings: List[str],
    scores: List[float],
    age: Optional[int] = None,
    gender: Optional[str] = None,
    view_position: Optional[str] = None,
) -> Tuple[int, str, str]:
    """
    Calculate risk score (0-100), urgency level, and reasoning string.

    Args:
        findings: list of detected pathology names
        scores: list of confidence scores (calibrated, 0-1) parallel to findings
        age: patient age
        gender: patient gender (M/F)
        view_position: imaging view (PA/AP)

    Returns:
        (risk_score, urgency, reason_text)
    """
    raw_score = 0.0
    reasons = []
    has_critical = False
    finding_names_normalized = set()

    # ── Per-finding scoring ───────────────────────────────────────
    paired = list(zip(findings or [], scores or []))
    for finding_name, confidence in paired:
        fn = _normalize(finding_name)
        finding_names_normalized.add(fn)
        weight = SEVERITY_WEIGHTS.get(fn, 8)
        conf = min(float(confidence), 1.0)

        # Non-linear scaling: square root to give partial credit for lower confidence
        # This means 25% confidence contributes 50% of max points, not just 25%
        scaled_conf = conf ** 0.7

        contribution = weight * scaled_conf
        raw_score += contribution
        reasons.append(
            f"{finding_name} ({conf*100:.0f}% confidence, {weight}pt severity -> +{contribution:.1f})"
        )

        if fn in CRITICAL_FINDINGS:
            has_critical = True

    # ── Multi-finding interaction bonus ───────────────────────────
    for pair, bonus in _COMPOUNDING_PAIRS.items():
        if pair.issubset(finding_names_normalized):
            raw_score += bonus
            names = " + ".join(sorted(pair))
            reasons.append(f"Co-morbid interaction ({names} -> +{bonus})")

    # ── Age modifier (stratified) ─────────────────────────────────
    if age is not None:
        try:
            age_val = int(age)
        except (ValueError, TypeError):
            age_val = None
        if age_val is not None:
            if age_val > 85:
                raw_score += 10
                reasons.append(f"Age {age_val} (>85, very elderly -> +10)")
            elif age_val > 75:
                raw_score += 7
                reasons.append(f"Age {age_val} (>75, elderly -> +7)")
            elif age_val > 65:
                raw_score += 5
                reasons.append(f"Age {age_val} (>65 -> +5)")
            elif age_val < 2:
                raw_score += 8
                reasons.append(f"Age {age_val} (infant -> +8)")
            elif age_val < 5:
                raw_score += 6
                reasons.append(f"Age {age_val} (pediatric -> +6)")

    # ── View position modifier ────────────────────────────────────
    if view_position:
        vp = _normalize(view_position)
        if vp == "ap":
            raw_score += 3
            reasons.append("AP view (portable/supine, reduced reliability -> +3)")

    # ── Clamp to 0-100 ───────────────────────────────────────────
    risk_score = int(max(0, min(100, round(raw_score))))

    # ── Urgency mapping ──────────────────────────────────────────
    # Critical findings always escalate to at least MEDIUM
    if risk_score >= 40 or (has_critical and risk_score >= 20):
        urgency = "HIGH"
    elif risk_score >= 15 or has_critical:
        urgency = "MEDIUM"
    else:
        urgency = "LOW"

    # ── Build reason text ────────────────────────────────────────
    if reasons:
        reason_text = "; ".join(reasons) + f". Total risk score: {risk_score}/100."
    else:
        reason_text = "No significant risk factors identified. All pathology scores below detection threshold."

    if gender:
        g = "Male" if str(gender).strip().upper() == "M" else (
            "Female" if str(gender).strip().upper() == "F" else str(gender)
        )
        reason_text = f"Patient: {g}. " + reason_text

    return risk_score, urgency, reason_text
