"""Phase 1a end-to-end demo: real browser go_to + observe via the shipped code."""
import sys
import time

sys.path.insert(0, "/home/ubuntu/barq/python")

from system_control.browser_control import browser_action  # noqa: E402

print("GO:", browser_action("go_to", {"url": "https://example.com", "browser": "chrome"}))
time.sleep(2)
print("OBSERVE:", browser_action("observe", {"browser": "chrome"}))
print("SESSIONS:", browser_action("list_sessions", {"browser": "chrome"}))
print("CLOSE:", browser_action("close_all", {"browser": "chrome"}))
