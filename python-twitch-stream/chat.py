#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This file contains the python code used to interface with the Twitch chat.
Twitch chat is IRC-based, so it is basically an IRC-bot, but with special features for Twitch,
such as congestion control built in.
"""

import time
import socket
import re
import fcntl
import os
import errno


class TwitchChatStream(object):
    """
    The TwitchChatStream is used for interfacing with the Twitch chat of
    a channel. To use this, an oauth-account (of the user chatting)
    should be created. At the moment of writing, this can be done here:
    https://twitchapps.com/tmi/
    """
    username = ""
    oauth = ""
    s = None

    def __init__(self, username, oauth, connect=True):
        """Create a new stream object, and try to connect."""
        self.username = username
        self.oauth = oauth
        self.last_sent_time = time.time()
        if connect:
            # connect with the IRC-server already such that no object is
            # created with false info
            self.connect()

    @staticmethod
    def _twitch_logged_in(data):
        """
        Test the login status from the returned communication of the
        server.

        :param data: bytes received from server during login
        :type data: list of bytes

        :return boolean, True when you are logged in.
        """
        if re.match(r'^:(testserver\.local|tmi\.twitch\.tv)'
                    r' NOTICE \* :Login unsuccessful\r\n$', data):
            return False
        else:
            return True

    @staticmethod
    def _check_has_ping(data):
        """
        Check if the data from the server contains a request to ping.

        :param data: the byte string from the server
        :type data: list of bytes
        :return: True when there is a request to ping, False otherwise
        """
        return re.match(
            r'^PING :(tmi\.twitch\.tv|\.testserver\.local)$', data)

    @staticmethod
    def _check_has_message(data):
        """
        Check if the data from the server contains a message a user
        typed in the chat.

        :param data: the byte string from the server
        :type data: list of bytes
        :return: returns iterator over these messages
        """
        return re.match(r'^:[a-zA-Z0-9_]+\![a-zA-Z0-9_]+@[a-zA-Z0-9_]+'
                        r'(\.tmi\.twitch\.tv|\.testserver\.local) '
                        r'PRIVMSG #[a-zA-Z0-9_]+ :.+$', data)

    def connect(self):
        """
        Connect to Twitch
        """

        # Do not use non-blocking stream, they are not reliably
        # non-blocking
        # s.setblocking(False)
        # s.settimeout(1.0)

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connect_host = "irc.twitch.tv"
        connect_port = 6667
        try:
            s.connect((connect_host, connect_port))
        except (Exception, IOError):
            print("Unable to create a socket to %s:%s" % (
                connect_host,
                connect_port))
            raise  # unexpected, because it is a blocking socket

        # Connected to twitch
        # Sending our details to twitch...
        s.send('PASS %s\r\n' % self.oauth)
        s.send('NICK %s\r\n' % self.username)

        if not TwitchChatStream._twitch_logged_in(s.recv(1024)):
            # ... and they didn't accept our details
            raise
        else:
            # ... and they accepted our details
            # Connected to twitch.tv!
            # now make this socket non-blocking on the OS-level
            fcntl.fcntl(s, fcntl.F_SETFL, os.O_NONBLOCK)
            if self.s is not None:
                self.s.close()  # close the previous socket
            self.s = s          # store the new socket
            s.send('JOIN #%s\r\n' % self.username)

    def _send(self, message):
        """
        Send a message to the IRC stream
        :param message: the message to be sent.
        :type message: string
        """
        if time.time() - self.last_sent_time > 5:
            if len(message) > 0:
                try:
                    self.s.send(message + "\n")
                finally:
                    self.last_sent_time = time.time()

    def _send_pong(self):
        """
        Send a pong message, usually in reply to a received ping message
        :return:
        """
        self._send("PONG")

    def send_chat_message(self, message):
        """
        Send a chat message to the server.
        :param message: String to send (don't use \n)
        :return:
        """
        self._send("PRIVMSG #{0} :{1}".format(self.username, message))

    def _parse_message(self, data):
        """
        Parse the bytes received from the socket.
        :param data: the bytes received from the socket
        :return:
        """
        if TwitchChatStream._check_has_ping(data):
            self.send_pong()
        if TwitchChatStream._check_has_message(data):
            # TODO: replace twice \! by !
            return {
                'channel': re.findall(r'^:.+\![a-zA-Z0-9_]+'
                                      r'@[a-zA-Z0-9_]+'
                                      r'.+ '
                                      r'PRIVMSG (.*?) :',
                                      data)[0],
                'username': re.findall(r'^:([a-zA-Z0-9_]+)\!', data)[0],
                'message': re.findall(r'PRIVMSG #[a-zA-Z0-9_]+ :(.+)',
                                      data)[0].decode('utf8')
            }
        else:
            return None

    def twitch_recieve_messages(self):
        """
        Call this function to process everything received by the socket
        :return: list of chat messages received
        """
        result = []
        while True:
            # process the complete buffer, until no data is left no more
            try:
                msg = self.s.recv(4096)     # NON-BLOCKING RECEIVE!
            except socket.error, e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    # There is no more data available to read
                    return result
                else:
                    # a "real" error occurred
                    # import traceback
                    # import sys
                    # print(traceback.format_exc())
                    # print("Trying to recover...")
                    self.connect()
                    return result
            else:
                rec = [self._parse_message(line)
                       for line in filter(None, msg.split('\r\n'))]
                rec = [r for r in rec if r]     # remove Nones
                result.extend(rec)