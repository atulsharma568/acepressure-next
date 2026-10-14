# Version 1.1.2 — payment-app buttons

Live checkout now shows Google Pay, PhonePe and Paytm separately. The QR remains a standard UPI QR for any compatible scanner. The generic button is labelled Other / default UPI app because Safari may hand it to WhatsApp or another registered handler.

Each button preserves exactly the QR/link query: payee UPI ID, name, exact rupees/paise, INR, tip reference and note. No button marks a tip paid. Only the existing authenticated bridge and review flow can confirm it.

## Update from 1.1.1
Pause new tips and finish outstanding reviews. Stop Start.bat and back up your existing folder. Extract separately; copy the new acepressure, docs and tests folders plus VERSION into your existing installation, replacing program files. Preserve .env, .venv, data and data-demo. Restart Start.bat and reload checkout. No token, UPI or ngrok changes are needed.

## Device check — no money required
Create a fresh pending tip. On Safari, tap each installed app's button separately and confirm it opens the intended app and pre-fills the correct recipient and exact paise amount. Cancel/back out without entering a PIN or paying. Return to the same pending page for the next app, within its timer. Opening/returning must never show payment success. Report the app name and behavior if a link does not work.

Google documents gpay://upi/pay for its iOS/web flows:
https://developers.google.com/pay/india/api/ios/in-app-payments
https://developers.google.com/pay/india/api/web/pay-ui

The PhonePe phonepe://pay and Paytm paytmmp://upi/pay links are compatibility attempts, not a confirmed vendor contract for Safari personal-UPI payments. No public primary specification confirming those exact personal-account flows was found during this update. They require device validation. Even a correctly formatted link may fail because of app version, browser policy or recipient restrictions. Do not substitute merchant codes or claim merchant approval to work around a rejection. QR is the fallback; never authorize unless the app shows the correct recipient and amount.

Browser checks validate three buttons, identical query parameters and mobile fit. They cannot launch installed iPhone payment apps. This update is not a payment-gateway SDK integration and does not add a bank-signed receipt.
