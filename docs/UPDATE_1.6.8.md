# Update to AcePressure 1.6.8

Installs over 1.6.7. If you are on an older 1.6.x, read UPDATE_1.6.7.md and UPDATE_1.6.6.md too, because 1.6.8 includes them. Your data, `.env`, sounds and OBS sources are kept. There is no database change.

## What's new
- **Payment buttons you can see.** After a viewer taps Continue, “Pay with” and four large buttons (Google Pay, PhonePe, Paytm, Other UPI app) are at the top. The QR and copy buttons follow under “or scan the QR”.
- **The amount comes along.** PhonePe and Paytm now open on their payment screen with the exact amount, for example ₹20.76. Tapping any button also copies the amount, so a viewer can paste it if an app still opens without it.
- **₹1,000 and more match.** Paytm notifications like “Received ₹1,000.37” are read correctly. Before, they waited in review with no amount.
- `Install_Web.bat` now finishes and builds the new frontend, and `Start_Next.bat` builds it if needed.

Details: CHANGELOG.md.

## Install safely
1. Finish outstanding payment reviews, then close the AcePressure window. If you use the **AcePressure Tipping** startup task, also end it in Task Scheduler.
2. Back up the whole installation folder, including `.env`, `data`, `data-demo` and your own media.
3. Get the new files: run `git pull` in your AcePressure folder, or copy `acepressure`, `docs`, `tests`, `web`, `VERSION`, `README.md`, `Install_Web.bat`, `Start_Next.bat`, `Start_Web.bat` and both `PACKAGE_MANIFEST` files over your installation.
4. Keep `.env`, `.venv`, `data` and `data-demo`. Don't replace them or run a fresh setup over them.
5. Start AcePressure with the same launcher as before: `Start.bat` for live or `Start_Demo.bat` for demo.
6. Only if you use the Next.js page: run `Install_Web.bat` again so the frontend is rebuilt.

## Try it on your phone (no money needed)
1. Start AcePressure live, open your tip link on the iPhone and create a ₹20 tip.
2. Check that “Pay with” and the four buttons appear right under the amount.
3. Tap **PhonePe**. It should open on a payment screen to your UPI ID with the exact amount, for example ₹20.76. **Back out without entering your PIN.**
4. Return to the tip page and repeat with **Paytm**, **Google Pay** and **Other UPI app** (wait a few seconds between taps).
5. If an app opens without the amount, note which app and what it showed, then paste in it: the amount is on the clipboard. The QR always carries the amount.

## If you need to go back
Close AcePressure. Run `git checkout` on the previous commit, or copy the same items from the 1.6.7 files over your installation. Then delete `tests\test_release_168.py` (otherwise Test.bat stops with an error on 1.6.7) and start AcePressure as before.

## Limits
- The PhonePe and Paytm link formats are not published by those companies, and an app update can change them. Google Pay may still refuse or leave the amount empty for a personal UPI ID. The QR and copy buttons always work.
- In Safari a tap can ask “Open in PhonePe?” first; that's normal.
- The app buttons only work on a phone with the app installed. On a computer, use the QR.
