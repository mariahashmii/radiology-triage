"""
model_utils.py - NeuroScan Edge Inference Pipeline (v5 - Production Grade)

ARCHITECTURE:
Dual-model selective ensemble using DenseNet-121 (224px) and ResNet-50 (512px).
Each pathology uses only models with clean noise baselines for that specific head.

KEY DESIGN DECISIONS:
- NO CLAHE: CLAHE amplifies noise textures that both models misinterpret as
  pathology (e.g., Effusion goes from 0.00 to 1.00 on noise with CLAHE).
  The models were trained on raw normalized images without CLAHE.
- TTA: Horizontal flip only (averaging 2 passes per model). This reduces
  random noise variance without adding CLAHE artifacts.
- Selective ensemble: Each pathology uses only model(s) with noise ceiling < 0.40.

NOISE BASELINES (op_norm output on 50 noise images WITHOUT CLAHE, mean+3*std):

                             DenseNet-121    ResNet-50       Strategy
Atelectasis                     0.5828         0.0657    -> ResNet only
Consolidation                   0.0567         0.0024    -> Both (ensemble)
Infiltration                    0.0003         0.0016    -> Both (ensemble)
Pneumothorax                    0.3683         0.0000    -> Both (ensemble)
Edema                           0.3417         0.0000    -> Both (ensemble)
Emphysema                       0.3189         0.0000    -> Both (ensemble)
Fibrosis                        0.0000         0.0000    -> Both (ensemble)
Effusion                        0.5213         0.0000    -> ResNet only
Pneumonia                       0.0003         1.0000    -> DenseNet only
Pleural_Thickening              0.0001         0.0002    -> Both (ensemble)
Cardiomegaly                    0.0752         0.0199    -> Both (ensemble)
Nodule                          0.0191         0.0196    -> Both (ensemble)
Mass                            0.0001         0.1224    -> Both (ensemble)
Hernia                          0.0115         0.0000    -> Both (ensemble)
Lung Lesion                     0.0003         0.5000    -> DenseNet only
Fracture                        0.3134         0.8776    -> DenseNet only
Lung Opacity                    0.9276         0.9999    -> BOTH BIASED
Enlarged Cardiomediastinum      0.0000         0.5000    -> DenseNet only
"""
import torch
import torchxrayvision as xrv
import numpy as np
from PIL import Image
import cv2
import logging

logger = logging.getLogger("neuroscan.model")

# ══════════════════════════════════════════════════════════════════════
# Model Setup
# ══════════════════════════════════════════════════════════════════════

logger.info("Loading DenseNet-121 (224px)...")
densenet = xrv.models.DenseNet(weights="densenet121-res224-all")
densenet.eval()

logger.info("Loading ResNet-50 (512px)...")
resnet = xrv.models.ResNet(weights="resnet50-res512-all")
resnet.eval()

PATHOLOGIES = list(densenet.pathologies)

# ══════════════════════════════════════════════════════════════════════
# Noise Ceilings (WITHOUT CLAHE — this is critical)
# ══════════════════════════════════════════════════════════════════════

_DENSENET_NOISE = {
    "Atelectasis": 0.5828, "Consolidation": 0.0567, "Infiltration": 0.0003,
    "Pneumothorax": 0.3683, "Edema": 0.3417, "Emphysema": 0.3189,
    "Fibrosis": 0.0000, "Effusion": 0.5213, "Pneumonia": 0.0003,
    "Pleural_Thickening": 0.0001, "Cardiomegaly": 0.0752, "Nodule": 0.0191,
    "Mass": 0.0001, "Hernia": 0.0115, "Lung Lesion": 0.0003,
    "Fracture": 0.3134, "Lung Opacity": 0.9276,
    "Enlarged Cardiomediastinum": 0.0000,
}

_RESNET_NOISE = {
    "Atelectasis": 0.0657, "Consolidation": 0.0024, "Infiltration": 0.0016,
    "Pneumothorax": 0.0000, "Edema": 0.0000, "Emphysema": 0.0000,
    "Fibrosis": 0.0000, "Effusion": 0.0000, "Pneumonia": 1.0000,
    "Pleural_Thickening": 0.0002, "Cardiomegaly": 0.0199, "Nodule": 0.0196,
    "Mass": 0.1224, "Hernia": 0.0000, "Lung Lesion": 0.5000,
    "Fracture": 0.8776, "Lung Opacity": 0.9999,
    "Enlarged Cardiomediastinum": 0.5000,
}

_CLEAN_THRESHOLD = 0.40
SAFETY_MARGIN = 0.03

# Build per-pathology strategy
_PATHOLOGY_CONFIG = {}
for name in PATHOLOGIES:
    dn_noise = _DENSENET_NOISE.get(name, 1.0)
    rn_noise = _RESNET_NOISE.get(name, 1.0)
    dn_clean = dn_noise < _CLEAN_THRESHOLD
    rn_clean = rn_noise < _CLEAN_THRESHOLD

    if dn_clean and rn_clean:
        strategy = "ensemble"
        boundary = max(0.50, max(dn_noise, rn_noise) + SAFETY_MARGIN)
    elif dn_clean:
        strategy = "densenet"
        boundary = max(0.50, dn_noise + SAFETY_MARGIN)
    elif rn_clean:
        strategy = "resnet"
        boundary = max(0.50, rn_noise + SAFETY_MARGIN)
    else:
        strategy = "high_threshold"
        boundary = min(0.98, max(0.50, min(dn_noise, rn_noise) + SAFETY_MARGIN + 0.05))

    _PATHOLOGY_CONFIG[name] = {
        "strategy": strategy,
        "boundary": boundary,
        "dn_clean": dn_clean,
        "rn_clean": rn_clean,
    }

DECISION_BOUNDARIES = {name: cfg["boundary"] for name, cfg in _PATHOLOGY_CONFIG.items()}

WEAK_MARGIN = 0.02
NO_FINDINGS_LABEL = "No Significant Findings"

# ══════════════════════════════════════════════════════════════════════
# Image Preparation (NO CLAHE — raw normalized input)
# ══════════════════════════════════════════════════════════════════════

def _prepare_for_densenet(img_gray_arr):
    """Prepare image for DenseNet-121 (224px)."""
    img_norm = xrv.datasets.normalize(img_gray_arr, 255)
    img_norm = img_norm[None, :, :]
    transform = xrv.datasets.XRayResizer(224)
    return torch.from_numpy(transform(img_norm)).unsqueeze(0)


def _prepare_for_resnet(img_gray_arr):
    """Prepare image for ResNet-50 (512px)."""
    img_norm = xrv.datasets.normalize(img_gray_arr, 255)
    img_norm = img_norm[None, :, :]
    transform = xrv.datasets.XRayResizer(512)
    return torch.from_numpy(transform(img_norm)).unsqueeze(0)


# Backward compatibility alias for heatmap_utils
def _prepare_image(img_gray_arr):
    return _prepare_for_densenet(img_gray_arr)


def _flip_horizontal(img_gray_arr):
    return np.fliplr(img_gray_arr).copy()


# ══════════════════════════════════════════════════════════════════════
# Inference Engine
# ══════════════════════════════════════════════════════════════════════

def _run_single_model(model_obj, prep_fn, img_gray_arr):
    tensor = prep_fn(img_gray_arr)
    with torch.no_grad():
        return model_obj(tensor)[0].numpy()


def _run_inference_with_tta(img_gray_arr):
    """
    Dual-model ensemble with Test-Time Augmentation (horizontal flip).
    NO CLAHE — models receive raw normalized images as they were trained on.
    """
    img_flipped = _flip_horizontal(img_gray_arr)

    # DenseNet: original + flipped, averaged
    dn_orig = _run_single_model(densenet, _prepare_for_densenet, img_gray_arr)
    dn_flip = _run_single_model(densenet, _prepare_for_densenet, img_flipped)
    dn_avg = (dn_orig + dn_flip) / 2.0

    # ResNet: original + flipped, averaged
    rn_orig = _run_single_model(resnet, _prepare_for_resnet, img_gray_arr)
    rn_flip = _run_single_model(resnet, _prepare_for_resnet, img_flipped)
    rn_avg = (rn_orig + rn_flip) / 2.0

    # Selective ensemble per pathology
    results = []
    for i, name in enumerate(PATHOLOGIES):
        cfg = _PATHOLOGY_CONFIG.get(name, {"strategy": "densenet", "boundary": 0.50})
        strategy = cfg["strategy"]
        boundary = cfg["boundary"]

        if strategy == "ensemble":
            score = (float(dn_avg[i]) + float(rn_avg[i])) / 2.0
        elif strategy == "resnet":
            score = float(rn_avg[i])
        elif strategy == "densenet":
            score = float(dn_avg[i])
        else:  # high_threshold
            if _DENSENET_NOISE.get(name, 1.0) < _RESNET_NOISE.get(name, 1.0):
                score = float(dn_avg[i])
            else:
                score = float(rn_avg[i])

        margin = score - boundary

        if margin > 0:
            headroom = 1.0 - boundary
            cal_conf = margin / headroom if headroom > 0 else 0.0
        else:
            cal_conf = 0.0

        results.append({
            "name": name,
            "score": score,
            "boundary": boundary,
            "margin": margin,
            "strategy": strategy,
            "calibrated_conf": min(1.0, max(0.0, cal_conf)),
            "is_positive": margin > 0,
            "is_weak": -WEAK_MARGIN <= margin <= 0,
        })

    results.sort(key=lambda x: x["margin"], reverse=True)
    return results


# ══════════════════════════════════════════════════════════════════════
# Clinical Correlation Rules
# ══════════════════════════════════════════════════════════════════════

_CO_OCCURRING = [
    ({"Consolidation", "Pneumonia"}, 1.10),
    ({"Effusion", "Atelectasis"}, 1.10),
    ({"Edema", "Effusion"}, 1.10),
    ({"Cardiomegaly", "Effusion"}, 1.10),
    ({"Infiltration", "Pneumonia"}, 1.10),
    ({"Mass", "Nodule"}, 1.10),
]

_INCOMPATIBLE = [
    ({"Emphysema", "Effusion"},),  # air trapping vs fluid
]


def _apply_correlation_rules(results):
    """Adjust confidence based on clinical co-occurrence / incompatibility."""
    positive_names = {r["name"] for r in results if r["is_positive"]}

    for r in results:
        name = r["name"]

        # Boost co-occurring findings
        for pair_set, boost_factor in _CO_OCCURRING:
            if name in pair_set:
                partner = list(pair_set - {name})[0]
                if partner in positive_names:
                    r["calibrated_conf"] = min(1.0, r["calibrated_conf"] * boost_factor)

        # Suppress incompatible findings
        for (pair_set,) in _INCOMPATIBLE:
            if name in pair_set and r["is_positive"]:
                partner = list(pair_set - {name})[0]
                partner_r = next((x for x in results if x["name"] == partner), None)
                if partner_r and partner_r["is_positive"]:
                    if r["margin"] < partner_r["margin"]:
                        r["is_positive"] = False
                        r["calibrated_conf"] = 0.0

    return results


# ══════════════════════════════════════════════════════════════════════
# Finding Selection
# ══════════════════════════════════════════════════════════════════════

def _select_findings(results):
    strong = []
    weak = []
    for r in results:
        if r["is_positive"]:
            strong.append((r["name"], r["calibrated_conf"]))
        elif r["is_weak"]:
            weak.append((r["name"], r["calibrated_conf"]))
    return strong, weak, len(strong) == 0


# ══════════════════════════════════════════════════════════════════════
# Input Validation
# ══════════════════════════════════════════════════════════════════════

def _validate_image(uploaded_file):
    """Comprehensive validation for medical X-ray images."""
    img = Image.open(uploaded_file)
    width, height = img.size

    if width < 64 or height < 64:
        raise ValueError(
            f"Invalid image: Resolution too low ({width}x{height}). "
            "Minimum 64x64 pixels required."
        )

    if img.mode in ("RGB", "RGBA"):
        arr = np.array(img.convert("RGB"))
        channel_std = np.mean(np.std(arr, axis=2))
        if channel_std > 5.0:
            raise ValueError(
                "Invalid image: This appears to be a color photograph, not a medical X-ray. "
                "Please upload a grayscale chest X-ray image."
            )

    img_gray = img.convert("L")
    img_arr = np.array(img_gray)

    if np.std(img_arr) < 5.0:
        raise ValueError(
            "Invalid image: The image has insufficient contrast (appears blank or uniform)."
        )

    pixel_mean = np.mean(img_arr)
    if pixel_mean < 10 or pixel_mean > 245:
        raise ValueError(
            "Invalid image: The image brightness is outside the expected range."
        )

    # Entropy check — near-max entropy = random noise
    histogram = np.histogram(img_arr, bins=256, range=(0, 256))[0]
    histogram = histogram / histogram.sum()
    nonzero = histogram[histogram > 0]
    entropy = -np.sum(nonzero * np.log2(nonzero))
    if entropy > 7.8:
        raise ValueError(
            "Invalid image: The image appears to be random noise, not a medical image."
        )

    aspect = max(width, height) / max(1, min(width, height))
    if aspect > 4.0:
        raise ValueError(
            f"Invalid image: Aspect ratio {aspect:.1f}:1 is too extreme for a chest X-ray."
        )

    return img_arr


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def predict_xray(uploaded_file, top_k=5):
    """Full production pipeline: validate -> TTA -> ensemble -> correlate -> results."""

    img_gray_arr = _validate_image(uploaded_file)
    all_results = _run_inference_with_tta(img_gray_arr)
    all_results = _apply_correlation_rules(all_results)
    strong, weak, no_significant = _select_findings(all_results)

    if not no_significant:
        display_label = strong[0][0]
        display_score = strong[0][1]
    else:
        display_label = NO_FINDINGS_LABEL
        display_score = max(0.0, all_results[0]["calibrated_conf"]) if all_results else 0.0

    display_score = max(0.0, min(1.0, float(display_score)))

    selected_scores = [(n, max(0.0, min(1.0, float(s)))) for n, s in strong]
    top_predictions = [
        (r["name"], max(0.0, min(1.0, r["calibrated_conf"])))
        for r in all_results[:top_k]
    ]

    return {
        "predictions": top_predictions,
        "selected_findings": [n for n, _ in strong],
        "selected_scores": selected_scores,
        "display_label": display_label,
        "display_score": display_score,
        "top_score": display_score,
        "no_findings": no_significant,
        "weak_findings": [(n, max(0.0, min(1.0, float(s)))) for n, s in weak],
    }


# ══════════════════════════════════════════════════════════════════════
# Warm-up
# ══════════════════════════════════════════════════════════════════════

def _warmup():
    dummy = np.random.RandomState(0).randint(50, 200, (64, 64), dtype=np.uint8)
    _run_single_model(densenet, _prepare_for_densenet, dummy)
    _run_single_model(resnet, _prepare_for_resnet, dummy)
    logger.info("Model warm-up complete.")

_warmup()

# Backward compat for heatmap_utils
model = densenet