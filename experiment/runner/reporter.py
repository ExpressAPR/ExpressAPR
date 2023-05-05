import json
import pathlib
import traceback

import threading

class ErrorReporter:
    def __init__(self, channel):
        self.channel = channel
        self.step = ''
        self.attachments = {}
        self.succ = True

    def reset(self):
        self.step = ''
        self.attachments = {}
        self.succ = True

    def set_step(self, step):
        self.step = step

    def attach(self, k, v):
        self.attachments.setdefault(k, []).append(v)

    def attach_fn(self, k, fn):
        p = pathlib.Path(fn)
        if p.exists():
            try:
                with p.open('r', encoding='utf-8') as f:
                    self.attach(k, f.read())
            except Exception as e:
                print('ATTACH FN ERROR', repr(e))
                self.attach(k, None)
        else:
            self.attach(k, None)

    def report_error(self, e):
        tbmsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        self.succ = False
        self.attach('error_type', str(type(e)))
        self.attach('error_repr', repr(e))
        self.attach('error_traceback', tbmsg)

    def write(self, f):
        json.dump({
            'succ': self.succ,
            'step': self.step,
            'attachments': self.attachments,
        }, f, indent=1)

class DoNothingReporter:
    def __init__(self, channel):
        self.channel = channel
        self.reset()

    def reset(self):
        self.step = 'nothing'
        self.attachments = {}
        self.succ = True

    def set_step(self, step):
        pass

    def attach(self, k, v):
        pass

    def attach_fn(self, k, fn):
        pass

    def report_error(self, exception):
        pass

    def write(self, f):
        pass

class ThreadDispatchingReporter:
    def __init__(self, cls, channel):
        self.channel = channel
        self.cls = cls
        self.reporter_map = {}

    def _get_reporter(self):
        tid = threading.get_ident()
        if tid not in self.reporter_map:
            print('create reporter for thread', tid)
            self.reporter_map[tid] = self.cls(self.channel)
        return self.reporter_map[tid]

    def __getattr__(self, item):
        #print('proxy', item)
        reporter = self._get_reporter()
        return getattr(reporter, item)

testkit_reporter = ErrorReporter('testkit')
