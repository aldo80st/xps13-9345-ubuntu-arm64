"""Tests for the privacy-preserving GPU UI acceptance probe."""
import unittest
from verify_resources_ui import classify_gpu_cells


class RenderedGpuCellsTests(unittest.TestCase):
    def test_unknown_zero_and_positive_are_distinct(self):
        self.assertEqual(
            classify_gpu_cells(["GPU: N/A", "GPU: 0.0 %", "GPU: 3.8 %"]),
            (1, 1, 1),
        )

    def test_does_not_mistake_process_id_cpu_or_unrelated_values(self):
        self.assertEqual(
            classify_gpu_cells(["ID del Proceso: 123", "Procesador: 5 %", "GPU: -1.0 %"]),
            (0, 0, 0),
        )

    def test_localized_decimal_and_extra_whitespace(self):
        self.assertEqual(
            classify_gpu_cells([" GPU: 0,3 % ", "GPU: 0,0 %", "GPU: N/A"]),
            (1, 1, 1),
        )


if __name__ == "__main__":
    unittest.main()
