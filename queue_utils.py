"""
queue_utils.py - Urgency classification for the patient queue (v5).

Delegates to the clinical reasoning engine for urgency, with a fallback
severity-mapping when findings are present but no scores are available.
"""
from model_utils import NO_FINDINGS_LABEL

try:
    from clinical_reasoning import calculate_risk, CRITICAL_FINDINGS
except Exception:
    calculate_risk = None
    CRITICAL_FINDINGS = set()


# Severity groups for fallback classification
HIGH_SEVERITY = {"Pneumothorax", "Mass", "Fracture", "Lung Lesion", "Nodule"}
MEDIUM_SEVERITY = {
    "Pneumonia", "Effusion", "Infiltration", "Consolidation",
    "Atelectasis", "Edema", "Cardiomegaly",
}
LOW_SEVERITY = {
    "Fibrosis", "Pleural_Thickening", "Pleural Thickening",
    "Emphysema", "Hernia", "Enlarged Cardiomediastinum",
}


def get_urgency(detected_findings, top_score=0.0, age=None, gender=None, view_position=None):
    """Return an emoji-prefixed urgency string (e.g., '\U0001f534 HIGH')."""
    if not detected_findings or detected_findings == [NO_FINDINGS_LABEL]:
        return "\U0001f7e2 LOW"

    # Use clinical reasoning engine when available
    if calculate_risk is not None:
        try:
            _risk_score, urgency, _reason = calculate_risk(
                detected_findings,
                [top_score] * len(detected_findings),
                age=age,
                gender=gender,
                view_position=view_position,
            )
            if urgency == "HIGH":
                return "\U0001f534 HIGH"
            if urgency == "MEDIUM":
                return "\U0001f7e1 MEDIUM"
            return "\U0001f7e2 LOW"
        except Exception:
            pass

    # Fallback: severity-set matching
    detected_set = set(detected_findings)

    if detected_set & HIGH_SEVERITY:
        return "\U0001f534 HIGH"
    if detected_set & MEDIUM_SEVERITY:
        return "\U0001f7e1 MEDIUM"
    if detected_set & LOW_SEVERITY:
        return "\U0001f7e2 LOW"

    if top_score >= 0.30:
        return "\U0001f7e1 MEDIUM"

    return "\U0001f7e2 LOW"