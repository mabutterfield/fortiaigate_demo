# Temporary AWS NVIDIA Package Cache Workaround

This is a temporary operator workaround for slow NVIDIA package downloads during
AWS k3s host bootstrap. It creates a private S3 cache bucket and grants the
existing k3s EC2 instance role read/write access, so the instance can pull cached
`.deb` bundles without an interactive AWS login.

This is not part of automated quickstart yet. Do not put this bucket in the
normal demo teardown path.

## Bucket Naming

Use a stable cache bucket base name, the AWS account ID from the active profile,
and the AWS region. The current temporary convention is
`faig-cache-${AWS_ACCOUNT_ID}-${AWS_REGION}`:

```bash
export AWS_PROFILE=ftnt-admin
export AWS_REGION=us-east-1

export CACHE_BUCKET_BASE=faig-cache
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --profile "$AWS_PROFILE" --query Account --output text)"
export CACHE_BUCKET="${CACHE_BUCKET_BASE}-${AWS_ACCOUNT_ID}-${AWS_REGION}"
export EC2_ROLE_NAME="$(terraform -chdir=terraform/aws-prep output -raw ec2_iam_role_name)"
export CACHE_POLICY_NAME="${CACHE_BUCKET_BASE}-nvidia-readwrite"
```

For a typical deployment, `EC2_ROLE_NAME` resolves to `faig-demo-ec2-role`.

## Create The Private Bucket

For `us-east-1`:

```bash
aws s3api create-bucket \
  --profile "$AWS_PROFILE" \
  --bucket "$CACHE_BUCKET" \
  --region "$AWS_REGION"
```

For other regions:

```bash
aws s3api create-bucket \
  --profile "$AWS_PROFILE" \
  --bucket "$CACHE_BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION"
```

Apply basic private-bucket controls:

```bash
aws s3api put-public-access-block \
  --profile "$AWS_PROFILE" \
  --bucket "$CACHE_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption \
  --profile "$AWS_PROFILE" \
  --bucket "$CACHE_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

## Grant The Existing k3s Role Access

The AWS k3s instance already uses the prep-owned EC2 role from
`terraform/aws-prep`. Attach a narrow IAM policy to that role:

```bash
cat > /tmp/faig-nvidia-cache-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListFaigNvidiaCacheBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::${CACHE_BUCKET}"
    },
    {
      "Sid": "ReadWriteFaigNvidiaCacheObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::${CACHE_BUCKET}/*"
    }
  ]
}
EOF

aws iam create-policy \
  --profile "$AWS_PROFILE" \
  --policy-name "$CACHE_POLICY_NAME" \
  --policy-document file:///tmp/faig-nvidia-cache-policy.json

aws iam attach-role-policy \
  --profile "$AWS_PROFILE" \
  --role-name "$EC2_ROLE_NAME" \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${CACHE_POLICY_NAME}"
```

## Upload A Package Bundle

After downloading package files into `~/nvidia-debs`:

```bash
cd ~
tar -czf nvidia-debs-ubuntu-24.04-595-server.tgz nvidia-debs

aws s3 cp \
  --profile "$AWS_PROFILE" \
  nvidia-debs-ubuntu-24.04-595-server.tgz \
  "s3://${CACHE_BUCKET}/ubuntu/24.04/nvidia/595-server/nvidia-debs-ubuntu-24.04-595-server.tgz"
```

## Download From The EC2 Instance

Because the instance role has S3 access, this does not require `aws sso login`
on the instance:

```bash
aws s3 cp \
  "s3://${CACHE_BUCKET}/ubuntu/24.04/nvidia/595-server/nvidia-debs-ubuntu-24.04-595-server.tgz" \
  .

tar -xzf nvidia-debs-ubuntu-24.04-595-server.tgz
sudo apt-get update
sudo apt-get install -y ./nvidia-debs/*.deb
sudo reboot
```

## Future Direction

Longer term, the cache bucket should remain a semi-permanent operator-owned
bucket. Terraform should not create or destroy it as part of the disposable demo
environment.

The likely implementation is:

- Add a user/system variable such as `nvidia_package_cache_bucket_name`, or a
  bucket base variable that derives `${bucket_base}-${account_id}-${region}`.
- If set, look up the existing bucket with a Terraform `data "aws_s3_bucket"`.
- Extend the prep-owned EC2 role policy to include the required object read, and
  optionally write, permissions for that bucket.
- Update Ansible bootstrap to try the S3 cache first and fall back to apt when
  the bucket or package archive is absent.
