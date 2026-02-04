from collections.abc import Callable, Generator

import numpy as np
from rapidfuzz import process, fuzz
from typing import TypeVar
from sklearn.cluster import DBSCAN

DataType = TypeVar("DataType")


def group_items_by_string_score(
    data: list[DataType],
    score: int = 80,
    processor: Callable[[DataType], str] | None = None,
    comparer: Callable[..., int] = fuzz.token_set_ratio,
) -> Generator[tuple[str, list[DataType]], None, None]:
    """HIGH PERFORMANCE ATTEMPT1"""
    processed_indices = []
    for i, current_item in enumerate(data):
        if i in processed_indices:
            continue

        current_group_indices = []

        for j, candidate_item in enumerate(data):
            if j in processed_indices:
                continue
            if i == j:
                current_group_indices.append(j)
                continue
            if comparer(current_item, candidate_item, processor=processor) > score:
                current_group_indices.append(j)

        processed_indices.extend(current_group_indices)
        yield processor(current_item), [data[idx] for idx in current_group_indices]


def group_items_by_string_distance(
    data: list[DataType],
    score: int = 80,
    processor: Callable[[DataType], str] | None = None,
    comparer: Callable[..., int] = fuzz.token_set_ratio,
) -> Generator[tuple[str, list[DataType]], None, None]:
    """HIGH PERFORMANCE ATTEMPT2"""

    similarity_matrix = process.cdist(data, data, scorer=comparer, processor=processor, workers=-1, dtype=np.uint8)

    distance_matrix = 100 - similarity_matrix
    eps = 100 - score
    db = DBSCAN(eps=eps, min_samples=1, metric="precomputed").fit(distance_matrix)

    grouped_objects = {}
    for idx, label in enumerate(db.labels_):
        grouped_objects.setdefault(label, []).append(data[idx])
    for key, values in grouped_objects.items():
        yield key, values


def group_items_by_string_distance_v2(
    data: list[DataType],
    score: int = 80,
    processor: Callable[[DataType], str] | None = None,
    comparer: Callable[..., int] = fuzz.token_set_ratio,
) -> Generator[tuple[str, list[DataType]], None, None]:
    """HIGH PERFORMANCE ATTEMPT3"""

    normalized_strings = [processor(obj) for obj in data]
    similarity_matrix = process.cdist(
        normalized_strings, normalized_strings, scorer=comparer, score_cutoff=score, workers=-1, dtype=np.uint8
    )

    distance_matrix = 100 - similarity_matrix
    eps = 100 - score
    db = DBSCAN(eps=eps, min_samples=1, metric="precomputed").fit(distance_matrix)

    grouped_objects = {}
    for idx, label in enumerate(db.labels_):
        grouped_objects.setdefault(label, []).append(data[idx])
    for key, values in grouped_objects.items():
        yield key, values
