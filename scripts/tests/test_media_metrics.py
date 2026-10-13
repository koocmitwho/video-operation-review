"""Pixel-exact metrics and bounded working-memory regression tests."""
from pathlib import Path
import sys
import tracemalloc
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vor_media import metrics


def scalar_metrics(previous, current, tile_size, threshold):
    """Independent small-image oracle, using Python integer arithmetic."""
    height, width, _ = current.shape
    values = [[max(abs(int(current[y, x, c]) - int(previous[y, x, c]))
                   for c in range(3)) for x in range(width)] for y in range(height)]
    tiles = []
    for y in range(0, height, tile_size):
        for x in range(0, width, tile_size):
            box = [x, y, min(width, x + tile_size), min(height, y + tile_size)]
            samples = [values[j][i] for j in range(y, box[3]) for i in range(x, box[2])]
            tiles.append({'box': box, 'mean_delta': sum(samples) / len(samples)})
    strongest = max(tiles, key=lambda tile: tile['mean_delta'])
    changed = sum(value >= threshold for row in values for value in row)
    return (sum(map(sum, values)) / (height * width), strongest['mean_delta'],
            changed, changed / (height * width), [strongest])


class PixelMetricsContract(unittest.TestCase):
    def test_full_resolution_working_memory_stays_below_twelve_bytes_per_pixel(self):
        # Regression: full RGB int16 temporaries consumed at least 18 bytes per
        # pixel, in addition to the two input images. No wall-clock CI threshold.
        previous = np.zeros((768, 1024, 3), dtype=np.uint8)
        current = np.full_like(previous, 255)
        already_tracing = tracemalloc.is_tracing()
        if not already_tracing:
            tracemalloc.start()
        try:
            baseline = tracemalloc.get_traced_memory()[0]
            tracemalloc.reset_peak()
            actual = metrics(previous, current, 32, 8)
            peak = tracemalloc.get_traced_memory()[1] - baseline
        finally:
            if not already_tracing:
                tracemalloc.stop()
        self.assertEqual(actual[:4], (255.0, 255.0, 768 * 1024, 1.0))
        self.assertLessEqual(peak, 12 * 768 * 1024,
                             'Full-resolution metrics exceeded its working-memory budget.')

    def test_one_pixel_confirmation_change_is_preserved_in_every_channel(self):
        previous = np.zeros((35, 37, 3), dtype=np.uint8)
        for channel in range(3):
            with self.subTest(channel=channel):
                current = previous.copy()
                current[34, 36, channel] = 8
                self.assertEqual(metrics(previous, current, 32, 8),
                                 (8 / 1295, 8 / 15, 1, 1 / 1295,
                                  [{'box': [32, 32, 37, 35], 'mean_delta': 8 / 15}]))
                self.assertEqual(metrics(current, previous, 32, 8),
                                 metrics(previous, current, 32, 8))

    def test_threshold_and_unsigned_extremes_match_hand_checked_values(self):
        previous = np.array([[[0, 255, 7], [10, 10, 10], [1, 2, 3]]], dtype=np.uint8)
        current = np.array([[[255, 0, 7], [10, 17, 10], [1, 2, 11]]], dtype=np.uint8)
        self.assertEqual(metrics(previous, current, 1, 8),
                         (90.0, 255.0, 2, 2 / 3,
                          [{'box': [0, 0, 1, 1], 'mean_delta': 255.0}]))

    def test_random_and_noncontiguous_images_match_scalar_oracle_without_mutation(self):
        rng = np.random.default_rng(61013)
        for height, width in [(1, 1), (7, 13), (35, 37)]:
            previous = rng.integers(0, 256, (height * 2, width * 2, 3), dtype=np.uint8)[::2, ::2]
            current = rng.integers(0, 256, (height * 2, width * 2, 3), dtype=np.uint8)[::2, ::2]
            snapshots = previous.copy(), current.copy()
            for tile_size in (1, 4, 32, 64):
                for threshold in (1, 8, 255):
                    with self.subTest(shape=(height, width), tile_size=tile_size, threshold=threshold):
                        self.assertEqual(metrics(previous, current, tile_size, threshold),
                                         scalar_metrics(previous, current, tile_size, threshold))
            self.assertTrue(np.array_equal(previous, snapshots[0]))
            self.assertTrue(np.array_equal(current, snapshots[1]))

    def test_exact_duplicates_keep_the_first_tile_and_zero_metrics(self):
        current = np.full((35, 37, 3), 127, dtype=np.uint8)
        self.assertEqual(metrics(current.copy(), current, 32, 8),
                         (0.0, 0.0, 0, 0.0,
                          [{'box': [0, 0, 32, 32], 'mean_delta': 0.0}]))

    def test_initial_and_changed_resolution_have_no_predecessor_metrics(self):
        current = np.zeros((3, 5, 3), dtype=np.uint8)
        self.assertEqual(metrics(None, current, 32, 8), (None, None, None, None, []))
        self.assertEqual(metrics(np.zeros((2, 5, 3), dtype=np.uint8), current, 32, 8),
                         (None, None, None, None, []))


if __name__ == '__main__':
    unittest.main()
