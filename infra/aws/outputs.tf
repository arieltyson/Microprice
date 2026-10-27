output "bucket" {
  value = aws_s3_bucket.artifacts.bucket
}

output "dashboard_url" {
  value = "http://${aws_instance.gateway.public_dns}"
}

output "emr_service_role" {
  value = aws_iam_role.emr_service.name
}

output "emr_instance_profile" {
  value = aws_iam_instance_profile.emr_nodes.name
}
