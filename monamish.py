#!/usr/bin/env python
# vim: set ts=8 sw=4 sts=4 et ai tw=79:
'''
FIXME/XXX: Shortcuts for monami. Document me.
'''
from collections import defaultdict
from urlparse import urlparse

# Local friend package.
from monami import MultiHostSequentialAmi, SequentialAmi


def amiaddr_to_dict(address):
    """
    Pass an address to an AMI host in the form myuser:mypass@myhost. Returns a
    dictionary with binary strings and an int:
    {'host': 'hostname, 'port': 5038, 'username': 'myuser', 'secret': 'mypass'}
    """
    # Cheat, and prepend http:// so we can use urlparse
    address = address.decode('utf-8')
    info = urlparse('http://%s' % (address,))
    ret = {
        'host': info.hostname or 'localhost',
        'port': info.port or 5038,
        'username': info.username or 'username',
        'secret': info.password or 'secret'
    }
    return ret


def channel_originate(ami_kwarg, channel, params=None):
    """
    See 'manager show command Originate'. Only the "Channel" param is required,
    but you'll usually want Context, Exten and Priority as well.

    It exits the AMI immediately without waiting for the call status. Returns
    nothing. If it fails, you'll get an exception in your face.
    """
    if 'Channel' in params:
        raise TypeError('missing "Channel" in params %r' % (params,))
    params['Channel'] = channel

    s = SequentialAmi(disconnect_mode=SequentialAmi.DIS_IMMEDIATELY,
                     **ami_kwarg)
    s.add_action('Originate', params)
    # This can raise a bunchof socket.* errors, or a bunch of MonAmiExceptions.
    # If it doesn't, the call probably went ok. (But due to the
    # DIS_IMMEDIATELY flag, we don't really know for sure.)
    s.process()


def reload_asterisken(ami_kwargs):
    """
    Reload the asterisk config (extensions, func_odbc, sip). Returns the
    failure count.
    """
    s = MultiHostSequentialAmi()
    s.add_action('Command', {'Command': 'dialplan reload'})
    s.add_action('Command', {'Command': 'module reload func_odbc'})
    s.add_action('Command', {'Command': 'sip reload'})
    for ami_kwarg in ami_kwargs:
        s.add_connection(**ami_kwarg)

    errors = s.process()
    return errors  # a list of error tuples [(ami_kwarg, error), ...]


def _fetch_eventinfo(ami_kwargs, command, params, end_event):
    """
    Shortcut for getting a single event between a start-event and end-event.
    """
    data = []

    def callback(dict, input):
        data.append((dict, input))

    s = MultiHostSequentialAmi()
    s.add_action('Events', {'EventMask': 'on'})
    s.add_action(command, params, callback, end_event)
    for ami_kwarg in ami_kwargs:
        s.add_connection(**ami_kwarg)

    errors = s.process()
    success_count = len(ami_kwargs) - len(errors)

    if not success_count:
        raise ValueError('Command failed on all asterisken')

    return data


def fetch_queuestatus(ami_kwargs, queue_id):
    assert queue_id.isdigit()
    data = _fetch_eventinfo(ami_kwargs, 'QueueStatus', {'Queue': queue_id},
                            'QueueStatusComplete')
    return translate_queuestatus(data)


def fetch_queuesummary(ami_kwargs, queue_id):
    assert queue_id.isdigit()
    data = _fetch_eventinfo(ami_kwargs, 'QueueSummary', {'Queue': queue_id},
                            'QueueSummaryComplete')
    return translate_queuesummary(data)


def translate_queuestatus(queue_data):
    # Sort the data by action_id and strip all info that we do not need.
    by_action_id = defaultdict(list)
    for output, input in queue_data:
        # We completely ignore the input (the original input parameters).
        action_id = output['ActionID']
        if output.get('Event') in (None, 'QueueStatusComplete'):
            pass
        else:
            by_action_id[action_id].append(output)

    # Run over them again, and try to filter out the info that we only do need.
    values = []
    for action_id, output in by_action_id.items():
        for row in output:
            if row.get('Event') == 'QueueParams':
                values.append({
                    'abandoned': int(row.get('Abandoned', 0)),
                    'calls': int(row.get('Calls', 0)),
                    'holdtime': int(row.get('Holdtime')),
                    'talktime': int(row.get('TalkTime', 0)),
                    'completed': int(row.get('Completed', 0)),
                })

    # Combine the values and hope that they're somewhat meaningful. And use an
    # initial dictionary, so we always get some values.
    ret = {'abandoned': 0, 'calls': 0, 'holdtime': 0, 'talktime': 0,
           'completed': 0}
    for value_dict in values:
        for key, value in value_dict.items():
            ret[key] += value

    return ret


def translate_queuesummary(queue_data):
    # Sort the data by action_id and strip all info that we do not need.
    by_action_id = defaultdict(list)
    for output, input in queue_data:
        # We completely ignore the input (the original input parameters).
        action_id = output['ActionID']
        if output.get('Event') in (None, 'QueueSummaryComplete'):
            pass
        else:
            by_action_id[action_id].append(output)

    # Run over them again, and try to filter out the info that we only do need.
    values = []
    for action_id, output in by_action_id.items():
        for row in output:
            if row.get('Event') == 'QueueSummary':
                values.append({
                    'average_talktime': int(row.get('TalkTime', 0)),
                    'current_holdtime': int(row.get('LongestHoldTime', 0)),
                    'average_holdtime': int(row.get('HoldTime', 0)),
                    'queued_callers': int(row.get('Callers', 0)),
                })

    # Combine the values and hope that they're somewhat meaningful. And use an
    # initial dictionary, so we always get some values.
    ret = {'average_talktime': 0, 'current_holdtime': 0, 'average_holdtime': 0,
           'queued_callers': 0}
    for value_dict in values:
        for key, value in value_dict.items():
            ret[key] += value

    return ret


if __name__ == '__main__':
    import unittest
    import sys

    class TestCase(unittest.TestCase):
        def test_amiaddr_to_dict_default(self):
            self.assertEquals(
                amiaddr_to_dict(''),
                {'host': 'localhost', 'port': 5038,
                 'username': 'username', 'secret': 'secret'}
            )

        def test_amiaddr_to_dict_partial(self):
            self.assertEquals(
                amiaddr_to_dict('abc@ghi'),
                {'host': 'ghi', 'port': 5038,
                 'username': 'abc', 'secret': 'secret'}
            )

        def test_amiaddr_to_dict_full(self):
            self.assertEquals(
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
                  'ActionID': '1333717971.398761-3', 'Holdtime': '0', 'Event':
                  'QueueParams', 'Abandoned': '1'}, {'Queue': '22', 'Action':
                  'QueueStatus', 'ActionID': '1333717971.398761-3'}),
                ({'Status': '1', 'Penalty': '0', 'Name':
                  'Local/ID22@route_phoneaccount', 'Queue': '22',
                  'Membership': 'static', 'Location':
                  'Local/ID22@route_phoneaccount', 'LastCall': '0',
                  'Paused': '0', 'Event': 'QueueMember', 'CallsTaken': '0',
                  'ActionID': '1333717971.398761-3'}, {'Queue':
                  '22', 'Action': 'QueueStatus', 'ActionID':
                  '1333717971.398761-3'}),
                ({'Status': '1', 'Penalty': '0', 'Name':
                  'Local/ID22@route_phoneaccount', 'Queue': '22',
                  'Membership': 'static', 'Location':
                  'Local/ID22@route_phoneaccount', 'LastCall': '0',
                  'Paused': '0', 'Event': 'QueueMember', 'CallsTaken': '0',
                  'ActionID': '1333717971.396309-3'}, {'Queue': '22', 'Action':
                  'QueueStatus', 'ActionID': '1333717971.398761-3'}),
                ({'Status': '1', 'Penalty': '0', 'Name':
                  'Local/ID12@route_phoneaccount', 'Queue': '22',
                  'Membership': 'static', 'Location':
                  'Local/ID12@route_phoneaccount', 'LastCall': '0',
                  'Paused': '0', 'Event': 'QueueMember', 'CallsTaken': '0',
                  'ActionID': '1333717971.396309-3'}, {'Queue': '22', 'Action':
                  'QueueStatus', 'ActionID': '1333717971.398761-3'}),
                ({'Event': 'QueueStatusComplete', 'ActionID':
                  '1333717971.396309-3'}, {'Queue': '22', 'Action':
                  'QueueStatus', 'ActionID': '1333717971.398761-3'}),
                ({'Status': '1', 'Penalty': '0', 'Name':
                  'Local/ID12@route_phoneaccount', 'Queue': '22',
                  'Membership': 'static', 'Location':
                  'Local/ID12@route_phoneaccount', 'LastCall': '0',
                  'Paused': '0', 'Event': 'QueueMember', 'CallsTaken': '0',
                  'ActionID': '1333717971.398761-3'}, {'Queue': '22', 'Action':
                  'QueueStatus', 'ActionID': '1333717971.398761-3'}),
                ({'Event': 'QueueStatusComplete', 'ActionID':
                  '1333717971.398761-3'}, {'Queue': '22', 'Action':
                  'QueueStatus', 'ActionID': '1333717971.398761-3'}),
            ]
            output = translate_queuestatus(queue_data)
            expected = {'completed': 32, 'holdtime': 33, 'abandoned': 35,
                        'calls': 31, 'talktime': 30}
            self.assertEquals(output, expected)

        def test_translate_queuesummary(self):
            queue_data = [
                ({'Message': 'Queue summary will follow', 'Response':
                  'Success', 'ActionID': '1334760883.002422-3'}, {'Queue':
                  '22', 'Action': 'QueueSummary', 'ActionID':
                  '1334760883.002422-3'}),
                ({'Available': '2', 'LoggedIn': '5', 'TalkTime': '8',
                  'LongestHoldTime': '55', 'Queue': '22', 'Callers': '2',
                  'ActionID': '1334760883.002422-3', 'HoldTime': '33', 'Event':
                  'QueueSummary'}, {'Queue': '22', 'Action': 'QueueSummary',
                  'ActionID': '1334760883.002422-3'}),
                ({'Event': 'QueueSummaryComplete', 'ActionID':
                  '1334760883.002422-3'}, {'Queue': '22', 'Action':
                  'QueueSummary', 'ActionID': '1334760883.002422-3'}),
                ({'Message': 'Queue summary will follow', 'Response':
                  'Success', 'ActionID': '1334760883.002422-4'}, {'Queue':
                  '22', 'Action': 'QueueSummary', 'ActionID':
                  '1334760883.002422-4'}),
                ({'Available': '2', 'LoggedIn': '5', 'TalkTime': '8',
                  'LongestHoldTime': '0', 'Queue': '22', 'Callers': '0',
                  'ActionID': '1334760883.002422-4', 'HoldTime': '0', 'Event':
                  'QueueSummary'}, {'Queue': '22', 'Action': 'QueueSummary',
                  'ActionID': '1334760883.002422-4'}),
                ({'Event': 'QueueSummaryComplete', 'ActionID':
                  '1334760883.002422-4'}, {'Queue': '22', 'Action':
                  'QueueSummary', 'ActionID': '1334760883.002422-4'}),
            ]
            output = translate_queuesummary(queue_data)
            expected = {'average_holdtime': 33, 'average_talktime': 16,
                        'current_holdtime': 55, 'queued_callers': 2}
            self.assertEquals(output, expected)

    # What did the user want?
    command, args = ''.join(sys.argv[1:2]), sys.argv[2:]
    if command == 'TestCase':
        unittest.main()
        assert False, 'we do not get here'
    elif command == 'originate':
        (channel, context, exten), args = args[0:3], args[3:]
    elif command == 'reload':
        pass
    elif command == 'queuestatus' or command == 'queuesummary':
        queue_id = args.pop(0)
    else:
        raise ValueError('Use the source, Luke')

    # Compile a list of host/user/pass arguments
    ami_kwargs = [amiaddr_to_dict(i) for i in args]

    # Set up a call
    if command == 'originate':
        assert len(ami_kwargs) == 1, 'Setting up multiple calls?'
        channel_originate(ami_kwargs[0], channel, {'Context': context,
                          'Exten': exten, 'Priority': 1})
        print 'Originate probably succeeded.'

    # Reload the config
    elif command == 'reload':
        errors = reload_asterisken(ami_kwargs)
        success_count = len(ami_kwargs) - len(errors)
        if not errors:
            print 'Reload successful on all %d asterisken.' % (success_count,)
        else:
            print ('Reload successful on %d (out of %d) asterisken.' %
                   (success_count, len(ami_kwargs)))
            for error in errors:
                print >>sys.stderr, '%s: %s' % (error[0]['host'], error[1])
            sys.exit(1)

    # Info about a queue
    elif command == 'queuesummary':
        print fetch_queuesummary(ami_kwargs, queue_id)

    # Not so useful
    elif command == 'queuestatus':
        print fetch_queuestatus(ami_kwargs, queue_id)
