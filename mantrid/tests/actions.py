import os
import time
import eventlet
from eventlet.timeout import Timeout
from unittest import TestCase
from ..actions import Empty, Static, Unknown, NoHosts, Redirect, Proxy, Spin


class MockBalancer(object):
    "Fake Balancer class for testing."

    def __init__(self, fixed_action=None):
        self.fixed_action = None
    
    def resolve_host(self, host):
        return self.fixed_action


class MockSocket(object):
    "Fake Socket class that remembers what was sent"

    def __init__(self):
        self.data = ""

    def send(self, data):
        self.data += data
        return len(data)
    
    def sendall(self, data):
        self.data += data


class ActionTests(TestCase):
    "Tests the various actions"

    def test_empty(self):
        "Tests the Empty action"
        action = Empty(MockBalancer(), "zomg-lol.com", code=500)
        sock = MockSocket()
        action.handle(sock, "", "/", {})
        self.assertEqual(
            "HTTP/1.0 500 Internal Server Error\r\nConnection: close\r\nContent-length: 0\r\n\r\n",
            sock.data,
        )

    def test_handle(self):
        "Tests the Static action"
        action = Static(MockBalancer(), "kittens.net", type="timeout")
        sock = MockSocket()
        action.handle(sock, "", "/", {})
        self.assertEqual(
            open(os.path.join(os.path.dirname(__file__), "..", "errors", "timeout.http")).read(),
            sock.data,
        )

    def test_unknown(self):
        "Tests the Unknown action"
        action = Unknown(MockBalancer(), "firefly.org")
        sock = MockSocket()
        action.handle(sock, "", "/", {})
        self.assertEqual(
            open(os.path.join(os.path.dirname(__file__), "..", "errors", "unknown.http")).read(),
            sock.data,
        )

    def test_nohosts(self):
        "Tests the NoHosts action"
        action = NoHosts(MockBalancer(), "thevoid.local")
        sock = MockSocket()
        action.handle(sock, "", "/", {})
        self.assertEqual(
            open(os.path.join(os.path.dirname(__file__), "..", "errors", "no-hosts.http")).read(),
            sock.data,
        )

    def test_redirect(self):
        "Tests the Redirect action"
        action = Redirect(MockBalancer(), "lions.net", redirect_to="http://tigers.net")
        # Test with root path
        sock = MockSocket()
        action.handle(sock, "", "/", {})
        self.assertEqual(
            "HTTP/1.0 302 Found\r\nLocation: http://tigers.net/\r\n\r\n",
            sock.data,
        )
        # Test with non-root path
        sock = MockSocket()
        action.handle(sock, "", "/bears/", {})
        self.assertEqual(
            "HTTP/1.0 302 Found\r\nLocation: http://tigers.net/bears/\r\n\r\n",
            sock.data,
        )
        # Test with https
        action = Redirect(MockBalancer(), "oh-my.com", redirect_to="https://meme-overload.com")
        sock = MockSocket()
        action.handle(sock, "", "/bears2/", {})
        self.assertEqual(
            "HTTP/1.0 302 Found\r\nLocation: https://meme-overload.com/bears2/\r\n\r\n",
            sock.data,
        )

    def test_proxy(self):
        "Tests the Proxy action"
        # Check failure with no backends
        self.assertRaises(
            AssertionError,
            lambda: Proxy(MockBalancer(), "khaaaaaaaaaaaaan.xxx", backends=[]),
        )
        # TODO: launch local server, proxy to that

    def test_spin(self):
        "Tests the Spin action"
        # Set the balancer up to return a Spin
        balancer = MockBalancer()
        action = Spin(balancer, "aeracode.org", timeout=4, check_interval=1)
        balancer.fixed_action = action
        # Ensure it times out
        sock = MockSocket()
        try:
            with Timeout(5):
                start = time.time()
                action.handle(sock, "", "/", {})
                duration = time.time() - start
        except Timeout:
            self.fail("Spin lasted for too long")
        self.assert_(
            duration >= 4,
            "Spin did not last for long enough"
        )
        self.assertEqual(
            open(os.path.join(os.path.dirname(__file__), "..", "errors", "timeout.http")).read(),
            sock.data,
        )
        # Now, ensure it picks up a change
        sock = MockSocket()
        try:
            with Timeout(3):
                def host_changer():
                    eventlet.sleep(1)
                    balancer.fixed_action = Empty(balancer, "aeracode.org", code=402)
                eventlet.spawn(host_changer)
                action.handle(sock, "", "/", {})
        except Timeout:
            self.fail("Spin lasted for too long")
        self.assertEqual(
            "HTTP/1.0 402 Payment Required\r\nConnection: close\r\nContent-length: 0\r\n\r\n",
            sock.data,
        )



