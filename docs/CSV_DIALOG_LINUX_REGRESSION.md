# Linux CSV selection and competing balance errors

Base: `e82af43e829dce0625a387106d261e30b8c625f3`.

The reported screenshot shows a CSV picker and a modal balance error at the
same time, not evidence of process termination. The exact stablecoin error
was reproduced with synthetic operations. A Tk picker runs a nested event
loop: queued UI refresh callbacks can execute while it is open. Previously,
the balance callback opened another modal, without an explicit parent.

## Changes

- Background balance errors are inline, identify the affected operation and
  direct the user to Histórico e Edição. Stale totals/cards/history are cleared
  and marked unavailable, never replaced with zero.
- The picker has an explicit owning top-level, catches opening errors inline,
  prevents reentrant clicks, and invalidates previous previews on cancellation.
- CSV preview runs through the existing worker/dispatcher. Workers do not call
  Tk. Closing the view discards queued callbacks through its existing lifetime
  contract. Import still requires explicit confirmation and hash verification.
- Stablecoin validation, tolerances and transaction rules are unchanged. No
  quantity, nominal value, rate, fee or historical record is automatically fixed.

## Validation

Nine focused regressions cover inline errors, stale figures, reentrancy,
ownership, opening failure, asynchronous scheduling and completion, and actual
SQLite rejection/correction with before/after audit and original CSV bytes.
Local full regression: 279 tests passed, using synthetic data only.

`tests/linux_csv_dialog_smoke.py` exercises the real Tcl file picker under X11,
injects a balance error while it is open, cancels and selects a synthetic CSV,
checks GUI responsiveness during deliberately delayed preview, then imports
and checks that a stablecoin divergence remains visible without a modal.
It is included in the Linux packaging CI before build. CI results must be
checked for the resulting commit; adding this script is not evidence it passed.

Local GUI execution was unavailable because this host has no display/X server;
attempts to provision Xvfb were unsuccessful. The exact Bruno desktop/session
and installed package remain unverified. No real financial file was accessed.
No merge, release or distribution is performed by this correction.
