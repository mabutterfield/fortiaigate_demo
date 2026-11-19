"""Versioned IDs and labels for scenario test results (FAIG 8.0.2 lab)."""

ACTIONS = {'alert': 'Alert', 'redact': 'Redact', 'block': 'Block'}
EXECUTIONS = {'completed': 'Completed', 'error': 'Error', 'timeout': 'Timed out'}
VERDICTS = {'log': 'Log', 'alert': 'Alert', 'redact': 'Redact', 'block': 'Block', 'unknown': 'Unknown'}
EVIDENCE = {
    'sensitive-data-in-tool-result': 'Sensitive data returned by a tool',
    'sensitive-data-in-reply': 'Sensitive data in the reply',
    'redaction-marker-in-reply': 'Redaction visible in the reply',
    'block-message-in-reply': 'Block message shown',
    'attack-tool-called': 'Attack tool was called',
}
OUTCOMES = {'pass': 'PASS', 'fail': 'FAIL', 'known-fail': 'KNOWN FAIL', 'incomplete': 'INCOMPLETE'}
VERDICT_PRIORITY = ('log', 'alert', 'redact', 'block')
RETIRED = {
    'deny': 'block',
    'sensitive-tool-result': 'sensitive-data-in-tool-result',
    'sensitive-output': 'sensitive-data-in-reply',
    'tool-pivot': 'attack-tool-called',
    'expected_result': 'expect',
    'expected_log_verdict': 'expect.verdict',
}
