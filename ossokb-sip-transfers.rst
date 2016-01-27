SIP transfers (ossokb, 2015)
============================

In telephony, transferring a call means moving one party of the
conversation to a different call. This can be done before the first call
has been established, before the second call has been established, or
after both calls are up.

With the SIP protocol stack, the different types of transfers are done
using various messages, depending on the direction of the transfer, and
the state of the first and second call.

The four (five) most common SIP transfer types are:

+-------------------------+--------------+-------------------+
| description             | who/result   | primary method    |
+=========================+==============+===================+
| `302 redirect`_         | B/AC         | 302               |
+-------------------------+--------------+-------------------+
| `Call pick-up`_         | C/AC         | INVITE w/Replaces |
+-------------------------+--------------+-------------------+
| `Blind transfer`_       | B/AC or A/BC | REFER             |
+-------------------------+--------------+-------------------+
| `Attended transfer`_    | B/AC or A/BC | REFER w/Replaces  |
| (and *blonde transfer*) |              |                   |
+-------------------------+--------------+-------------------+

The *who* and the *result* in the table above, describe who initiates
the transfer and which dialog is the end result; assuming that it is
A who starts a call with B.

*The examples below all assume that the SIP parties are directly
communicating with each other (Alice to Bob and Charlie). In an
Asterisk PBX setup, two SIP users are always speaking to a B2BUA
(Asterisk) in between. That B2BUA will take care of the transfer
on one end, so the other end may not notice that a transfer has
happened. Or they may notice, but through different means
(e.g. a re-INVITE or an UPDATE).*

*For example, in the 302 redirect case, Alice never sees any
redirect. The B2BUA simply retries the call to Charlie on the
B-leg side of the call.*



302 redirect
------------

User Alice calls Bob, Bob returns status code 302 and sends the call to
Charlie.

Here the transfer happens before any call has been established.

::

    (Alice)         (Bob)       (Charlie)
    |=================|=================|

    A ----INVITE----> B

    A <-----302------ B
        Contact: sip:C

    A ----------------------INVITE----> C
    A <-----------------------180------ C

    |=================|=================|

At this point, Alice hears the ringing (180) of Charlie's phone.

Links:
`RFC-3261-21.3.3 <https://tools.ietf.org/html/rfc3261#section-21.3.3>`_



Call pick-up
------------

User Alice calls Bob, Charlie picks up the call.

*Charlie has probably received the necessary call details through a
dialoginfo Event, passed in a NOTIFY transaction, because he has an open
SUBSCRIBE dialog with Alice or Bob or a presence server.*

Here the transfer happens before any call has been established.

::

    (Alice)         (Bob)       (Charlie)
    |=================|=================|

    A ----INVITE----> B

    A <---------------------INVITE----- C
        Replaces: <callid>;to-tag=<fromtag>;
          from-tag=<totag>;early-only
    A ------------------------200-----> C
    A <-----------------------ACK------ C

    A ----CANCEL----> B
    A <-----200------ B
    A <-----487------ B
    A ------ACK-----> B

    |=================|=================|

Alice has accepted (200) the call with Charlie. And Alice has cancelled
the original dialog with Bob.

*Observe how the fromtag and totag seem reversed. They should be read as
remote_tag and local_tag respectively. Similar to how the From and To
headers are swapped when the UAS turns UAC in a dialog.*

Links:
`RFC-3891-7.1 <https://tools.ietf.org/html/rfc3891#section-7.1>`_



Blind transfer
--------------

User Alice calls Bob, Bob picks up. Then he transfers Alice to Charlie.

Here the transfer happens after the first call has been established.

::

    (Alice)         (Bob)       (Charlie)
    |=================|=================|

    A ----INVITE----> B
    A <-----200------ B
    A ------ACK-----> B

    A <---INVITE----- B
        sdp: c=... 0.0.0.0 (old way)
        sdp: a=sendonly (place A on hold)
    A ------200-----> B
    A <-----ACK------ B

    A <----REFER----- B
        Refer-To: sip:C
    A ------202-----> B

    A ----------------------INVITE----> C
    A <-----------------------180------ C

    A ----NOTIFY----> B
        Event: refer;id=<cseq>
        Content-Type: message/sipfrag;version=2.0
        (body contains 180 Ringing, this updates as long as
        we keep the dialog up)
    A <-----200------ B

    A <-----BYE------ B
    A ------200-----> B

    |=================|=================|

At this point, Alice is trying to establish a new dialog with Charlie.
Whether that call succeeds is irrelevant to Bob. He has ended the
original dialog, so he won't get updated through NOTIFY messages
anymore.

*A similar scenario happens if Alice decides to REFER Bob to Charlie.
But then Bob sets up the new call, obviously.*

*The initiator of the transfer can keep the original dialog up for as
long as needed to establish whether the new call succeeded or not.
This means that a blind transfer to a failed destination can be picked
back up, if done right.*

*For those wondering: a REFER emitted out-of-dialog is legal, but may
not be accepted by the UAS. Having a phone start calling seemingly out
of the blue, would create confusion.*

Links:
`RFC-3515-2 <https://tools.ietf.org/html/rfc3515#section-2>`_
`RFC-5589-5 <https://tools.ietf.org/html/rfc5589#section-5>`_



Attended transfer
-----------------

User Alice calls Bob, Bob picks up. Bob puts the original call on hold
and establishes a second call to Charlie. First after Charlie answers,
he connects Alice with Charlie.

Here the transfer happens after two calls have been established.

::

    (Alice)         (Bob)       (Charlie)
    |=================|=================|

    A ----INVITE----> B
    A <-----200------ B
    A ------ACK-----> B

    A <---INVITE----- B
        sdp: c=... 0.0.0.0 (old way)
        sdp: a=sendonly (place A on hold)
    A ------200-----> B
    A <-----ACK------ B

                      B ----INVITE----> C
                      B <-----200------ C
                      B ------ACK-----> C

    A <----REFER----- B
        Refer-To: sip:C?
          Replaces=<callid>%3Bfrom-tag%3D
            <fromtag>%3Bto-tag%3D<totag>
    A <-----202------ B

    (Same NOTIFY transaction seen as in the blind transfer case.
     This time with a sipfrag with "200 OK".)

    A ----------------------INVITE----> C
        Replaces: <callid>;from-tag=
          <fromtag>;to-tag=<totag>
    A <-----------------------200------ C
    A ------------------------ACK-----> C

    (Note that this last bit doesn't happen in a B2BUA setting.
     The B2BUA will catch the REFER and internally move the B-leg
     of the AB call, to the B-leg of the BC call. At that point
     a reINVTIE will happen to unhold the A-leg and connect it to
     the new B-leg.)

    A ----NOTIFY----> B
        Event: refer;id=<cseq>
        Content-Type: message/sipfrag;version=2.0
        (body contains 200 OK, because the call is up)
    A <-----200------ B

    A <-----BYE------ B
    A ------200-----> B
        (hang it up, we're done)

                      B <-----BYE------ C
                      B ------200-----> C
        (hang it up, we've been replaced;
         this only concerns the A-leg side
         of this dialog)

    |=================|=================|

And now, Alice talks to Charlie.

**Blonde transfer** is a term used in the Asterisk community for this
scenario where the transfer happens while the BC-call is still in a
Ringing (180) state. Apart from that, it's the same.

*Compatibility note: the SPA941 does not do blonde transfers, it does
a blind transfer instead. The newer SPA504G does properly do a blonde
transfer.*

Links:
`RFC-5589-7 <https://tools.ietf.org/html/rfc5589#section-7>`_


.. footer:: Walter Doekes, OSSO B.V., august 2015
