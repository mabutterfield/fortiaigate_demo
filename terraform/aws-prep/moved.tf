moved {
  from = aws_iam_policy.ec2_phase8_documents_read
  to   = aws_iam_policy.ec2_scenario_documents_read
}

moved {
  from = aws_iam_role_policy_attachment.ec2_phase8_documents_read
  to   = aws_iam_role_policy_attachment.ec2_scenario_documents_read
}

moved {
  from = aws_s3_bucket.phase8_documents
  to   = aws_s3_bucket.scenario_documents
}

moved {
  from = aws_s3_bucket_public_access_block.phase8_documents
  to   = aws_s3_bucket_public_access_block.scenario_documents
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.phase8_documents
  to   = aws_s3_bucket_server_side_encryption_configuration.scenario_documents
}

moved {
  from = aws_s3_bucket_versioning.phase8_documents
  to   = aws_s3_bucket_versioning.scenario_documents
}

moved {
  from = aws_s3_bucket_policy.phase8_documents
  to   = aws_s3_bucket_policy.scenario_documents
}
