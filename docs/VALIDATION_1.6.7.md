# Validation — 1.6.7
13 October 2026, macOS build machine (the app and tests on Python 3.14, the check scripts on Python 3.9, headless Chrome). Based on the 1.6.6 release.

- Full pytest suite: **987 passed** (954 in 1.6.6). New: `tests/test_release_167.py`, 33 tests:
  - A Design studio upload returns and keeps the name it was uploaded with. Several files with the same name stay apart, a folder path in the name is never kept, files from before 1.6.7 have no name, and deleted files aren't listed. An alert bundle's visual keeps its name too. These names never reach the sound list, and the settings form can't write them.
  - Each sound added without a name (as Add a sound does for several files) becomes its own row named after its file, with the shared emoji, category, minimum tip and “Viewers can pick”, and none becomes the default. A bad file is refused with a reason the list can show, and adds no row.
  - The two forms (checked in the source here; the real-Chrome check below runs them):
    - the file fields take several files; with several sounds, Name and “Make it my default sound” are switched off;
    - files go up one at a time with the shared fields, read once when the batch starts; a failing file is listed and the rest still go up;
    - a sign-out, or AcePressure not answering, stops the batch and lists the files not tried;
    - a redraw during a batch draws the form busy and the batch reports to the form on screen; closing the page mid-batch asks first;
    - the list survives the redraw and shows once, long file names in it wrap, and the toast gives counts only;
    - one file works as before; a second click in the Design studio is ignored, and one file says “Uploading…”;
    - the menus show the uploaded name and are sorted by it; the alert bundle still takes one visual and one sound.
- Several files at once in real Chrome (65 checks), on the source folder and on the extracted ZIP:
  - Sound library, four files (two clips, one that isn't audio, one of 9 MB): the button counts while they go up; two rows are added once each with the shared category, emoji and ₹50 minimum; the default sound doesn't change; the list says which two weren't added and why; the form is ready again; the list shows once.
  - One sound works as before, with its name and “Make it my default sound”.
  - Design studio, three files (one isn't an image): two upload once each even when Upload is clicked twice, the failure is listed, and the menus show “logo.png · <stored name>”, also after a reload. One file gives the usual message, now naming the file as the menus show it (“Uploaded logo.png · <stored name>. Select it above, then save.”); one bad file gives the same error as before.
  - Uploads held by Chrome's DevTools until the check let them go, so “mid-batch” was exact:
    - Sound library: a tab switch and back mid-batch drew the form busy; it counted on there and the list appeared there. The rows kept the fields from when the batch started, not edits made meanwhile. The page asked before closing while files uploaded, and not after.
    - AcePressure stopped answering during the second of three sounds. The batch stopped; the list said the file in flight “may have been added” and the third wasn't tried, with what to check. The form kept its fields, and the dashboard reconnected by itself.
    - Design studio: one file said “Uploading…”. A batch redrawn midway stayed busy. When it finished on another tab, the toast gave counts and the list showed once on return. The menus listed “None” first, then by name. A sign-out mid-batch stopped it and listed the file not tried.
  - Phone width (390 px): long file names wrapped in both lists without sideways scrolling, and the toast gave counts only. No script errors.
- The 1.6.4 browser check in real Chrome (80 checks) and the live-mode check with a stand-in `tailscale` program (31 checks) passed on the extracted ZIP.
- Straight upgrades to 1.6.7 from the 1.6.0 to 1.6.4 ZIPs, both 1.6.5 test builds and 1.6.6, with the files copied over as UPDATE_1.6.7.md says (14 checks each):
  - settings, tips, sounds and the running session are kept, alerts play and the pages load;
  - artwork uploaded before the update is still listed, and new artwork keeps the name it was uploaded with;
  - sounds added without a name are named after their files, with the shared category and minimum, and the default stays.
- Rollback, 15 checks: 1.6.7, then 1.6.6, then 1.6.7 again on one installation and data folder.
  - 1.6.6 runs on the data 1.6.7 wrote: artwork, the chosen alert image, sounds, settings and alerts.
  - Test.bat fails while `tests\test_release_167.py` is left behind and passes once it's deleted, as UPDATE_1.6.7.md says.
  - Back on 1.6.7, the uploaded names return.
  - The same back to 1.6.4, with Test.bat passing once both test files are deleted, as UPDATE_1.6.7.md says (16 checks).
  - Also 1.6.7 back to the 1.6.0 to 1.6.4 ZIPs and forward again (11 checks each).
- Release ZIP: extracted into an empty folder and checked for:
  - the manifest and file hashes;
  - no `.env` or data;
  - launchers in ASCII with CRLF line endings;
  - on the extracted copy: the full suite and every check above;
  - a fresh install from the ZIP (41 checks).
- Not tested here: Windows (its file picker), a real phone connection over Funnel (simulated by holding and failing requests in Chrome), the browser's own “Leave site?” box (only that the page asks for it), OBS, real payments and the production database.

Still needs your PC:
- In Sound library → Add a sound, select two or three clips at once and add them.
- In Design studio → Upload your artwork, select two images at once, then pick one and save.
