"""Agent behaviour with bonus tools: retry budget, Retry-After, context compaction."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent
from agent import run_agent
from bonus.tools import BonusTools


def call(call_id, name, args):
    raw = json.dumps(args)
    msg = {'role': 'assistant', 'content': None,
           'tool_calls': [{'id': call_id, 'type': 'function', 'function': {'name': name, 'arguments': raw}}]}
    return {'message': msg, 'calls': [{'id': call_id, 'name': name, 'arguments': raw}], 'finish': 'tool_calls', 'usage': {}}


def final(answer='Đã kiểm tra'):
    return {'message': {'role': 'assistant', 'content': answer}, 'calls': [], 'finish': 'stop', 'usage': {}}


class Scripted:
    def __init__(self, responses):
        self.responses, self.histories = iter(responses), []

    def complete(self, messages, schemas):
        self.histories.append(list(messages))
        return next(self.responses)


def tool_events(result, name):
    return [t for t in result['trace'] if t.get('event') == 'tool' and t.get('name') == name]


class BonusAgentBehaviourTests(unittest.TestCase):
    def test_persistent_429_is_capped_at_three_real_calls(self):
        p = Scripted([call(f'c{i}', 'get_vercel_status', {}) for i in range(5)] + [final()])
        result = run_agent('Kiểm tra Vercel', p, BonusTools(scenario='rate_limit_always'), max_steps=8)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(tool_events(result, 'get_vercel_status')), 3)
        blocked = json.loads(p.histories[4][-1]['content'])
        self.assertEqual(blocked['error'], 'RETRY_LIMIT_REACHED')
        self.assertTrue(any(t['event'] == 'retry_blocked' for t in result['trace']))

    def test_long_retry_after_stops_retrying(self):
        class LiveLike:
            def execute(self, name, args):
                return {'ok': False, 'error': 'RATE_LIMITED', 'http_status': 429, 'retry_after': '120'}
        p = Scripted([call('a', 'get_npm_status', {}), call('b', 'get_npm_status', {}), final()])
        with patch.object(agent.time, 'sleep') as sleep:
            result = run_agent('npm?', p, LiveLike(), max_steps=5)
        sleep.assert_not_called()
        self.assertEqual(len(tool_events(result, 'get_npm_status')), 1)
        self.assertEqual(json.loads(p.histories[2][-1]['content'])['error'], 'RETRY_LIMIT_REACHED')

    def test_short_retry_after_waits_before_next_call(self):
        class LiveLike:
            def __init__(self):
                self.n = 0

            def execute(self, name, args):
                self.n += 1
                if self.n == 1:
                    return {'ok': False, 'error': 'RATE_LIMITED', 'http_status': 429, 'retry_after': '2'}
                return {'provider': 'npm'}
        p = Scripted([call('a', 'get_npm_status', {}), call('b', 'get_npm_status', {}), final()])
        with patch.object(agent.time, 'sleep') as sleep:
            run_agent('npm?', p, LiveLike(), max_steps=5)
        sleep.assert_called_once_with(2.0)

    def test_noisy_lists_are_compacted_for_model_but_kept_in_trace(self):
        p = Scripted([call('a', 'get_vercel_status', {}), final()])
        result = run_agent('Vercel?', p, BonusTools(scenario='noisy'), max_steps=3)
        sent = json.loads(p.histories[1][-1]['content'])
        self.assertLess(len(sent['distractors']), 160)
        self.assertIn('distractors_omitted', sent)
        self.assertEqual(len(tool_events(result, 'get_vercel_status')[0]['result']['distractors']), 160)

    def test_bonus_prompt_adds_rules(self):
        p = Scripted([final()])
        run_agent('Kiểm tra', p, BonusTools(), max_steps=2)
        system = p.histories[0][0]['content']
        self.assertIn('DigitalOcean', system)
        self.assertIn('RATE_LIMITED', system)
        self.assertIn('next_offset', system)


if __name__ == '__main__':
    unittest.main()
