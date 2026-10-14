# 1.2.0 validation — 11 October 2026

Automated backend regression suite: 95 passing tests. New coverage includes browser opt-in/forget, separation without consent and across browsers, HttpOnly cookie and blocking, remembered profiles after a merge, authenticated previews, invalid appearance settings, and rejecting active-content uploads while accepting decoded PNGs. Added tests validate SSML escaping/cache, dynamic voice selection and fixed public samples, and actual FFmpeg re-encoding of a test clip with its sound track removed.

Chromium acceptance script: passed admin login, persistent bridge capture/review, approval, supporter merge, Design studio save and all four preview frames, QR and exact-amount controls, identical payment parameters across optional app links, mobile layout, polling pause/expiry and later manual approval. No JavaScript page errors. All payment data in these tests was isolated and fictitious; no money was sent.

Manual visual inspection: Design studio and the four rendered previews. Live rendering uses the same alert/goal builders. Existing audio/TTS and queue code was retained.

Not validated here: real app launch on the user's iPhone, payment acceptance within Google Pay/Paytm/PhonePe, actual Windows audio/TTS output, and OBS capture on the user's PC. Azure synthesis is mocked, and actual Windows voice enumeration cannot run on this Linux host. The QR-first fallback is not a claim that third-party payment restrictions are fixed. Refresh OBS sources once after installing, test an alert, and check goal sizing on both canvases.
