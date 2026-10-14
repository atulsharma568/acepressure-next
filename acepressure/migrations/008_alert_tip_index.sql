-- Live activity shows each tip's alert status and the tip page asks whether an alert was queued: both look alerts up by tip.
CREATE INDEX IF NOT EXISTS alerts_tip ON alerts(tip_id);
