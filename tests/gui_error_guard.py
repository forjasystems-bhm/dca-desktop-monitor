"""Make asynchronous failures fail GUI CI instead of hiding behind green exit."""
import sys
import threading
import tkinter
import traceback
ERRORS=[]
def install():
    def record(kind,value,tb):
        ERRORS.append(str(value))
        traceback.print_exception(kind,value,tb)
    from tkinter import messagebox
    def unexpected_dialog(*args,**kwargs):
        raise AssertionError('Diálogo de erro inesperado no smoke: '+repr(args))
    messagebox.showerror=unexpected_dialog
    tkinter.Tk.report_callback_exception=lambda self,*args:record(*args)
    threading.excepthook=lambda args:record(args.exc_type,args.exc_value,args.exc_traceback)
    sys.unraisablehook=lambda args:record(args.exc_type,args.exc_value,args.exc_traceback)
def verify():
    if ERRORS:raise AssertionError('Exceções assíncronas da GUI: '+repr(ERRORS))
