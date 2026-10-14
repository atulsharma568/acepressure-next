# Upgrade to 1.2.0

1. Pause **Accept new tip requests** and finish outstanding payment reviews.
2. Stop the AcePressure server. Back up your entire installation folder while it is stopped.
3. Extract this ZIP into a separate folder. Copy **acepressure**, **scripts**, **docs**, **tests**, **VERSION**, and **Install_Media_Tools.bat** into your existing installation, replacing their old files. Keep `.env`, `.venv`, `data`, `data-demo`, and your uploaded media. Do not replace your data with empty folders.
4. Restart the same mode you were using: `Start.bat` for live, `Start_Demo.bat` for demo. The additive browser-recognition table is created automatically. No donation records are removed.
5. Sign in using your existing admin address. Refresh the dashboard and the OBS browser sources once to load the new scripts. Keep the local OBS URLs, overlay keys, audio settings and existing scene collection.
6. Open **Design studio**. Choose colors and a style, inspect the four silent previews, then **Save appearance**. Upload artwork at the bottom, choose the uploaded filename in the relevant selector, and save again.
7. Test an alert from **Alertbox**. Test alerts never change revenue. Inspect your existing goals in OBS, then reopen new tip requests when ready.

Your iPhone bridge token, Shortcut URL, bank marker, ngrok address and manual review setting do not need to change for this update.

## Weekly goal

Admin → Goals → Create a goal (or Edit). Enter your title and target, set **Period = week**, **Reset = automatic**, **Starting amount = 0** unless deliberately adding an opening amount, and enable **Show on OBS**. Week boundaries are Monday 00:00 Asia/Kolkata. Historical donations are retained. To keep progress beyond the week use carry-forward, or choose lifetime for a campaign. No default target is imposed by the server.

Use the goal URL from OBS with your existing overlay key. For OBS on the streaming PC, use the local server origin (normally `http://127.0.0.1:8765` live or port 8766 demo) and preserve the path and query. Design studio styles all goal overlays. Per-goal title, target, period, compact/large design and bar/segments remain under Goals.

## TTS and short alert videos

See [TTS_AND_MEDIA.md](TTS_AND_MEDIA.md) for detected male/female voices, local Windows speech, optional Azure speech, English/Hinglish sample testing, and short video/GIF plus separate sound. No secrets are needed for local Windows voices.

## Returning supporters

The public page now has an optional **Remember my supporter profile on this browser** checkbox. When selected, a random HttpOnly cookie groups later tips from that browser for up to one year. Only a keyed hash is stored in the database; no device fingerprinting is used. The browser remembers the checkbox preference locally.

This is recognition, not proof of identity. Different browsers/phones, cleared cookies and private browsing can create another profile. Names alone are never merged. Optional emails remain unverified grouping hints. Use Supporters → Merge duplicate after checking identity when needed. Remembered browser profiles follow an existing merge. A shared-device user should click **Forget this browser**; this removes recognition, not historical tips. Entering a different email can switch the remembered profile on that browser. No public history or private email is exposed by the cookie.

## Artwork

PNG, WebP and GIF are accepted, including animation. Maximum upload 8 MB, 4 megapixels per frame, 120 frames, 24 million decoded pixels in total. Images are resized to 1280×1280 maximum, re-encoded and stripped of metadata; animation is saved as WebP. No SVG, HTML, arbitrary CSS or remote images. Short MP4/WebM uploads are now supported for alerts with FFmpeg installed; see TTS_AND_MEDIA.md. Select None to stop using an image. Unused uploads are retained, including in backups.

Live and preview overlays use the same rendering functions. Previews use sample values, are silent, do not consume queued alerts, and never affect donations or goals. The previews show responsive browser viewports; confirm final scale on your 2560×1440 / 1080×1920 OBS canvases. Tier thresholds and alert duration remain editable in Alertbox; TTS and sounds keep their existing controls.

## Payment app errors

The QR already includes the exact amount and recipient. The checkout now leads with that QR, adds **Save payment QR**, and offers app links under **Try opening an installed UPI app**. After saving, open your payment app and use its photo/gallery scanner if supported. If the browser opens the PNG instead of downloading it, use its image-save/share controls. A second phone can camera-scan the QR directly.

App launch requests have an eight-second cooldown and no automatic retry. The same-personal-UPI links cannot guarantee app launch or acceptance on every iPhone/browser. They remain optional. Copy UPI ID and Copy exact amount remain available. Always check the recipient and paise amount inside the payment app. Do not split a payment, round it, or pay again without checking the app's history.

The supplied PhonePe screenshot already shows ₹100.78. Its ₹2,000 gallery-limit message does not explain a rejection of that smaller amount. This release does not claim to override or fix a payment-app restriction. If rejection persists after dismissing the popup, capture the final error (hide personal details) and note the app/browser versions and whether the QR was camera-scanned or imported from photos.

Google's documented Google Pay website integration requires verified UPI merchants, and its iOS scheme alone does not prove acceptance for a personal UPI recipient:
- https://developers.google.com/pay/india/api/web/intro
- https://developers.google.com/pay/india/api/ios/in-app-payments
Paytm's documented iOS gateway flow is a separate merchant integration:
- https://business.paytm.com/docs/upi-intent-for-ios

No payment is marked successful just because an app was opened or a QR saved. Existing verification/review rules remain in force.
