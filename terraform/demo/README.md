# Demo of elastic-ip-manager by Terraform

That is a simple configuration allowing to deploy a demo stack of elastip-ip-manager to AWS.

It creates:
- The pool of 3 ElasticIPs
- Auto Scaling Group of 3 instances
- AWS Lambda function for elastic-ip-manager
- CloudWatch Event Rules and Targets for triggering the elastic-ip-manager Lambda function

## Requirements

- `terraform` 0.12.6 of higher (http://terraform.io/)

## Usage

This demo stack is designed to be deployed in the existing VPC.
You should provide the VPC ID and the list of public subnet IDS using variables, for example:

```
terraform init
terraform apply -var='vpc_id=vpc-1a2b3c4d5f' -var='subnets=["subnet-1a2b3c4d", "subnet-5e6f7g8h"]'
```
