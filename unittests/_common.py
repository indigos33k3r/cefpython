# Copyright (c) 2018 CEF Python, see the Authors file.
# All rights reserved. Licensed under BSD 3-clause license.
# Project website: https://github.com/cztomczak/cefpython

from cefpython3 import cefpython as cef

import base64
import os
import platform
import sys
import time

# Platforms
SYSTEM = platform.system().upper()
if SYSTEM == "DARWIN":
    SYSTEM = "MAC"
WINDOWS = SYSTEM if SYSTEM == "WINDOWS" else False
LINUX = SYSTEM if SYSTEM == "LINUX" else False
MAC = SYSTEM if SYSTEM == "MAC" else False

# To show the window for an extended period of time increase this number.
MESSAGE_LOOP_RANGE = 100  # each iteration is 0.01 sec

g_subtests_ran = 0
g_js_code_completed = False
g_on_load_end_callbacks = []


def subtest_message(message):
    global g_subtests_ran
    g_subtests_ran += 1
    print(str(g_subtests_ran) + ". " + message)
    sys.stdout.flush()


def show_test_summary(pyfile):
    print("\nRan " + str(g_subtests_ran) + " sub-tests in "
          + os.path.basename(pyfile))


def html_to_data_uri(html):
    html = html.encode("utf-8", "replace")
    b64 = base64.b64encode(html).decode("utf-8", "replace")
    ret = "data:text/html;base64,{data}".format(data=b64)
    return ret


def run_message_loop():
    # Run message loop for some time.
    # noinspection PyTypeChecker
    for i in range(MESSAGE_LOOP_RANGE):
        cef.MessageLoopWork()
        time.sleep(0.01)
    subtest_message("cef.MessageLoopWork() ok")


def do_message_loop_work(work_loops):
    # noinspection PyTypeChecker
    for i in range(work_loops):
        cef.MessageLoopWork()
        time.sleep(0.01)


def on_load_end(callback, *args):
    global g_on_load_end_callbacks
    g_on_load_end_callbacks.append([callback, args])


def js_code_completed():
    """Sometimes window.onload can execute before javascript bindings
    are ready if the document loads very fast. When setting javascript
    bindings it can take some time, because these bindings are sent
    via IPC messaging to the Renderer process."""
    global g_js_code_completed
    assert not g_js_code_completed
    g_js_code_completed = True
    subtest_message("js_code_completed() ok")


def check_auto_asserts(test_case, objects):
    # Check if js code completed
    test_case.assertTrue(g_js_code_completed)

    # Automatic check of asserts in handlers and in external
    for obj in objects:
        test_for_True = False  # Test whether asserts are working correctly
        for key, value in obj.__dict__.items():
            if key == "test_for_True":
                test_for_True = True
                continue
            if "_True" in key:
                test_case.assertTrue(value, "Check assert: " +
                                     obj.__class__.__name__ + "." + key)
                subtest_message(obj.__class__.__name__ + "." +
                                key.replace("_True", "") +
                                " ok")
            elif "_False" in key:
                test_case.assertFalse(value, "Check assert: " +
                                      obj.__class__.__name__ + "." + key)
                subtest_message(obj.__class__.__name__ + "." +
                                key.replace("_False", "") +
                                " ok")
        test_case.assertTrue(test_for_True)


class DisplayHandler(object):
    def __init__(self, test_case):
        self.test_case = test_case

        # Asserts for True/False will be checked just before shutdown
        self.test_for_True = True  # Test whether asserts are working correctly
        self.javascript_errors_False = False
        self.OnConsoleMessage_True = False

    def OnConsoleMessage(self, message, **_):
        if "error" in message.lower() or "uncaught" in message.lower():
            self.javascript_errors_False = True
            raise Exception("Javascript error: " + message)
        else:
            # Check whether messages from javascript are coming
            self.OnConsoleMessage_True = True
            subtest_message(message)


class GlobalHandler(object):
    def __init__(self, test_case):
        self.test_case = test_case

        # Asserts for True/False will be checked just before shutdown
        self.test_for_True = True  # Test whether asserts are working correctly
        self.OnAfterCreated_True = False

    def _OnAfterCreated(self, browser, **_):
        # For asserts that are checked automatically before shutdown its
        # values should be set first, so that when other asserts fail
        # (the ones called through the test_case member) they are reported
        # correctly.
        self.test_case.assertFalse(self.OnAfterCreated_True)
        self.OnAfterCreated_True = True
        self.test_case.assertEqual(browser.GetIdentifier(), 1)


class LoadHandler(object):
    def __init__(self, test_case, datauri):
        self.test_case = test_case
        self.datauri = datauri
        self.frame_source_visitor = None

        # Asserts for True/False will be checked just before shutdown
        self.test_for_True = True  # Test whether asserts are working correctly
        self.OnLoadStart_True = False
        self.OnLoadEnd_True = False
        self.FrameSourceVisitor_True = False
        # self.OnLoadingStateChange_Start_True = False # FAILS
        self.OnLoadingStateChange_End_True = False

    def OnLoadStart(self, browser, frame, **_):
        self.test_case.assertFalse(self.OnLoadStart_True)
        self.OnLoadStart_True = True
        self.test_case.assertEqual(browser.GetUrl(), frame.GetUrl())
        self.test_case.assertEqual(browser.GetUrl(), self.datauri)

    def OnLoadEnd(self, browser, frame, http_code, **_):
        # OnLoadEnd should be called only once
        self.test_case.assertFalse(self.OnLoadEnd_True)
        self.OnLoadEnd_True = True
        self.test_case.assertEqual(http_code, 200)
        self.frame_source_visitor = FrameSourceVisitor(self, self.test_case)
        frame.GetSource(self.frame_source_visitor)
        browser.ExecuteJavascript("print('LoadHandler.OnLoadEnd() ok')")

        subtest_message("Executing callbacks registered with on_load_end()")
        global g_on_load_end_callbacks
        for callback_data in g_on_load_end_callbacks:
            callback_data[0](*callback_data[1])
        del g_on_load_end_callbacks

    def OnLoadingStateChange(self, browser, is_loading, can_go_back,
                             can_go_forward, **_):
        if is_loading:
            # TODO: this test fails, looks like OnLoadingStaetChange with
            #       is_loading=False is being called very fast, before
            #       OnLoadStart and before client handler is set by calling
            #       browser.SetClientHandler().
            #       SOLUTION: allow to set OnLoadingStateChange through
            #       SetGlobalClientCallback similarly to _OnAfterCreated().
            # self.test_case.assertFalse(self.OnLoadingStateChange_Start_True)
            # self.OnLoadingStateChange_Start_True = True
            pass
        else:
            self.test_case.assertFalse(self.OnLoadingStateChange_End_True)
            self.OnLoadingStateChange_End_True = True
            self.test_case.assertEqual(browser.CanGoBack(), can_go_back)
            self.test_case.assertEqual(browser.CanGoForward(), can_go_forward)


class FrameSourceVisitor(object):
    """Visitor for Frame.GetSource()."""

    def __init__(self, load_handler, test_case):
        self.load_handler = load_handler
        self.test_case = test_case

    def Visit(self, value):
        self.test_case.assertFalse(self.load_handler.FrameSourceVisitor_True)
        self.load_handler.FrameSourceVisitor_True = True
        self.test_case.assertIn("747ef3e6011b6a61e6b3c6e54bdd2dee",
                                value)
