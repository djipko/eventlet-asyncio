import eventlet

import sys
import threading

from eventlet import tpool
import trollius
from trollius import From, Return


class AsyncioThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.loop = None
        self._ready = threading.Event()

    def wait_ready(self):
        self._ready.wait()

    def run(self):
        print("<Processor %d>" % threading.current_thread().ident)
        self.loop = trollius.new_event_loop()
        trollius.set_event_loop(self.loop)
        self.loop.call_soon(self._ready.set)
        self.loop.run_forever()


class EventletFuture(object):
    def __init__(self, loop, callback, *args, **kwargs):
        self.loop = loop
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.sentinel = object()
        self._result = self.sentinel

    def result(self):
        @trollius.coroutine
        def _callback():
            self._result = yield From(self.callback(*self.args, **self.kwargs))

        def _dispatch_and_wait():
            self.loop.call_soon_threadsafe(trollius.async, _callback(), self.loop)
            while True:
                eventlet.sleep()
                if self._result != self.sentinel:
                    return self._result

        gt = eventlet.spawn(_dispatch_and_wait)
        return gt.wait()


class Executor(object):
    def __init__(self, callback, stream=None):
        self.callback = callback
        self.stream = stream or sys.stdin
        self.asyncio_thread = AsyncioThread()

    def start(self):
        print("<Executor %d>" % threading.current_thread().ident)
        self.asyncio_thread.start()
        self.asyncio_thread.wait_ready()
        eventlet.monkey_patch(thread=False)

        for line in self.stream.readlines():
            fut = EventletFuture(self.asyncio_thread.loop, self.callback, line.strip())
            result = fut.result()
            print("<Reader %d>: %s, %s" %
                  (threading.current_thread().ident, line.strip(), result))

    def stop(self):
       self.asyncio_thread.loop.stop()
       while True:
           try:
               self.asyncio_thread.loop.close()
           except:
               pass
           else:
               break


@trollius.coroutine
def async_reverser(line):
    print("<Processor %d>" % threading.current_thread().ident)
    yield From(trollius.sleep(1))
    raise Return(''.join(reversed(line)))


if __name__ == '__main__':
     e = Executor(async_reverser, open(__file__))
     try:
         e.start()
     finally:
         e.stop()

