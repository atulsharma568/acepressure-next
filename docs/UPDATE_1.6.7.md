# Update to AcePressure 1.6.7

Installs over 1.6.6. It also installs over 1.6.0 to 1.6.4 or a 1.6.5 test build: then read UPDATE_1.6.6.md too, because 1.6.7 includes everything in 1.6.6 (Start.bat turning your tip link on, and names filtered as whole words). Your data, `.env`, sounds and OBS sources are kept. There is no database change.

## What's new
- **Several sounds at once.** In **Sound library → Add a sound**, click **Choose files** and select several clips (Ctrl-click or Shift-click). The button changes to “Add 3 sounds”. Each sound is named after its file; the emoji, category, minimum tip and “Viewers can pick” apply to all of them. With several files, Name and “Make it my default sound” are switched off: pick your default under **Default sound** afterwards.
- **Several artwork files at once.** **Design studio → Upload your artwork** works the same way for images and videos.
- **A list when something fails.** A file that can't be added (too big, too long, not a sound or image) doesn't stop the others. A list under the form shows what was added and why any file wasn't. If you're signed out or AcePressure stops answering, the upload stops and the list names the files it didn't try.
- **Names you recognise.** The Design studio's image menus show the name a file was uploaded with, for example “logo.png · Kq3x9_abCdEfGh12.png”, sorted by that name. Files uploaded before 1.6.7 show only the stored name.
- Clicking Upload again in the Design studio while files upload no longer uploads them twice.

Details: CHANGELOG.md.

## Install safely
1. Finish outstanding payment reviews, then close the AcePressure window. If you use the **AcePressure Tipping** startup task, also end it in Task Scheduler.
2. Back up the whole installation folder, including `.env`, `data`, `data-demo` and your own media.
3. Extract this ZIP into a new, empty folder. From its AcePressure folder, copy `acepressure`, `scripts`, `docs`, `tests`, `run.py`, `VERSION`, `README.md`, `Install_Piper.bat` and both `PACKAGE_MANIFEST` files into your existing installation, replacing those files.
4. Keep `.env`, `.venv`, `data` and `data-demo`. Don't replace them or run a fresh setup over them.
5. Start AcePressure with the same launcher as before: `Start.bat` for live or `Start_Demo.bat` for demo.

## Try it
- Open **Sound library → Add a sound**, click **Choose files**, select two or three clips and set a category. Click **Add 3 sounds**. The list under Add a sound shows what was added, and the sounds appear under **Your sounds**.
- Open **Design studio → Upload your artwork**, select a few images and click **Upload 3 files**. Pick one under **Alert image / GIF / video**, then **Save appearance**.

## If you need to go back
Close AcePressure (and end the **AcePressure Tipping** task if you use it). From AcePressure-1.6.6-windows.zip, extracted as in step 3, copy the same items over your installation: `acepressure`, `scripts`, `docs`, `tests`, `run.py`, `VERSION`, `README.md`, `Install_Piper.bat` and both `PACKAGE_MANIFEST` files. Then delete `tests\test_release_167.py` (otherwise Test.bat stops with an error on 1.6.6) and start AcePressure as before. Sounds and artwork uploaded with 1.6.7 stay; the Design studio menus show only the stored names again.

If you installed 1.6.7 over 1.6.4 and want 1.6.4 back, use the 1.6.4 ZIP the same way, then delete both `tests\test_release_165.py` and `tests\test_release_167.py`.

## Limits
- Files go up one after another, so a batch takes as long as uploading them one by one. Videos take longest, because each one is converted.
- Keep the page open until the button says “Add sound” or “Upload image” again (switching tabs in the dashboard is fine). Files not uploaded yet when you close or reload the page are not added; the browser asks first.
- The tip page, OBS and the alert bundle are unchanged.
- Tested on a Mac in Chrome, not on Windows.
