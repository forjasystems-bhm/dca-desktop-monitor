import threading
import unittest
from backend.ui_dispatch import UiDispatcher
class FakeWidget:
    def __init__(self): self.owner=threading.get_ident();self.calls=[]
    def after(self, delay, callback):
        assert threading.get_ident()==self.owner, 'Tk called from worker'
        self.calls.append(callback);return len(self.calls)
    def bind(self,*args,**kwargs): pass
    def after_cancel(self,token):
        assert threading.get_ident()==self.owner
class DispatchTests(unittest.TestCase):
    def test_worker_never_calls_tk_and_closed_queue_discards_results(self):
        widget=FakeWidget();d=UiDispatcher(widget);seen=[]
        t=threading.Thread(target=lambda:d.post(lambda:seen.append(threading.get_ident())))
        t.start();t.join();self.assertEqual(seen,[])
        widget.calls.pop(0)();self.assertEqual(seen,[widget.owner])
        d.close();self.assertFalse(d.post(lambda:seen.append(99)))
        self.assertEqual(seen,[widget.owner])
    def test_overlapping_refreshes_are_serialized_and_coalesced(self):
        import time
        widget=FakeWidget();d=UiDispatcher(widget);seen=[]
        started=threading.Event();release=threading.Event()
        def first():started.set();release.wait(2);seen.append(1)
        d.run(first);self.assertTrue(started.wait(1))
        d.run(lambda:seen.append(2));d.run(lambda:seen.append(3))
        self.assertEqual(seen,[]);release.set()
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and (d.running or d.pending):
            if widget.calls:widget.calls.pop(0)()
            time.sleep(0.002)
        self.assertEqual(seen,[1,3]);d.close()
