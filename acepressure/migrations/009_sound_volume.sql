-- Volume for each library sound (1.6.2), in percent from 10 to 100, where 100 plays the file as uploaded.
-- OBS, the dashboard preview and the tip page preview apply it. Older versions ignore the column.
-- No semicolons in these comments: the migration runner splits statements on them.
ALTER TABLE soundboards ADD COLUMN volume INTEGER NOT NULL DEFAULT 100
