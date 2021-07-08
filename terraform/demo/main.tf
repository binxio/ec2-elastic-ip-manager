terraform {
  required_version = ">= 0.12.6"
}

# ---------------------------------------------------------------------------------------------------------------------
# Deploy a demo ElasticIP pool
# ---------------------------------------------------------------------------------------------------------------------

resource "aws_eip" "demo" {
  count = 3

  vpc = true

  tags = merge(var.tags, {
    Name                    = "demo-elastic-ip-manager"
    elastic-ip-manager-pool = "bastion"
  })
}

# ---------------------------------------------------------------------------------------------------------------------
# Deploy a demo Auto Scaling Group
# ---------------------------------------------------------------------------------------------------------------------

resource "aws_security_group" "bastion" {
  name        = "demo-elastic-ip-manager-bastion"
  description = "Demo Security Group for Bastion host"
  vpc_id      = var.vpc_id

  ingress {
    description = "Allow SSH from the internet"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Allow ping from the internet"
    from_port   = "-1"
    to_port     = "-1"
    protocol    = "icmp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

data "aws_ami" "amazon_linux" {
  owners      = ["amazon"]
  most_recent = true

  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

resource "aws_launch_template" "demo" {
  name_prefix   = "demo-elastic-ip-manager"
  image_id      = data.aws_ami.amazon_linux.id
  instance_type = "t2.micro"

  network_interfaces {
    security_groups             = [aws_security_group.bastion.id]
  }

  tag_specifications {
    resource_type = "instance"

    tags = merge(var.tags, {
      elastic-ip-manager-pool = "bastion"
    })
  }

  tags = var.tags
}

resource "aws_autoscaling_group" "demo" {
  name_prefix         = "demo-elastic-ip-manager"
  vpc_zone_identifier = var.subnets
  desired_capacity    = 3
  max_size            = 3
  min_size            = 1

  launch_template {
    id      = aws_launch_template.demo.id
    version = "$Latest"
  }
}

# ---------------------------------------------------------------------------------------------------------------------
# Deploy elastic-ip-manager Lambda function and all related resources
# ---------------------------------------------------------------------------------------------------------------------

module "elastic_ip_manager" {
  source = "../modules/elastic-ip-manager"

  tags = var.tags
}
