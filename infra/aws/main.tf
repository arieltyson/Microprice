# Cloud runs: an S3 bucket for packed sessions and results, an EC2 host for the
# gateway and dashboard, and least-privilege roles for EC2 and EMR.

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "artifacts" {
  bucket = "${var.project}-${data.aws_caller_identity.current.account_id}-${var.region}"
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    id     = "expire-emr-logs"
    status = "Enabled"
    filter {
      prefix = "emr-logs/"
    }
    expiration {
      days = 14
    }
  }
}

# EC2 host: reads results and data from its own prefixes only.
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "gateway_read" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/results/*", "${aws_s3_bucket.artifacts.arn}/data/*", "${aws_s3_bucket.artifacts.arn}/release/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["results/*", "data/*", "release/*"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${var.project}-gateway"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy" "gateway_read" {
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_read.json
}

resource "aws_iam_role_policy_attachment" "gateway_ssm" {
  role       = aws_iam_role.gateway.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "gateway" {
  name = "${var.project}-gateway"
  role = aws_iam_role.gateway.name
}

resource "aws_security_group" "web" {
  name        = "${var.project}-web"
  description = "Dashboard over HTTP from an allowed range; no SSH (use SSM Session Manager)"
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_instance" "gateway" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  iam_instance_profile   = aws_iam_instance_profile.gateway.name
  vpc_security_group_ids = [aws_security_group.web.id]
  metadata_options {
    http_tokens = "required" # IMDSv2 only
  }
  user_data = templatefile("${path.module}/user_data.sh", { bucket = aws_s3_bucket.artifacts.bucket })
  tags = {
    Name = "${var.project}-gateway"
  }
}

# EMR: the service role plus an instance profile that can read packed sessions
# and write sweep results, nothing else.
data "aws_iam_policy_document" "emr_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["elasticmapreduce.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "emr_service" {
  name               = "${var.project}-emr-service"
  assume_role_policy = data.aws_iam_policy_document.emr_assume.json
}

resource "aws_iam_role_policy_attachment" "emr_service" {
  role       = aws_iam_role.emr_service.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEMRServicePolicy_v2"
}

data "aws_iam_policy_document" "emr_nodes" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/sessions/*", "${aws_s3_bucket.artifacts.arn}/release/*"]
  }
  statement {
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/results/sweeps/*", "${aws_s3_bucket.artifacts.arn}/emr-logs/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
  }
}

resource "aws_iam_role" "emr_nodes" {
  name               = "${var.project}-emr-nodes"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy" "emr_nodes" {
  role   = aws_iam_role.emr_nodes.id
  policy = data.aws_iam_policy_document.emr_nodes.json
}

resource "aws_iam_instance_profile" "emr_nodes" {
  name = "${var.project}-emr-nodes"
  role = aws_iam_role.emr_nodes.name
}
