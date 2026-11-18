# NVIDIA package cache for AWS bootstrap

The optional cache keeps a tested NVIDIA driver and its downloaded Ubuntu
package dependencies in an operator-owned private S3 object. The bucket is
independent of the disposable FAIG infrastructure and is not deleted by the
normal demo teardown. The cache is disabled unless both an object URI and an
independently recorded SHA-256 are configured.

The bootstrap verifies the entire object against the configured SHA-256,
checks each package's hash and metadata, and checks Ubuntu release,
architecture, and driver branch. It creates a local APT repository and asks
APT to install the exact cached NVIDIA driver, utilities, DKMS, and compute
utilities versions. Other packages can still be resolved from Ubuntu if they
are not in the cache. An unavailable S3 object falls back to the usual Ubuntu
APT install; a downloaded object with a bad checksum or incompatible metadata
stops the bootstrap. An S3 error can also indicate missing IAM access.

The checksum must be recorded through a trusted channel separate from the S3
object: a hash stored next to an untrusted object is not authentication. The
local APT repository is marked trusted because its packages were verified
against that configured hash; keep its path root-owned. A cache accelerates
package downloads but does not eliminate DKMS compilation, reboot, kernel
compatibility checks, or all access to Ubuntu's repositories. The branch name
(e.g. `595-server`) is not a full driver version. Exact pins here apply to the
bootstrap install; normal OS upgrades are not automatically held.

## Build a bundle

On an Ubuntu host of the same release and architecture, after the desired
NVIDIA driver installation has successfully completed and the complete `.deb`
files remain in APT's cache, copy `scripts/nvidia_package_cache.py` to the
host and run:

```sh
sudo python3 /tmp/nvidia_package_cache.py build \
  --packages /var/cache/apt/archives --driver-suffix 595-server \
  --output /var/tmp/faig-nvidia-cache.tar
```

The helper refuses an incomplete cache or inconsistent versions of the four
required NVIDIA packages and prints the bundle SHA-256 and driver version.
Review the package set and store the checksum outside the bucket. APT may
clean downloaded packages on some images; in that case fetch the exact desired
packages and dependencies into a staging directory before building. Do not
bundle an APT `partial` directory or a package download still in progress.

Upload the bundle to a versioned, immutable-by-convention object key in a
private bucket. One option is to copy it to an operator workstation and upload
with its SSO profile; alternatively grant the host a short-lived, object-scoped
`PutObject` permission and remove it after upload. Verify the resulting object
against the recorded SHA-256. S3 storage, requests, and any cross-region
transfer have their normal AWS charges.

## Configure AWS and Ansible

Configure the same exact object URI in the AWS prep module's ignored override
file and apply its plan:

```hcl
nvidia_package_cache_s3_uri = "s3://your-bucket/ubuntu/24.04/595-server/FULL-VERSION/CHECKSUM.tar"
```

The optional Terraform policy gives the EC2 role only `s3:GetObject` for that
object. It does not create a bucket, write packages, or put the bucket into the
Terraform destroy path. If the bucket uses a customer-managed KMS key, supply
the additional key permission separately.

In ignored `ansible/group_vars/user.yml`, configure:

```yaml
nvidia_package_cache_s3_uri: "s3://your-bucket/ubuntu/24.04/595-server/FULL-VERSION/CHECKSUM.tar"
nvidia_package_cache_sha256: "<trusted-64-character-sha256>"
nvidia_package_cache_region: "us-east-2"
```

The AWS CLI must be available on the host; the `common` role installs it before
this driver role. A successful fresh-host bootstrap should be followed by
`nvidia-smi`, a reboot, and Kubernetes GPU validation. When intentionally
upgrading the driver, build and test a new versioned object, update both the URI
and trusted checksum, and update the Terraform read policy. Leaving the URI
and checksum empty uses the standard unpinned branch-based Ubuntu install.
