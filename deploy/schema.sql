CREATE TABLE items (
  id                uuid PRIMARY KEY,      -- made in the app; also the photo's object name
  received_at       timestamptz NOT NULL,  -- on arrival, before the read; D5's time taken starts here
  revision          text,                  -- Cloud Run K_REVISION; NULL off Cloud Run
  reading           jsonb NOT NULL,        -- ArtNumberReading's shape, for replay through from_reading()
  value_shown       text,                  -- art_base; NULL means an empty read
  final_value       text,                  -- as entered; trim/uppercase only for the outcome comparison
  outcome           text CHECK (outcome IN ('unchanged', 'edited')),
  confirmed_at      timestamptz,
  CHECK (value_shown <> ''),                                  -- one form of empty
  CHECK ((final_value IS NULL) = (confirmed_at IS NULL)
     AND (outcome IS NULL) = (confirmed_at IS NULL)),         -- a confirm is all or nothing
  CHECK (confirmed_at IS NULL OR value_shown IS NOT NULL)     -- an empty read can't be confirmed
);
