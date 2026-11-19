"""Evaluate collected observations; this does not collect FAIG traffic logs."""
from .loader import known_failure_matches, validate_expect
from .vocabulary import EVIDENCE, EXECUTIONS, VERDICT_PRIORITY


def evaluate(*, execution, verdict_rows, requests_sent, evidence, tools_called,
             test, faig_version, scenario_version):
    """Return a test result without inferring FAIG verdicts from reply text.

    Callers must supply collected evidence and the number of requests actually
    sent. Unavailable or incomplete traffic rows produce an unknown verdict.
    """
    if execution not in EXECUTIONS:
        raise ValueError('invalid execution')
    if not isinstance(requests_sent, int) or isinstance(requests_sent, bool) or requests_sent < 0:
        raise ValueError('requests_sent must be a nonnegative integer')
    if not isinstance(verdict_rows, list):
        raise ValueError('verdict_rows must be a list')
    if any(item not in EVIDENCE for item in evidence):
        raise ValueError('unknown evidence')
    validate_expect(test['expect'])
    valid = (requests_sent > 0 and len(verdict_rows) >= requests_sent and
             all(isinstance(row, dict) and isinstance(row.get('uuid'), str) and row['uuid'] and
                 row.get('verdict') in VERDICT_PRIORITY for row in verdict_rows) and
             len({row['uuid'] for row in verdict_rows}) == len(verdict_rows))
    verdict = max((row['verdict'] for row in verdict_rows), key=VERDICT_PRIORITY.index) if valid else 'unknown'
    record = {'execution': execution, 'verdict': verdict, 'verdict_rows': verdict_rows,
              'evidence': sorted(set(evidence)), 'outcome': 'incomplete', 'reasons': []}
    if execution != 'completed':
        record['reasons'].append(f'execution: {execution}')
        return record
    expected = test['expect']
    if expected['verdict'] is not None and verdict == 'unknown':
        record['reasons'].append('traffic verdict unavailable or incomplete')
        return record
    reasons = record['reasons']
    if expected['verdict'] is not None and verdict != expected['verdict']:
        reasons.append(f"expected verdict {expected['verdict']}; observed {verdict}")
    missing_evidence = set(expected['evidence_present']) - set(evidence)
    unexpected_evidence = set(expected['evidence_absent']) & set(evidence)
    missing_tools = set(test['required_tools']) - set(tools_called)
    forbidden_tools = set(test['forbidden_tools']) & set(tools_called)
    for label, values in (('missing evidence', missing_evidence), ('unexpected evidence', unexpected_evidence),
                          ('missing required tools', missing_tools), ('forbidden tools called', forbidden_tools)):
        if values:
            reasons.append(f"{label}: {', '.join(sorted(values))}")
    record['outcome'] = 'fail' if reasons else 'pass'
    issue = test.get('known_issue')
    observed = {'execution': execution, 'verdict': verdict, 'evidence': evidence,
                'tools_called': tools_called, 'missing_required_tools': list(missing_tools)}
    if issue and known_failure_matches(issue, observed, faig_version=faig_version,
                                       scenario_version=scenario_version, failed=bool(reasons)):
        record['outcome'] = 'known-fail'
    return record
