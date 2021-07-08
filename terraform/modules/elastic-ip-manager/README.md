# Terraform module for elastip-ip-manager

Terraform module which deploys `elastip-ip-manager` and all required resources to AWS.

These types of resources are managed by this module:
* [IAM Role](https://www.terraform.io/docs/providers/aws/r/iam_role.html)
* [IAM Policy](https://www.terraform.io/docs/providers/aws/r/iam_policy.html)
* [Lambda Function](https://www.terraform.io/docs/providers/aws/r/lambda_function.html)
* [Lambda Permission](https://www.terraform.io/docs/providers/aws/r/lambda_permission.html)
* [CloudWatch Event Rule](https://www.terraform.io/docs/providers/aws/r/cloudwatch_event_rule.html)
* [CloudWatch Event Target](https://www.terraform.io/docs/providers/aws/r/cloudwatch_event_target.html)

## Terraform Version

This module supports Terraform 0.12.6 and higher

## Usage

The module contains all sane defaults, so no variables are required:
```hcl
module "elastic_ip_manager" {
  source = "git@github.com:binxio/ec2-elastic-ip-manager.git//terraform/modules/elastic-ip-manager"
}
```

But if you want, you can customize any variables. You can find all supported variables and their descriptions
in `./variables.tf`

### Use custom S3 bucket and tags

```hcl
module "elastic_ip_manager" {
  source = "git@github.com:binxio/ec2-elastic-ip-manager.git//terraform/modules/elastic-ip-manager"

  s3_bucket = "my-org-bucket"
  s3_key    = "path/to/elastic-ip-manager-latest.zip"

  tags = {
    CreatedBy = "terraform"
  }
}
```
