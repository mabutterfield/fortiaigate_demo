import unittest
from functional_test.catalog_logs import match_rows

MARKER = '[faig-test-' + 'a' * 32 + ']'


class CatalogLogTests(unittest.TestCase):
    def test_only_verified_matching_detail_is_returned(self):
        rows = [dict(uuid='one', keyAlias='key', timeStamp=10),
                dict(uuid='two', keyAlias='key', timeStamp=10),
                dict(uuid='three', keyAlias='other', timeStamp=10)]
        details = {'one': dict(uuid='one', keyAlias='key', verdictLabel='Block', prompt={'original': 'Hi ' + MARKER}),
                   'two': dict(uuid='two', keyAlias='key', verdictLabel='Log', prompt={'original': 'other prompt'})}
        self.assertEqual(match_rows(rows, key_name='key', since_ms=9, marker=MARKER, fetch_detail=details.__getitem__),
                         [{'uuid': 'one', 'verdict': 'block'}])

    def test_fail_closed_on_invalid_detail_and_errors(self):
        row = dict(uuid='one', keyAlias='key', timeStamp=10)
        for detail in [dict(uuid='different', keyAlias='key', verdictLabel='Log', prompt={'original': MARKER}),
                       dict(uuid='one', keyAlias='other', verdictLabel='Log', prompt={'original': MARKER}),
                       dict(uuid='one', keyAlias='key', verdictLabel='mystery', prompt={'original': MARKER})]:
            self.assertEqual(match_rows([row], key_name='key', since_ms=9, marker=MARKER, fetch_detail=lambda _: detail), [])
        self.assertEqual(match_rows([row], key_name='key', since_ms=9, marker=MARKER, fetch_detail={ }.__getitem__), [])
        with self.assertRaises(ValueError):
            match_rows([row], key_name='key', since_ms=9, marker='', fetch_detail=lambda _: {})


if __name__ == '__main__':
    unittest.main()
