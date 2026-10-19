"""Opt-in packaged GUI acceptance in an explicitly owned disposable wallet."""
from pathlib import Path
import json
import os
import re
import threading
import sys


def schedule_probe(root, app, token):
    folder=Path(os.environ.get('DCA_MONITOR_DATA_DIR','')).resolve()
    if (re.fullmatch('[a-f0-9]{32}',token or '') is None or
            not (folder/'package-test-owner.json').is_file() or
            json.loads((folder/'package-test-owner.json').read_text()) != {'token':token}):
        raise RuntimeError('Ensaio de distribuição exige carteira temporária explicitamente identificada.')
    if app.data_manager.arquivo_db.parent.resolve() != folder:
        raise RuntimeError('A carteira do ensaio diverge do destino isolado.')
    proof=folder/'package-test-result.json'
    errors=[]
    def callback_error(kind,value,tb):
        errors.append(str(value))
    root.report_callback_exception=callback_error
    threading.excepthook=lambda args:errors.append(str(args.exc_value))
    sys.unraisablehook=lambda args:errors.append(str(args.exc_value))
    def finish():
        result={'ready':False,'closed':False,'errors':errors}
        try:
            root.update_idletasks()
            result['ready']=bool(root.winfo_viewable())
            result['tcl_library']=str(root.tk.call('info','library'))
            result['tk_library']=str(root.tk.call('set','tk_library'))
            result['tcl_present']=(Path(result['tcl_library'])/'init.tcl').is_file()
            result['tk_present']=(Path(result['tk_library'])/'tk.tcl').is_file()
            from backend.app_lifecycle import APP_VERSION
            result['version']=APP_VERSION
            app._on_closing(force=True)
            result['closed']=bool(app._closing)
        except Exception as exc:
            errors.append(str(exc))
            try:root.destroy()
            except Exception:pass
        finally:
            proof.write_text(json.dumps(result),encoding='utf-8')
    # Wait until the splash has yielded to the actual main window.
    root.after(2500,finish)
