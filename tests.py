# vim: set ts=8 sw=4 sts=4 et ai tw=79:
import unittest

from monamish import (
    amiaddr_to_dict, translate_queuestatus, translate_queuesummary)


class TestCase(unittest.TestCase):
    def test_amiaddr_to_dict_default(self):
        self.assertEqual(
            amiaddr_to_dict(''),
            {'host': 'localhost', 'port': 5038,
             'username': 'username', 'secret': 'secret'}
        )

    def test_amiaddr_to_dict_partial(self):
        self.assertEqual(
            amiaddr_to_dict('abc@ghi'),
            {'host': 'ghi', 'port': 5038,
             'username': 'abc', 'secret': 'secret'}
        )

    def test_amiaddr_to_dict_full(self):
        self.assertEqual(
            amiaddr_to_dict('abc:def@ghi:123'),
            {'host': 'ghi', 'port': 123,
             'username': 'abc', 'secret': 'def'}
        )

    def test_translate_queuestatus(self):
        queue_data = [
            ({'Message': 'Queue status will follow', 'Response':
             'Success', 'ActionID': '1333717971.396309-3'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'ServicelevelPerf': '0.0', 'TalkTime': '30', 'Calls': '31',
              'Max': '12', 'Completed': '32', 'ServiceLevel': '0',
              'Strategy': 'random', 'Queue': '22', 'Weight': '0',
              'ActionID': '1333717971.396309-3', 'Holdtime': '33',
              'Event': 'QueueParams', 'Abandoned': '34'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'Message': 'Queue status will follow', 'Response': 'Success',
             'ActionID': '1333717971.398761-3'}, {'Queue': '22', 'Action':
             'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'ServicelevelPerf': '0.0', 'TalkTime': '0', 'Calls': '0',
              'Max': '12', 'Completed': '0', 'ServiceLevel': '0',
              'Strategy': 'random', 'Queue': '22', 'Weight': '0',
              'ActionID': '1333717971.398761-3', 'Holdtime': '0',
              'Event': 'QueueParams', 'Abandoned': '1'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'Status': '1', 'Penalty': '0', 'Name':
              'Local/ID22@route_phoneaccount', 'Queue': '22',
              'Membership': 'static', 'Location':
              'Local/ID22@route_phoneaccount', 'LastCall': '0',
              'Paused': '0', 'Event': 'QueueMember', 'CallsTaken': '0',
              'ActionID': '1333717971.398761-3'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'Status': '1', 'Penalty': '0', 'Name':
              'Local/ID22@route_phoneaccount', 'Queue': '22',
              'Membership': 'static', 'Location':
              'Local/ID22@route_phoneaccount', 'LastCall': '0',
              'Paused': '0', 'Event': 'QueueMember', 'CallsTaken': '0',
              'ActionID': '1333717971.396309-3'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'Status': '1', 'Penalty': '0', 'Name':
              'Local/ID12@route_phoneaccount', 'Queue': '22',
              'Membership': 'static', 'Location':
              'Local/ID12@route_phoneaccount', 'LastCall': '0',
              'Paused': '0', 'Event': 'QueueMember', 'CallsTaken': '0',
              'ActionID': '1333717971.396309-3'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'Event': 'QueueStatusComplete', 'ActionID':
              '1333717971.396309-3'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'Status': '1', 'Penalty': '0', 'Name':
              'Local/ID12@route_phoneaccount', 'Queue': '22',
              'Membership': 'static', 'Location':
              'Local/ID12@route_phoneaccount', 'LastCall': '0',
              'Paused': '0', 'Event': 'QueueMember', 'CallsTaken': '0',
              'ActionID': '1333717971.398761-3'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ({'Event': 'QueueStatusComplete', 'ActionID':
              '1333717971.398761-3'}, {'Queue': '22',
             'Action': 'QueueStatus', 'ActionID': '1333717971.398761-3'}),
        ]
        output = translate_queuestatus(queue_data)
        expected = {'completed': 32, 'holdtime': 33, 'abandoned': 35,
                    'calls': 31, 'talktime': 30}
        self.assertEqual(output, expected)

    def test_translate_queuesummary(self):
        queue_data = [
            ({'Message': 'Queue summary will follow', 'Response':
              'Success', 'ActionID': '1334760883.002422-3'},
             {'Queue': '22', 'Action': 'QueueSummary', 'ActionID':
              '1334760883.002422-3'}),
            ({'Available': '2', 'LoggedIn': '5', 'TalkTime': '8',
              'LongestHoldTime': '55', 'Queue': '22', 'Callers': '2',
              'ActionID': '1334760883.002422-3', 'HoldTime': '33', 'Event':
              'QueueSummary'}, {'Queue': '22', 'Action': 'QueueSummary',
             'ActionID': '1334760883.002422-3'}),
            ({'Event': 'QueueSummaryComplete', 'ActionID':
              '1334760883.002422-3'}, {'Queue': '22',
             'Action': 'QueueSummary', 'ActionID': '1334760883.002422-3'}),
            ({'Message': 'Queue summary will follow', 'Response':
              'Success', 'ActionID': '1334760883.002422-4'},
             {'Queue': '22', 'Action': 'QueueSummary',
              'ActionID': '1334760883.002422-4'}),
            ({'Available': '2', 'LoggedIn': '5', 'TalkTime': '8',
              'LongestHoldTime': '0', 'Queue': '22', 'Callers': '0',
              'ActionID': '1334760883.002422-4', 'HoldTime': '0', 'Event':
              'QueueSummary'}, {'Queue': '22', 'Action': 'QueueSummary',
             'ActionID': '1334760883.002422-4'}),
            ({'Event': 'QueueSummaryComplete', 'ActionID':
              '1334760883.002422-4'}, {'Queue': '22',
             'Action': 'QueueSummary', 'ActionID': '1334760883.002422-4'}),
        ]
        output = translate_queuesummary(queue_data)
        expected = {'average_holdtime': 33, 'average_talktime': 16,
                    'current_holdtime': 55, 'queued_callers': 2}
        self.assertEqual(output, expected)
