# Waza needs a protected account sign-in

The native client is ready for operator setup. The pinned Copilot 1.0.85
version/help commands and native containment check passed. Waza's published
binary embeds the selected source revision, but reports `vcs.modified=true`;
the release archive is publisher-hash verified, not a reproducible-build proof.
No Waza agent evaluation has run.

GitHub currently lists Copilot CLI in its Free plan, with no credit card required:
[plan details](https://github.com/features/copilot/plans). This corrects the earlier
assumption that a paid subscription is necessarily required. Your actual account
eligibility and available allowance remain unknown.

To make supported backend access available:

1. In your own browser, check whether your account has Copilot Free access. If
   enrollment is needed, choose only Free. Stop if payment, an upgrade or terms
   you do not accept are required. AEEP has no authority to enroll you or spend.
2. In your own Terminal, run the protected setup helper below. It runs only the
   pinned client's `login` command, with a private HOME and configuration area.
   Complete its GitHub device/browser sign-in yourself. Do not run this in an
   agent terminal, record its screen, or send its output, codes or tokens here.
3. Tell the implementation agent only “sign-in completed”, “no account access”,
   or the non-secret reason you stopped. Exit zero is not proof of entitlement.

```bash
python3 "/Users/edwintse/Documents/aeep-toolkit-v2/reports/toolkit-v2/c13/waza-native-backend-20261104/protected-login.py" --operator-login
```

The helper records one setup operation's duration and exit status in the existing
ledger, without capturing stdout/stderr or inspecting credential files. It does
not prompt a model, run Waza, read Codex authentication, install globally or
change a spending ceiling. The client may use OS authentication services during
your sign-in. Its private credential area must remain outside task workers and
agent inspection. No agent may enumerate, hash, copy or print its contents.

A later real-backend journey still needs an exact bounded execution/disclosure
review, applicable containment, protected grading and canonical result capture.
The current no-model checks cannot close that integration gate. If this setup is
interrupted, preserve its attempt and ask for recovery; do not retry the helper.
