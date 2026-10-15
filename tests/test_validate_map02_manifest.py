"""Synthetic tests for the map-02 audit manifest validator."""
import copy
import unittest
from tools.validate_map02_manifest import validate

GOOD = {
    "map": 2,
    "records": [
        {"gfx": 241, "tile": 243, "face": 0, "land_dt": 641,
         "uv": [0, 0], "size": [0, 0], "palette": 0, "source_map": 2},
        {"gfx": 243, "tile": 319, "face": 0, "land_dt": 643,
         "uv": [0, 0], "size": [0, 0], "palette": 0, "source_map": 2}
    ],
}


class Map02ValidatorTests(unittest.TestCase):
    def test_expected_observations(self):
        self.assertEqual(validate(GOOD), [])

    def test_wrong_palette(self):
        data = copy.deepcopy(GOOD)
        data["records"][0]["palette"] = 35
        self.assertTrue(validate(data))

    def test_wrong_source_map(self):
        data = copy.deepcopy(GOOD)
        data["records"][0]["source_map"] = 11
        self.assertTrue(validate(data))

    def test_missing_and_duplicate(self):
        data = copy.deepcopy(GOOD)
        data["records"] = [data["records"][0], data["records"][0]]
        self.assertTrue(validate(data))

    def test_reject_boolean_integer_impostor(self):
        data = copy.deepcopy(GOOD)
        data["records"][0]["palette"] = False
        self.assertTrue(validate(data))


if __name__ == "__main__":
    unittest.main()
