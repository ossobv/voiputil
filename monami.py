#!/usr/bin/env python
# vim: set ts=8 sw=4 sts=4 et ai tw=79:
"""
FIXME/TODO: add usage/manual here.
.. something about being able to contact multiple asterisken at the same time
"""
import select
import socket
import sys
import time
from hashlib import md5  # for challenge auth


class TokenBufferedSocket(object):
    """
    The TokenBufferedSocket has the following properties:
    (1) It is single-threaded and therefore more suitable for calls from e.g. a
        webserver.
    (2) It splits input by tokens, but does not strip the tokens.
    (3) It does *not* split output by tokens. It sends as much as possible at
        once.
    (4) On error and/or lost connection, it attempts to deliver as much data as
        possible to both ends of the pipe. (Even if there are messages left
        without a trailing token.)
    (5) It's not supposed to be the most efficient (excess select calls when
        reading or writing large blocks of data), but it's supposed to be
        straight-forward.

    All timeouts mentioned are in seconds (floats are legal).
    """

    def __init__(self, token='\n', on_data=None):
        """
        Construct a TokenBufferedSocket. Parameter token specifies on which
        token lines should be plit. Parameter on_data is a callback which is
        called for every new chunk of data, but you can subclass this and
        override the on_data if you rather do that.
        """
        assert token
        self._token = token  # e.g. LF or CRLF
        self._on_data = on_data
        self._timeout = 0.333
        self._sock = None
        self._inbuf = ''
        self._outbuf = ''
        self._blocksize = 4096

        self._alarm_time = None

    def connect(self, host, port, connect_timeout=4):
        """
        Connect to the specified host and port.
        """
        timeout = connect_timeout or self._timeout
        self.trace('|| Connect to %s:%s (timeout=%s)\n' %
                   (host, port, timeout))
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setblocking(0)  # takes effect after connect
        self._sock.settimeout(timeout)
        # Connect can raise:
        # s.error(), s.gaierror(), s.timeout(), OverflowError
        self._sock.connect((host, port))
        # This flag states that we should shut the connection down when we're
        # done writing.
        self._shutdown_when_written = False

    def trace(self, message):
        """
        A way to debug this.
        """
        # sys.stderr.write(message)
        pass

    def alarm(self, seconds, callback):
        """
        Add callback after specified time. At the moment, setting a second
        alarm will overwrite the first.
        """
        assert seconds > 0
        self._alarm_callback = callback
        self._alarm_time = time.time() + seconds

    def loop(self, absolute_timeout=None, relative_timeout=None):
        """
        Main loop. Do all the work and exit when done.
        """
        keep_time = absolute_timeout or relative_timeout
        t0 = tn = time.time()
        while self._sock:
            if keep_time:
                tm = time.time()
                if absolute_timeout and (tm - t0) > absolute_timeout:
                    break

            did_something = self.work()
            if relative_timeout:
                if did_something:
                    tn = tm
                elif (tm - tn) > relative_timeout:
                    break
        self.abort()

    def work(self):
        """
        Check if there is work to be done and do it.

        We use select.select() here instead of poll() or newer candidates
        because we don't need anything fancy, and select is more portable.
        """
        if self._alarm_time and time.time() > self._alarm_time:
            callback = self._alarm_callback
            self._alarm_callback, self._alarm_time = None, None
            callback()

        if not self._sock:
            return None

        rlist, wlist, timeout = [self._sock], [], self._timeout
        if self._outbuf:
            wlist.append(self._sock)
        rlist, wlist, xlist = select.select(rlist, wlist, (), timeout)
        assert not xlist

        if rlist:
            self._read()
        if wlist:
            self._write()

        return bool(rlist or wlist)

    def on_data(self, data):
        """
        Called for incoming data.
        """
        if self._on_data:
            self._on_data(data)
        else:
            raise NotImplementedError('Got data but no one to handle it!',
                                      data)

    def write(self, data, shutdown_when_written=False):
        """
        Call this to add outgoing data.
        """
        self._outbuf += data  # will fail if abort is called and it's a None
        if shutdown_when_written:
            self._shutdown_when_written = True

    def abort(self, error=None):
        if self._sock:
            self._sock.close()  # python takes care of shutdown() call
            self._sock = None
            self._outbuf = None  # (ugly quickfix to refuse data in put_data)
            self._dispatch(last=True)
        if error:
            raise error

    def _dispatch(self, last=False):
        """
        If last is True, we force the last data out, even if it doesn't have
        a terminating token.
        """
        while True:
            try:
                i = self._inbuf.index(self._token)
            except ValueError:
                if last:
                    data, self._inbuf = self._inbuf, ''
                    if not data:
                        break
                else:
                    break
            else:
                i += len(self._token)
                data, self._inbuf = self._inbuf[0:i], self._inbuf[i:]
            self.on_data(data)

    def _read(self):
        try:
            ret = self._sock.recv(self._blocksize)
        except socket.error as e:
            # Connection reset by peer?
            self.trace('|| Recv yielded: %s\n' % (e,))
            self.abort(e)
        else:
            if ret == '':
                self.trace('|| Recv yielded EOF\n')
                self.abort()
            self.trace('<< %r (%d)\n' % (ret, len(ret)))
            # We could optimize things here by looking back at most
            # (len(token)-1) characters in _inbuf when looking for token. But
            # it doesn't feel worth while.
            self._inbuf += ret
            if self._token in self._inbuf:
                self._dispatch()

    def _write(self):
        while self._outbuf:
            size_to_write = min(self._blocksize, len(self._outbuf))
            bytes_to_write = self._outbuf[0:size_to_write]
            self.trace('>> %r (%d)\n' % (bytes_to_write, size_to_write))
            try:
                ret = self._sock.send(bytes_to_write)
            except socket.error as e:
                # Connection reset by peer?
                self.trace('|| Recv yielded: %s\n' % (e,))
                self.abort()  # empties _outbuf so we exit the while
            else:
                self._outbuf = self._outbuf[ret:]
                if ret < size_to_write:
                    self.trace('|| Wrote less than expected (%d)\n' % (ret,))
                    break
        # If caller has requested this to be the last write, we abort
        # immediately without waiting for any input.
        if not self._outbuf and self._shutdown_when_written:
            self.abort()


class MonAmiException(Exception):
    pass


class MonAmiActionFailed(MonAmiException):
    pass


class MonAmiConnectFailed(MonAmiException):
    """
    Raised when connect raised an error. Only raised from SequentialAmi
    __init__().
    """
    pass


# FIXME: rename to "data" or "protocol" error?
class MonAmiError(MonAmiException):
    pass


class MonAmiFinished(MonAmiException):
    """
    Raised from work() when disconnect_mode is not DIS_NEVER and we're done.

    XXX: should we inherit from EOFError or StopIteration instead?
    """
    pass


class MonAmiReset(MonAmiException):
    """
    Raised when the connection got terminated by the peer.
    """
    pass


class MonAmiTimeout(MonAmiException):
    """
    Raised from process() when we're not done, but a timeout is reached.
    """
    pass


class SequentialAmi(object):
    # Disconnect modes
    DIS_NEVER = 1        # keep the connection open
    DIS_WHEN_DONE = 2    # disconnect when all actions are done
    DIS_IMMEDIATELY = 3  # disconnect when all actions are submitted

    def __init__(self, host, port=5038, username='username', secret='secret',
                 auth='plain', keepalive=None, disconnect_mode=DIS_WHEN_DONE):
        if disconnect_mode not in (self.DIS_NEVER, self.DIS_WHEN_DONE,
                                   self.DIS_IMMEDIATELY):
            raise TypeError("invalid disconnect mode %r" % (disconnect_mode,))
        self._username = username
        self._secret = secret
        self._disconnect_mode = disconnect_mode

        # Privates
        self._sock = TokenBufferedSocket(token='\r\n', on_data=self._on_line)
        self._first = True
        self._done = False
        self._iterations = 0
        self._inbuf, self._outbuf = [], []
        self._action_id = 0
        self._action_id_prefix = '%f-' % (time.time(),)  # should be unique-ish
        self._actions = {}
        # If you're going to add events asynchronously and calling next_action
        # on them, you need to check if we're authenticated first. Otherwise
        # we'd start sending login messages out of order.
        self._is_authenticated = False

        # Load up login action
        if auth == 'md5':
            self.add_action('challenge', {
                'AuthType': 'MD5'
            }, callback=self._on_login_challenge)
        elif auth == 'plain':
            self.add_action('login', {
                # #'AuthType': clear-text
                'Username': self._username,
                'Secret': self._secret,
                # Enable events using the Events-action. You don't need this
                # unless you're listening for the FullyBooted event which is
                # sent immediately. (See _on_login_challenge() too.)
                'Events': 'off',
            }, callback=self._on_login_response)
        else:
            raise TypeError('Unknown auth type for host "%s"', auth)

        # Connect immediately
        try:
            self._sock.connect(host, port)
        except Exception as e:
            # Re-raise with the original stack frame but a slightly altered
            # exception.
            raise MonAmiConnectFailed(
                'connecting to %s: %s' % (host, e)) from e

        # Schedule a new ping.
        self._keepalive = 5  # login timeout being this + ping timeout
        self._user_keepalive = keepalive
        self._keepalive_on_pong(None, None)

    def is_authenticated(self):
        """
        Returns True if we've authenticated.

        Use this check if you're using the sequentialami in a non-sequential
        fashion: i.e. adding events before waiting for older results.

        Example usage::

            s = SequentialAmi(host)

            # Ensure that login work is completed first.
            while not s.is_authenticated():
                s.work()

            while True:
                # Asynchronous adding of requests.
                queue_id = queue_id_info_to_fetch()
                if queue_id:
                    s.add_action('QueueSummary', {'Queue': queue_id},
                                 callback=on_queue_response,
                                 stop_event='QueueSummaryComplete')
                    s.next_action()

                # Do a bit of work.
                s.work()
        """
        return self._is_authenticated

    def trace(self, message):
        """
        A way to debug this.
        """
        # sys.stderr.write(message)
        pass

    def on_dict(self, dict):
        try:
            action = self._actions[dict['ActionID']]
        except KeyError:
            self.on_unexpected(dict)
        else:
            self.on_response(dict, action[0], action[1], action[2])

    def on_response(self, dict, input, callback=None, stop_event=None):
        # print 'Response:', dict, 'to', input
        event = dict.get('Event')
        response = dict.get('Response')
        if not event and response not in ('Success', 'Follows'):
            if 'Secret' in input:
                input['Secret'] = '(hidden)'
            exception = MonAmiActionFailed(input, dict)
            self._sock.abort(exception)
            return

        if callback:
            callback(dict, input)

        if not stop_event or event == stop_event:
            self.next_action()

    def on_unexpected(self, dict):
        """
        This may be expected or unexpected, but it is not matched to a
        requested action by ActionID.
        """
        if dict.get('Event'):
            print('Got event: %s\n%s\n' % (dict['Event'],
                                           '\n'.join('  %s\t%r' % (k, v)
                                                     for k, v in dict.items()
                                                     if k != 'Event')))
        else:
            print('Unexpected:', dict)

    def add_action(self, action, parameters, callback=None, stop_event=None,
                   insertpos=None):
        """
        Add an action to fire when the previous action has completed. If you
        supply a custom callback, you don't need to call next_action(). It will
        be done for you. If you supply stop_event, a command will not be marked
        as completed until that event has been received.
        """
        self._action_id += 1
        identifier = self._action_id_prefix + str(self._action_id)
        parameters['Action'] = action
        parameters['ActionID'] = identifier

        self._actions[identifier] = (parameters, callback, stop_event)
        msg = ('\r\n'.join(['%s: %s' % (k, parameters[k]) for k in parameters])
               + '\r\n\r\n')

        if insertpos is None:
            self._outbuf.append(msg)
        else:
            self._outbuf.insert(insertpos, msg)

    def next_action(self):
        """
        Load up the next action. This is called by the default on_response()
        handler. If there are no more actions to be done, the connection is
        terminated, unless of course when disconnect_mode is never, in which
        case nothing is done.
        """
        if self._outbuf:
            data = self._outbuf.pop(0)
            self.trace('}} %r\n' % (data,))
            last_action = ((not self._outbuf) and
                           self._disconnect_mode == self.DIS_IMMEDIATELY)
            self._sock.write(data, shutdown_when_written=last_action)
            if last_action:
                self._done = True
        elif self._disconnect_mode == self.DIS_WHEN_DONE:
            assert not self._done
            self.trace('|| Shutting down because done\n')
            self._sock.abort()
            self._done = True

    def process(self, absolute_timeout=5, relative_timeout=2):
        # If disconnect_mode is not never, we expect results fairly quickly, so
        # there's a timeout.
        if self._disconnect_mode != self.DIS_NEVER:
            self._sock.loop(absolute_timeout=absolute_timeout,
                            relative_timeout=relative_timeout)
            if not self._done:
                raise MonAmiTimeout()  # XXX: add delta
        else:
            # First log in.. first then go to infinite loop mode
            # (work() takes 0.333 seconds per run if no data is received)
            for i in range(10):
                if self._sock.work() is None:
                    raise MonAmiReset('Connection broken')
            if self._first:
                raise MonAmiError('No timely welcome message')
            self._sock.loop()

    def work(self):
        # Manual work, if you're combining multiple instances
        ret = self._sock.work()
        if ret is None:
            raise MonAmiReset('Connection broken')
        self._iterations += 1
        if self._first and self._iterations == 10:
            raise MonAmiError('No timely welcome message')
        if self._done and self._disconnect_mode != self.DIS_NEVER:
            raise MonAmiFinished('Done')
        return ret

    def _on_line(self, data):
        if self._first:
            # Asterisk 1.6.2 says: Asterisk Call Manager/1.1
            # Asterisk 10.3 says: Asterisk Call Manager/1.2
            if (not data.startswith('Asterisk Call Manager/') or
                    not data.endswith('\r\n')):
                raise MonAmiError('Unexpected welcome message', data)
            self._first = False
            # Load up the login action
            self.next_action()
            return

        if data == '\r\n':
            self._on_raw_dict(self._inbuf)
            self._inbuf = []
        elif not data.endswith('\r\n'):  # apparently EOF
            if len(data):
                self._inbuf.append(self._inbuf)
            if len(self._inbuf):
                self._on_raw_dict(self._inbuf)
            self._inbuf = []
            raise MonAmiError('Got EOF from other end')
        else:
            self._inbuf.append(data)

    def _on_raw_dict(self, raw_dict):
        dict = {}
        for i, line in enumerate(raw_dict):
            if (line.endswith('--END COMMAND--\r\n') and
                    dict.get('Response') == 'Follows'):
                dict[''] = line[0:-17]  # drop '--END COMMAND--\r\n'
            else:
                key, value = line.split(':', 1)
                dict[key.strip()] = value.strip()
        self.trace('{{ %r\n' % (dict,))
        self.on_dict(dict)

    # Challenge login handling
    def _on_login_challenge(self, response, request):
        # Add a login action, and prepend it.
        self.add_action('login', {
            'AuthType': 'MD5',
            'Username': self._username,
            'Key': md5(response['Challenge'] + self._secret).hexdigest(),
            # Enable events using the Events-action. You don't need this unless
            # you're listening for the FullyBooted event which is sent
            # immediately.
            'Events': 'off',
        }, callback=self._on_login_response, insertpos=0)

    def _on_login_response(self, response, request):
        # Set flag that we're logged in.
        self._is_authenticated = True
        # Set the regular keepalive time instead of the during-login keepalive
        # time.
        self._keepalive = self._user_keepalive

    # Keepalive handling
    def _keepalive_ping(self):
        # Enqueue a ping as first next action.
        self.add_action('ping', {
        }, callback=self._keepalive_on_pong, insertpos=0)
        # Set a new alarm for it. Wait 5 seconds for the pong.
        # OBSERVE: these hardcoded 5 seconds will cause the minimum
        # ping keepalive to be at least 5, since the next alarm will
        # be scheduled first on pong_alarm.
        self._sock.alarm(5, self._keepalive_pong_alarm)
        # Force the ping to go out immediately.
        self.next_action()

    def _keepalive_on_pong(self, response, request):
        # Re-schedule the ping. Discard the _keepalive_pong_alarm.
        if self._keepalive:
            # Only if _keepalive. Now we can alter the keepalive time
            # during the running of the program.
            self._sock.alarm(self._keepalive, self._keepalive_ping)

    def _keepalive_pong_alarm(self):
        # Connection broken? Tear it down and raise an exception.
        self._sock.abort(MonAmiTimeout('Ping timeout'))


class MultiHostSequentialAmi(object):
    """
    Run multiple SequentialAmis at the same time. Note that connecting to a
    host can delay things. Also not that broken connections will slow things
    down.

    Example usage::

        s = MultiHostSequentialAmi()
        kwargs = {'username': 'username', 'secret': 'secret', 'auth': 'md5'}
        s.add_action('command', {'Command': 'module reload func_odbc'})
        s.add_action('command', {'Command': 'dialplan reload'})
        s.add_action('command', {'Command': 'sip reload'})
        s.add_connection(host='server1', **kwargs)
        s.add_connection(host='server2', **kwargs)
        s.add_connection(host='server3', **kwargs)
        errors = s.process()
        if not errors:
            print 'All went well.'
        else:
            print len(errors), 'reloads failed'
    """

    def __init__(self):
        self._amis = []
        self._actions = []
        self._errors = []

    def add_action(self, action, parameters, callback=None, stop_event=None):
        self._actions.append((action, parameters, callback, stop_event))

    def add_connection(self, **kwargs):
        try:
            s = SequentialAmi(**kwargs)
        except Exception as e:
            self._errors.append((kwargs, e))
        else:
            self._amis.append((kwargs, s))

    def process(self):
        # Enqueue the actions
        for kwargs, ami in self._amis:
            for action, parameters, callback, stop_event in self._actions:
                ami.add_action(action, parameters, callback, stop_event)

        # Loop until all amis are complete or have errors
        while self._amis:
            for kwargs, ami in self._amis:
                try:
                    ami.work()
                except MonAmiFinished:
                    self._amis.pop(self._amis.index((kwargs, ami)))  # drop it
                except Exception as e:
                    self._errors.append((kwargs, e))
                    self._amis.pop(self._amis.index((kwargs, ami)))  # drop it

        return self._errors


def main():
    # s = TokenBufferedSocket()
    # s.connect('server1', 5038)
    # s.loop(relative_timeout=3, absolute_timeout=2)

    command, host, username, secret = sys.argv[1:5]

    if command == 'reload':
        s = SequentialAmi(host, username=username, secret=secret, auth='md5')
        s.add_action('command', {'Command': 'dialplan reload'})
        s.add_action('command', {'Command': 'module reload func_odbc'})
        s.add_action('command', {'Command': 'sip reload'})
        s.process()

    elif command == 'listen':
        s = SequentialAmi(host, username=username, secret=secret, auth='md5',
                          keepalive=60,
                          disconnect_mode=SequentialAmi.DIS_NEVER)
        # If you have read=all perms in your manager.conf, you'll get flooded
        # with events now :)
        s.add_action('events', {'EventMask': 'on'})
        s.process()

    else:
        # s.add_action('originate', {
        #     'Action': 'Originate',
        #     'Channel': channel,
        #     'Context': context,
        #     'Exten': exten,
        #     'Priority': 1,
        # }, on_result)
        raise ValueError('Use the source, Luke')


if __name__ == '__main__':
    main()
