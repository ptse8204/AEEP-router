# Check supported Copilot access for Waza

The pinned Copilot CLI passed its native bootstrap checks. The operator sign-in
was unstarted when its first review expired. The [refreshed review](protected-login-review.json)
keeps the same binary, arguments and private home. It permits one terminal
sign-in with zero model calls or cash and expires November 16 at 8:22 p.m.
Vancouver time.

1. Check whether your own GitHub account has Copilot Free access. If GitHub
   requires payment, an upgrade or terms you do not accept, stop and report
   that access is unavailable. [GitHub plan details](https://docs.github.com/en/copilot/get-started/plans)
2. Open your own Terminal and run the command below. Type `LOGIN` at the prompt
   and complete the GitHub sign-in yourself. Keep the terminal output, device
   codes and credentials private.
3. Report only whether sign-in completed or access was unavailable. If the
   command stops partway through, report that it was interrupted. The existing
   one-attempt journal preserves any partial state.

```bash
python3 -B /Users/edwintse/Documents/aeep-toolkit-v2/reports/toolkit-v2/c13/waza-native-backend-20261104/operator-setup-20261113/protected-login.py --operator-login
```

Successful sign-in allows AEEP to prepare a separate account capability and
Waza backend check. Actual account compatibility and grades remain open.
