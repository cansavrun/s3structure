mock_provider "aws" {
  mock_data "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/tenantfiles-api-task", name = "tenantfiles-api-task" }
  }
}

variables {
  application_role_name = "tenantfiles-api-task"
  customers = {
    amy   = { bucket = "private-files", prefix = "amy/", external_id = "amy-external" }
    atlas = { bucket = "private-files", prefix = "atlas/", external_id = "atlas-external" }
  }
}

run "customers_have_distinct_read_only_scopes" {
  command = plan
  assert {
    condition     = jsondecode(aws_iam_role_policy.customer_read["amy"].policy).Statement[1].Resource == "arn:aws:s3:::private-files/amy/*"
    error_message = "Amy yalnızca amy/ prefix'ini okuyabilmeli."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.customer_read["atlas"].policy).Statement[0].Condition.StringLike["s3:prefix"][0] == "atlas/*"
    error_message = "Atlas ListBucket prefix'i atlas/ olmalı."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.customer_read["amy"].policy).Statement[1].Action == ["s3:GetObject"]
    error_message = "Müşteri rolünde yazma izni olmamalı."
  }
}

run "overlapping_prefix_rejected" {
  command = plan
  variables {
    customers = {
      amy   = { bucket = "private-files", prefix = "amy/", external_id = "amy-external" }
      atlas = { bucket = "private-files", prefix = "amy/sub/", external_id = "atlas-external" }
    }
  }
  expect_failures = [var.customers]
}
