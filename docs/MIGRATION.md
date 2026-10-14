# Migration from your existing AcePressure setup

## What was inspected

The supplied collection `AcePressure_FINAL_Alerts_UPI_WeeklyGoal(1).json` contains:

- `UPI QR - AcePressure` (image source)
- `Weekly Support Goal` (browser source)
- `YouTube Alerts - Horizontal` and `YouTube Alerts - Vertical`
- `Sub Alert`

The old weekly HTML has `CURRENT = 0`, `TARGET = 1000` and reloads every three seconds. The BAT changes the HTML manually. These files do not contain a transaction ledger, so there is no historical donation record to import automatically. The other supplied collection also contains a subscriber alert source. Those third-party alert URLs are not repurposed as UPI verification.

All 12 supplied files are preserved byte-for-byte under `legacy/original-uploads/`. The manifest records SHA-256 hashes. This is a private backup; original OBS exports may contain third-party alert tokens. Do not publish the folder.

## Safest manual migration

1. In OBS, export the currently active Scene Collection and duplicate it. Your live collection may have changed since the uploaded JSON; use a fresh export.
2. Back up `D:\Stream Assets\AcePressure` separately before making local changes.
3. Start the new application in demo mode and create a configurable goal.
4. In the **duplicate** collection, update `Weekly Support Goal`: uncheck Local file, paste the new goal URL from Admin → OBS, and set browser dimensions to 700×180. Inspect crop/position/scale in all horizontal and vertical scenes.
5. Add `AcePressure Tips - Horizontal` and `AcePressure Tips - Vertical` using the URLs and canvas dimensions in OBS.md. Leave your YouTube/Streamlabs/BotRix alerts in place for Super Chat, memberships and subscriber events.
6. Generate a QR to the **public tipping page** with `Generate_Page_QR.bat` after HTTPS is configured. Replace or hide the old direct-UPI QR in the duplicated scene collection. A static direct-UPI QR bypasses pending creation, so those transfers cannot be reliably attributed to a viewer request.
7. Test every scene and both Aitum orientations. Importing a collection does not guarantee every plugin/crop/transform is identical across OBS installations.
8. Once accepted, use the new collection. Keep the original collection and manual BAT/HTML for emergency rollback. Do not run the old installer over your new assets: it uses overwriting copies.

## Optional assisted scene-file migration

After `Install.bat`, drag a **fresh exported JSON** onto `Migrate_OBS.bat`. The script:

1. Creates `data/migration-backups/YYYYMMDD-HHMMSS/`.
2. Copies the exported JSON and, if it exists, the entire `D:\Stream Assets\AcePressure` directory into that backup.
3. Writes a **new** `AcePressure_Database_Goals.json` with a different collection name.
4. Replaces only browser source entries named exactly `Weekly Support Goal`, pointing them at `/overlay/goal` and 700×180.
5. Leaves all other sources, including QR and YouTube/subscriber alerts, unchanged.
6. Writes a migration report. It does not open OBS, import a collection, delete sources or change the original export.

Import the generated collection explicitly via OBS → Scene Collection → Import. Add the new alert sources and hide/replace the static QR manually after review. If you have multiple goals, edit the browser URL to use `goal=ID`; otherwise the generic route stacks all enabled goals and may need a taller source.

You may run:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_obs.py "D:\Exports\current.json" --goal YOUR_GOAL_ID
```

## Preserving your old manual counter

The original BAT/HTML remains usable as an independent emergency display. It is not a trusted ledger and cannot verify money. If a previous manually recorded total should contribute to a new campaign display, enter it as that goal's starting amount with a clear title/note in your own records. This does not fabricate individual donors or add revenue to financial statistics.

Do not manufacture historical donations from a single aggregate total. To reconstruct history, use actual bank references and amounts with dates, and implement a reviewed import if needed. No automatic fabricated history is included.
