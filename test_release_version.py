import unittest
from release_version import next_version,validate_new_version

class NumberingTests(unittest.TestCase):
    def test_patch_carries_without_limiting_minor(self):
        self.assertEqual(next_version('0.7.8'),'0.7.9')
        self.assertEqual(next_version('0.7.9'),'0.8.0')
        self.assertEqual(next_version('0.9.9'),'0.10.0')
        self.assertEqual(next_version('1.12.9'),'1.13.0')
    def test_new_policy_does_not_reinterpret_legacy_installations(self):
        self.assertEqual(next_version('0.6.50'),'0.7.0')
        self.assertEqual(validate_new_version('0.7.0'),'0.7.0')
        with self.assertRaises(ValueError):validate_new_version('0.7.10')
