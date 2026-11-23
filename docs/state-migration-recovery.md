# Recover an interrupted local state migration

Terraform state, its backups and temporary copies can contain credentials in
plaintext. Keep them private. Stop all Terraform, quickstart and teardown runs
in every worktree before investigating; do not run Terraform against an
unverified copy. These steps do not change AWS resources.

1. Find the selected external state root in the private storage profile. If
   `<state-root>/.migration-in-progress.json` exists, read that small journal
   to identify `backup_root` and the affected modules. It contains paths and
   module names, not state values. Preserve the journal while investigating.
2. Preserve the entire external state root and the journal's backup directory
   in a new owner-only location. Pre-migration snapshots and their original
   backups are under `<backup-root>/preflight/<module>/<workspace>/`;
   `<backup-root>/retired/` contains originals archived during migration.
   Treat any `faig-state-migration-*` directories beneath the backup area as
   sensitive temporary state too. Do not delete any copy yet.
3. For every module and workspace in the migration inventory, compare its
   preflight snapshot with any external snapshot using
   `scripts.state_storage.checked_state_identity`: it returns the lineage,
   serial, managed-instance count and a digest of resource contents, without
   printing secret values. Compare against a copy; a different identity may
   indicate changes after the backup and must be investigated before restoring.
   The original worktree and the destination paths are shown in the quickstart
   migration inventory. State containing a moved-state sentinel is not a usable
   snapshot.
4. To roll back, after choosing the verified preflight snapshot for each
   workspace, restore it to its original module path (`terraform.tfstate` for
   default, `terraform.tfstate.d/<workspace>/terraform.tfstate` for named
   workspaces), with owner-only permissions. Restore any corresponding
   `.backup` separately. Other worktrees may contain invalid moved-state
   sentinels; retain them until the original owner is restored and verified.
   Preserve the external copy outside its active backend location so there is
   only one active state for each module/workspace.
5. Once every original is verified and no Terraform process is running,
   remove only the inspected, private `faig-state-migration-*` staging copies,
   clear the incomplete external profile and journal, and re-inventory all
   worktrees before retrying. Keep the preflight and retired backups until the
   restored or retried workflow has been verified. Do not use a Terraform
   `-reconfigure` as a substitute for restoring or migrating state.

If paths, identities or ownership are ambiguous, stop and investigate instead
of clearing the journal or deleting a snapshot. ECR and S3 must not be destroyed
as part of recovery.
