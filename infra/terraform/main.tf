terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = { Application = "tenantfiles", ManagedBy = "terraform" } }
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "application_role_name" {
  type        = string
  description = "Mevcut ECS task role adı; execution role veya AWS admin rolü değil."
}

variable "customers" {
  type = map(object({
    bucket      = string
    prefix      = string
    external_id = string
    kms_key_arn = optional(string)
  }))
  description = "Mevcut private S3 bucket/prefix kayıtları. Prefix boş veya / ile biter."
  validation {
    condition = alltrue([for id, c in var.customers :
      can(regex("^[a-z0-9][a-z0-9_-]{1,47}$", id)) &&
      can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", c.bucket)) &&
      (c.prefix == "" || (can(regex("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*/$", c.prefix)) && length(c.prefix) <= 256)) &&
      can(regex("^[A-Za-z0-9_+=,.@:/-]{2,128}$", c.external_id))
    ])
    error_message = "Geçersiz müşteri id, bucket, prefix veya external_id. Wildcard prefix kullanmayın."
  }
  validation {
    condition = alltrue(flatten([for a, x in var.customers : [for b, y in var.customers :
      a == b || x.bucket != y.bucket || (!startswith(x.prefix, y.prefix) && !startswith(y.prefix, x.prefix))
    ]]))
    error_message = "Aynı bucket içinde müşteri prefix'leri çakışamaz; boş prefix tüm bucket'ı ayırır."
  }
}

data "aws_iam_role" "application" { name = var.application_role_name }

resource "aws_iam_role" "customer" {
  for_each             = var.customers
  name                 = "tenantfiles-${each.key}"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = data.aws_iam_role.application.arn }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "sts:ExternalId" = each.value.external_id } }
    }]
  })
}

resource "aws_iam_role_policy" "customer_read" {
  for_each = var.customers
  name     = "read-own-files"
  role     = aws_iam_role.customer[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = "arn:aws:s3:::${each.value.bucket}"
        Condition = { StringLike = { "s3:prefix" = ["${each.value.prefix}*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${each.value.bucket}/${each.value.prefix}*"
      }
      ], each.value.kms_key_arn == null ? [] : [{
        Effect    = "Allow"
        Action    = ["kms:Decrypt"]
        Resource  = each.value.kms_key_arn
        Condition = { StringEquals = { "kms:ViaService" = "s3.${var.region}.amazonaws.com" } }
    }])
  })
}

resource "aws_iam_role_policy" "application_assume" {
  name = "tenantfiles-assume-customer-roles"
  role = data.aws_iam_role.application.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sts:AssumeRole"]
      Resource = [for role in aws_iam_role.customer : role.arn]
    }]
  })
}

output "customer_role_arns" {
  value = { for id, role in aws_iam_role.customer : id => role.arn }
}
