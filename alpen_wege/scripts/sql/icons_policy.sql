-- Icons: the resource type `icon` and its access policies, for a database that already has users and policies.
-- Adds ONLY the icon rows (init_seed.py rebuilds the whole policy matrix from scratch, which would also remove every policy
-- that was edited by hand). Same rules as init_seed.py: the administrator reads and writes, every other group reads (scope all).
-- Idempotent, one transaction. Run it BEFORE the new api starts (a policy that was looked up earlier stays cached for 5 minutes).
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/icons_policy.sql
\set ON_ERROR_STOP on
BEGIN;

INSERT INTO core_ref_resource_type (id, key, name, color, icon, created_by)
SELECT gen_random_uuid(), 'icon', 'Icon', '#607D8B', 'image', u.id
  FROM (SELECT p.id FROM profile_usr_user p
          JOIN profile_user_credentials c ON c.user_id = p.id
         WHERE c.user_group = 'administrator' ORDER BY p.created_at LIMIT 1) u
ON CONFLICT (key) DO NOTHING;

INSERT INTO profile_access_policy (id, user_group, resource_type_id, action, scope)
SELECT gen_random_uuid(), v.user_group, rt.id, v.action, 'all'
  FROM core_ref_resource_type rt,
       (VALUES ('administrator', 'create'), ('administrator', 'read'), ('administrator', 'update'), ('administrator', 'delete'),
               ('editor', 'read'), ('viewer', 'read'), ('guest', 'read')) AS v(user_group, action)
 WHERE rt.key = 'icon'
   AND NOT EXISTS (SELECT 1 FROM profile_access_policy a
                    WHERE a.user_group = v.user_group AND a.resource_type_id = rt.id AND a.action = v.action);

DO $$
BEGIN
    IF (SELECT count(*) FROM profile_access_policy a JOIN core_ref_resource_type rt ON rt.id = a.resource_type_id WHERE rt.key = 'icon') < 7 THEN
        RAISE EXCEPTION 'the resource type icon has fewer than 7 policy rows: is there an administrator user?';
    END IF;
END $$;

COMMIT;
