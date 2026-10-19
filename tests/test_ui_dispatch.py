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
