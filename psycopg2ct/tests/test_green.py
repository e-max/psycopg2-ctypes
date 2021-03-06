#!/usr/bin/env python

# test_green.py - unit test for async wait callback
#
# Copyright (C) 2010-2011 Daniele Varrazzo  <daniele.varrazzo@gmail.com>
#
# psycopg2 is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# In addition, as a special exception, the copyright holders give
# permission to link this program with the OpenSSL library (or with
# modified versions of OpenSSL that use the same license as OpenSSL),
# and distribute linked combinations including the two.
#
# You must obey the GNU Lesser General Public License in all respects for
# all of the code used other than OpenSSL.
#
# psycopg2 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public
# License for more details.

import unittest

import psycopg2ct as psycopg2
from psycopg2ct import extensions
from psycopg2ct import extras
from psycopg2ct.tests.testconfig import dsn


class ConnectionStub(object):
    """A `connection` wrapper allowing analysis of the `poll()` calls."""
    def __init__(self, conn):
        self.conn = conn
        self.polls = []

    def fileno(self):
        return self.conn.fileno()

    def poll(self):
        rv = self.conn.poll()
        self.polls.append(rv)
        return rv

class GreenTests(unittest.TestCase):
    def setUp(self):
        self._cb = extensions.get_wait_callback()
        extensions.set_wait_callback(extras.wait_select)
        self.conn = psycopg2.connect(dsn)

    def tearDown(self):
        self.conn.close()
        extensions.set_wait_callback(self._cb)

    def set_stub_wait_callback(self, conn):
        stub = ConnectionStub(conn)
        extensions.set_wait_callback(
            lambda conn: extras.wait_select(stub))
        return stub

    def test_flush_on_write(self):
        # a very large query requires a flush loop to be sent to the backend
        conn = self.conn
        stub = self.set_stub_wait_callback(conn)
        curs = conn.cursor()
        for mb in 1, 5, 10, 20, 50:
            size = mb * 1024 * 1024
            del stub.polls[:]
            curs.execute("select %s;", ('x' * size,))
            self.assertEqual(size, len(curs.fetchone()[0]))
            if stub.polls.count(extensions.POLL_WRITE) > 1:
                return

        # This is more a testing glitch than an error: it happens
        # on high load on linux: probably because the kernel has more
        # buffers ready. A warning may be useful during development,
        # but an error is bad during regression testing.
        import warnings
        warnings.warn("sending a large query didn't trigger block on write.")

    def test_error_in_callback(self):
        conn = self.conn
        curs = conn.cursor()
        curs.execute("select 1")  # have a BEGIN
        curs.fetchone()

        # now try to do something that will fail in the callback
        extensions.set_wait_callback(lambda conn: 1//0)
        self.assertRaises(ZeroDivisionError, curs.execute, "select 2")

        # check that the connection is left in an usable state
        extensions.set_wait_callback(extras.wait_select)
        conn.rollback()
        curs.execute("select 2")
        self.assertEqual(2, curs.fetchone()[0])


def test_suite():
    return unittest.TestLoader().loadTestsFromName(__name__)

if __name__ == "__main__":
    unittest.main()
