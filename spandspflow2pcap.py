#!/usr/bin/env python
# vim: set ts=8 sw=4 sts=4 et ai tw=79:
'''
Usage: ./spandspflow2pcap.py SPANDSP_LOG SENDFAX_PCAP

Takes a log from spandsp (e.g. the debug fax.log from your Asterisk), extract
the "received" data and put it in a pcap file.

Input data should look something like this:
[2013-08-07 15:17:34] FAX[23479] res_fax.c: FLOW T.38 Rx     5: IFP c0 01 ...

Output data will look like a valid pcap file ;-)

This allows you to reconstruct sent faxes into replayable pcaps. Replaying is
expected to be done by: sipp(1) with sendfax.xml:
- https://code.osso.nl/projects/sipp/browser/
- https://code.osso.nl/projects/sipp/browser/scenario/sendfax.xml

Author: Walter Doekes, OSSO B.V. (2013)
License: Public Domain
'''
from base64 import b16decode
from datetime import datetime, timedelta
from re import search
from time import mktime
from struct import pack
import sys


def n2b(text):
    return b16decode(text.replace(' ', '').replace('\n', '').upper())


class FaxPcap(object):
    PCAP_PREAMBLE = n2b('d4 c3 b2 a1 02 00 04 00'
                        '00 00 00 00 00 00 00 00'
                        'ff ff 00 00 71 00 00 00')

    def __init__(self, outfile):
        self.outfile = outfile
        self.date = None
        self.dateoff = timedelta(seconds=0)
        self.seqno = 0
        self.udpseqno = 128
        self.prev_data = n2b('0000 0000')  # sequence 0, no data

        # Only do this if at pos 0?
        self.outfile.write(self.PCAP_PREAMBLE)

    def data2packet(self, date, udpseqno, seqno, data, prev_data):
        kwargs = {
            'sum16': '\x00\x00',  # checksum is irrelevant for sipp sending
            'udpseqno': pack('>H', udpseqno),
            'sourceip': '\x01\x01\x01\x01',     # 1.1.1.1
            'sourceport': '\x00\x01',           # 1
            'destip': '\x02\x02\x02\x02',       # 2.2.2.2
            'destport': '\x00\x02',             # 2
        }

        data = '%s%s' % (pack('>H', seqno), data)
        new_prev = data
        data += prev_data

        kwargs['data'] = data
        kwargs['lenb16'] = pack('>H', len(kwargs['data']) + 8)
        udp = '%(sourceport)s%(destport)s%(lenb16)s%(sum16)s%(data)s' % kwargs

        kwargs['data'] = udp
        kwargs['lenb16'] = pack('>H', len(kwargs['data']) + 20)
        ip = ('\x45\xb8%(lenb16)s%(udpseqno)s\x00\x00\xf9\x11%(sum16)s'
              '%(sourceip)s%(destip)s%(data)s') % kwargs

        kwargs['data'] = ip
        frame = ('\x00\x00\x00\x01\x00\x06\x00\x30\x48\xb1\x1c\x34\x00\x00'
                 '\x08\x00%(data)s') % kwargs

        kwargs['data'] = frame
        sec = mktime(date.timetuple())
        msec = date.microsecond
        datalen = len(kwargs['data'])
        kwargs['pre'] = pack('<IIII', sec, msec, datalen, datalen)
        packet = '%(pre)s%(data)s' % kwargs

        return (packet, new_prev)

    def add(self, date, seqno, data):
        assert seqno == self.seqno, '%s != %s' % (seqno, self.seqno)

        # Data is prepended by len(data)
        data = chr(len(data)) + data

        # Auto-increasing dates
        if self.date is None or date > self.date:
            print 'date is larger', date, self.date
            self.date = date
        elif (date < self.date.replace(microsecond=0)):
            assert False, ('We increased too fast.. decrease delta: %r/%r' %
                           (date, self.date))
        else:
            self.date += timedelta(microseconds=9000)

#        if seqno == 0:
#            self.dateoff += timedelta(seconds=1)
#        if seqno == 1078:
#            self.dateoff += timedelta(seconds=1)
#        elif seqno == 1079:
#            self.dateoff += timedelta(seconds=2)
#        elif seqno == 1083:
#            self.dateoff += timedelta(seconds=2)

        print seqno, '\t', self.date + self.dateoff

        # Make packet.
        packet, prev_data = self.data2packet(self.date + self.dateoff,
                                             self.udpseqno, self.seqno,
                                             data, self.prev_data)
        self.outfile.write(packet)

        if False:
            # Send it again.
            self.date += timedelta(microseconds=9000)
            self.udpseqno += 1
            packet = self.data2packet(self.date + self.dateoff,
                                      self.udpseqno, self.seqno, data,
                                      self.prev_data)
            self.outfile.write(packet)

        # Increase values
        self.udpseqno += 1
        self.seqno += 1
        self.prev_data = prev_data

    def add_garbage(self, date):
        if self.date is None or date > self.date:
            self.date = date

        packet, ignored = self.data2packet(self.date, self.udpseqno,
                                           0xffff, 'GARBAGE', '')
        self.udpseqno += 1

        self.outfile.write(packet)


with open(sys.argv[1], 'r') as infile:
    with open(sys.argv[2], 'wb') as outfile:
        first = True
        p = FaxPcap(outfile)
        # p.add(datetime.now(), 0, n2b('06'))
        # p.add(datetime.now(), 1, n2b('c0 01 80 00 00 ff'))

        for lineno, line in enumerate(infile):
            # Look for lines like:
            # [2013-08-07 15:17:34] FAX[23479] res_fax.c: \
            #   FLOW T.38 Rx     5: IFP c0 01 80 00 00 ff
            if 'FLOW T.38 Rx' not in line:
                continue
            if 'IFP' not in line:
                continue

            match = search(r'(\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d):(\d\d)', line)
            assert match
            date = datetime(*[int(i) for i in match.groups()])

            match = search(r'Rx\s*(\d+):', line)
            assert match
            seqno = int(match.groups()[0])

            match = search(r': IFP ([0-9a-f ]+)', line)
            assert match
            data = n2b(match.groups()[0])

            # Have the file start a second early.
            if first:
                p.add_garbage(date)
                first = False

            # Add the packets.
            p.add(date, seqno, data)
