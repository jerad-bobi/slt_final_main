from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.db.models import Count, Max

from accounts.models import SkeletalSignSample


_CAPTURE_ROOT = settings.BASE_DIR / 'captured_skeletal_signs'
_MODEL_CACHE: dict[str, object] = {
    'signature': None,
    'model': None,
}
_MIN_CANDIDATE_CONFIDENCE = 0.20
_CANDIDATE_CONFIDENCE_RATIO = 0.55
_MAX_CANDIDATES = 3


def normalize_landmarks(landmarks: list[dict]) -> list[float] | None:
    if not isinstance(landmarks, list) or len(landmarks) < 21:
        return None

    try:
        points = [(float(item['x']), float(item['y'])) for item in landmarks[:21]]
    except (TypeError, ValueError, KeyError):
        return None

    wrist_x, wrist_y = points[0]
    centered = [(x - wrist_x, y - wrist_y) for x, y in points]

    # Normalize in-plane rotation so equivalent poses are closer in feature space.
    middle_mcp_x, middle_mcp_y = centered[9]
    if abs(middle_mcp_x) > 1e-9 or abs(middle_mcp_y) > 1e-9:
        current_angle = math.atan2(middle_mcp_y, middle_mcp_x)
        target_angle = -math.pi / 2
        rotation = target_angle - current_angle
        cos_theta = math.cos(rotation)
        sin_theta = math.sin(rotation)
        centered = [
            (
                (x * cos_theta) - (y * sin_theta),
                (x * sin_theta) + (y * cos_theta),
            )
            for x, y in centered
        ]

    max_radius = max(math.hypot(x, y) for x, y in centered)
    if max_radius <= 1e-9:
        return None

    return [value / max_radius for point in centered for value in point]


def _iter_sample_files() -> Iterable[Path]:
    if not _CAPTURE_ROOT.exists():
        return []

    return _CAPTURE_ROOT.glob('*/*.json')


def _build_signature() -> tuple[tuple[str, int, int], ...]:
    db_aggregate = SkeletalSignSample.objects.aggregate(
        sample_count=Count('id'),
        latest_id=Max('id'),
        latest_captured=Max('captured_at'),
    )

    db_signature = (
        'db',
        int(db_aggregate.get('sample_count') or 0),
        int(db_aggregate.get('latest_id') or 0),
        int(db_aggregate['latest_captured'].timestamp()) if db_aggregate.get('latest_captured') else 0,
    )

    signature_items = []
    for file_path in sorted(_iter_sample_files()):
        stat = file_path.stat()
        signature_items.append((str(file_path), stat.st_mtime_ns, stat.st_size))
    return (db_signature, *signature_items)


def _load_model() -> dict:
    sign_vectors: dict[str, list[list[float]]] = {}
    png_only_samples = 0

    db_samples = SkeletalSignSample.objects.values('sign_folder', 'feature_vector')
    db_sample_count = 0

    for sample in db_samples.iterator():
        sign_name = str(sample.get('sign_folder', '')).strip()
        feature_vector = sample.get('feature_vector')

        if not sign_name or not isinstance(feature_vector, list) or not feature_vector:
            continue

        try:
            clean_vector = [float(value) for value in feature_vector]
        except (TypeError, ValueError):
            continue

        sign_vectors.setdefault(sign_name, []).append(clean_vector)
        db_sample_count += 1

    if _CAPTURE_ROOT.exists():
        for image_path in _CAPTURE_ROOT.glob('*/*.png'):
            if not image_path.with_suffix('.json').exists():
                png_only_samples += 1

    if db_sample_count == 0:
        for file_path in _iter_sample_files():
            try:
                payload = json.loads(file_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue

            sign_name = str(payload.get('sign_folder', '')).strip()
            feature_vector = payload.get('feature_vector')

            if not sign_name or not isinstance(feature_vector, list) or not feature_vector:
                continue

            try:
                clean_vector = [float(value) for value in feature_vector]
            except (TypeError, ValueError):
                continue

            sign_vectors.setdefault(sign_name, []).append(clean_vector)

    centroids = {}
    sample_count = 0

    for sign_name, vectors in sign_vectors.items():
        if not vectors:
            continue

        dimension = len(vectors[0])
        valid_vectors = [vector for vector in vectors if len(vector) == dimension]
        if not valid_vectors:
            continue

        centroid = []
        for i in range(dimension):
            centroid.append(sum(vector[i] for vector in valid_vectors) / len(valid_vectors))

        centroids[sign_name] = {
            'vector': centroid,
            'samples': len(valid_vectors),
        }
        sample_count += len(valid_vectors)

    return {
        'centroids': centroids,
        'samples': sample_count,
        'classes': len(centroids),
        'png_only_samples': png_only_samples,
        'db_samples': db_sample_count,
    }


def get_classifier_model() -> dict:
    signature = _build_signature()
    if _MODEL_CACHE['signature'] == signature and _MODEL_CACHE['model'] is not None:
        return _MODEL_CACHE['model']

    model = _load_model()
    _MODEL_CACHE['signature'] = signature
    _MODEL_CACHE['model'] = model
    return model


def predict_sign_from_landmarks(landmarks: list[dict]) -> dict:
    feature_vector = normalize_landmarks(landmarks)
    if feature_vector is None:
        return {
            'ok': False,
            'error': 'Invalid landmarks.',
        }

    model = get_classifier_model()
    centroids = model.get('centroids', {})

    if not centroids:
        png_only_samples = int(model.get('png_only_samples', 0) or 0)
        if png_only_samples:
            return {
                'ok': False,
                'error': 'Found legacy PNG captures without ML metadata. Please recapture samples using the current capture mode.',
                'classes': 0,
                'samples': 0,
                'png_only_samples': png_only_samples,
            }

        return {
            'ok': False,
            'error': 'No training data found. Capture samples first.',
            'classes': 0,
            'samples': 0,
            'png_only_samples': 0,
        }

    # Evaluate both the original and mirrored hand to reduce handedness mismatch.
    mirrored_feature_vector = feature_vector.copy()
    for point_index in range(0, len(mirrored_feature_vector), 2):
        mirrored_feature_vector[point_index] = -mirrored_feature_vector[point_index]

    scored_matches = []

    for sign_name, descriptor in centroids.items():
        centroid = descriptor['vector']
        if len(centroid) != len(feature_vector):
            continue

        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(feature_vector, centroid)))
        mirrored_distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(mirrored_feature_vector, centroid)))
        distance = min(distance, mirrored_distance)

        scored_matches.append(
            {
                'sign': sign_name,
                'distance': distance,
                'samples': int(descriptor.get('samples', 0) or 0),
            }
        )

    scored_matches.sort(key=lambda item: item['distance'])

    best_match = scored_matches[0] if scored_matches else None

    best_sign = best_match['sign'] if best_match else None
    best_distance = best_match['distance'] if best_match else None

    if best_sign is None or best_distance is None:
        return {
            'ok': False,
            'error': 'Classifier model is not ready.',
            'classes': model.get('classes', 0),
            'samples': model.get('samples', 0),
        }

    confidence = 1.0 / (1.0 + best_distance)
    best_descriptor = centroids.get(best_sign, {})

    candidate_predictions = []
    for match in scored_matches:
        candidate_confidence = 1.0 / (1.0 + float(match['distance']))
        candidate_predictions.append(
            {
                'sign': match['sign'],
                'distance': match['distance'],
                'confidence': candidate_confidence,
                'confidence_percent': round(candidate_confidence * 100),
                'samples': match['samples'],
            }
        )

    high_confidence_candidates = [
        candidate
        for candidate in candidate_predictions
        if candidate['confidence'] >= _MIN_CANDIDATE_CONFIDENCE
        and candidate['confidence'] >= confidence * _CANDIDATE_CONFIDENCE_RATIO
    ][: _MAX_CANDIDATES]

    if not high_confidence_candidates:
        high_confidence_candidates = candidate_predictions[:1]

    return {
        'ok': True,
        'predicted_sign': best_sign,
        'confidence': confidence,
        'confidence_percent': round(confidence * 100),
        'distance': best_distance,
        'classes': model.get('classes', 0),
        'samples': model.get('samples', 0),
        'matched_samples': best_descriptor.get('samples', 0),
        'candidates': high_confidence_candidates,
    }
