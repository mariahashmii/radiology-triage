"""
heatmap_utils.py - GradCAM heatmap generator (v5 - Production Grade)

Uses DenseNet for GradCAM visualization. Targets the pathology with the
highest margin above its decision boundary.

Output is 448px for high-resolution display.
"""
import torch
import numpy as np
import cv2
from PIL import Image
from pytorch_grad_cam import GradCAM
from pytorch_grad_cam.utils.image import show_cam_on_image
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

from model_utils import densenet, DECISION_BOUNDARIES, _prepare_for_densenet, PATHOLOGIES

# Cache GradCAM object
_target_layers = [densenet.features.denseblock4]
_cam = GradCAM(model=densenet, target_layers=_target_layers)

OUTPUT_SIZE = 448


def generate_heatmap(uploaded_file):
    """Generate a high-resolution GradCAM heatmap."""

    img = Image.open(uploaded_file).convert("L")
    img_arr = np.array(img)

    # Prepare for DenseNet (no CLAHE — raw normalized)
    input_tensor = _prepare_for_densenet(img_arr)

    with torch.no_grad():
        preds = densenet(input_tensor)[0].numpy()

    # Target the pathology with highest margin above boundary
    best_idx = 0
    best_margin = -999.0
    for i, name in enumerate(PATHOLOGIES):
        boundary = DECISION_BOUNDARIES.get(name, 0.50)
        margin = float(preds[i]) - boundary
        if margin > best_margin:
            best_margin = margin
            best_idx = i

    # GradCAM
    targets = [ClassifierOutputTarget(best_idx)]
    grayscale_cam = _cam(input_tensor=input_tensor, targets=targets)[0]

    # Build high-res overlay
    rgb_img = cv2.resize(img_arr, (OUTPUT_SIZE, OUTPUT_SIZE))
    rgb_img = rgb_img.astype(np.float32) / 255.0
    rgb_img = np.stack([rgb_img] * 3, axis=-1)

    cam_resized = cv2.resize(grayscale_cam, (OUTPUT_SIZE, OUTPUT_SIZE))
    cam_resized[cam_resized < 0.15] = 0.0  # suppress low-activation noise

    heatmap = show_cam_on_image(rgb_img, cam_resized, use_rgb=True)
    return heatmap