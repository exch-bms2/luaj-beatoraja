import unittest
from audit_results import digest, normalize

class AuditResultsTest(unittest.TestCase):
    def test_only_diagnostic_identities_are_removed(self):
        self.assertEqual(normalize('table: abc123 thread: aabbcc org.luaj.vm2.luajc.JavaLoader @cc0011'),
                         normalize('table: 123abc thread: cc1122 org.luaj.vm2.luajc.JavaLoader @dd0022'))
        self.assertIn('@dead', normalize('function: @dead:1-2'))

    def test_numeric_results_are_not_removed(self):
        self.assertNotEqual(digest('number:31'), digest('number:32'))
        self.assertNotEqual(digest('finite=true,text=Infinity'), digest('finite=true,text=1e40'))

    def test_distinct_invalid_utf8_bytes_remain_distinct(self):
        self.assertNotEqual(digest(b'\xff'.decode('utf-8','surrogateescape')),
                            digest(b'\xfe'.decode('utf-8','surrogateescape')))

if __name__ == '__main__': unittest.main()
