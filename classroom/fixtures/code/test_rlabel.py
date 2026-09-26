import unittest

from rlabel import garage_label, is_numbered


class GarageLabelTest(unittest.TestCase):
    def test_keeps_glyph(self):
        self.assertEqual(garage_label(" ЯBOT "), "ЯBOT")

    def test_keeps_casing(self):
        # ЯMAX is shown as ЯMAX; a label like "Scout .01" must not be upper-cased.
        self.assertEqual(garage_label("Scout .01"), "Scout .01")

    def test_numbered(self):
        self.assertTrue(is_numbered("ЯBOT#1"))
        self.assertFalse(is_numbered("ЯMAX"))


if __name__ == "__main__":
    unittest.main()
