output "lambda_function_arn" {
  value       = aws_lambda_function.elastic_ip_manager.arn
  description = "ARN of created AWS Lambda function"
}

output "lambda_function_name" {
  value       = aws_lambda_function.elastic_ip_manager.function_name
  description = "The name of created AWS Lambda function"
}

output "iam_role_name" {
  value       = aws_iam_role.elastic_ip_manager.name
  description = "The name of created IAM Role"
}
