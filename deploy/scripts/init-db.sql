-- First initialization of the dedicated ViMag database only.
-- The bootstrap administrator and application use distinct secret files.
DO $bootstrap$
BEGIN
  IF current_user <> 'vimag_cluster_admin' THEN
    RAISE EXCEPTION 'Unexpected bootstrap role';
  END IF;
  EXECUTE format(
    'CREATE ROLE vimag LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    btrim(pg_read_file('/run/secrets/db_password'))
  );
END
$bootstrap$;
ALTER DATABASE vimag OWNER TO vimag;
REVOKE CONNECT ON DATABASE vimag FROM PUBLIC;
GRANT CONNECT ON DATABASE vimag TO vimag;
