# AWS Elastic IP manager
The elastic-ip-manager, manages the assignment of a pool of Elastic IP addresses to instances. When
the instance is stopped or terminated, the elastic ip address is removed. When a new instance is started, an elastic 
ip is assigned to it.

## Who does it work?
The manager will listen to all EC2 instance state change notifications. When an instance with the tag `elastic-ip-manager-pool` 
reaches the state running, it will assign a free elastic ip addresses with the same tag and tag value.

## How do I use it?
You can start using the elastic IP manager, in two simple steps:

1. create a pool of tagged elastic IP addresses
2. create an auto scaling group of tagged instances OR adjust autoscaling group of existing ones

## deploy the elastic-ip-manager
To deploy the provider, type:
~
```sh
cd ..
git clone https://github.com/binxio/ec2-elastic-ip-manager.git
cd ec2-elastic-ip-manager
LAMBDA_BUCKET_PREFIX=binxio-public
LAMBDA_BUCKET_REGION=eu-central-1    
make S3_BUCKET_PREFIX=${LAMBDA_BUCKET_PREFIX:-binxio-public} AWS_REGION=${LAMBDA_BUCKET_REGION:-eu-central-1} deploy

aws cloudformation create-stack \
        --capabilities CAPABILITY_IAM \
        --stack-name elastic-ip-manager \
        --template-body file://./cloudformation/elastic-ip-manager.yaml \
        --parameters ParameterKey=LambdaS3Bucket,ParameterValue=${LAMBDA_BUCKET_PREFIX}-${LAMBDA_BUCKET_REGION} \
        --parameters ParameterKey=CFNCustomProviderZipFileName,ParameterValue=lambdas/elastic-ip-manager-latest.zip
```
## Create a pool of Elastic IP addresses
Create a pool of elastic ip addresses, and tag them with an `elastic-ip-manager-pool` value:
```
  EIP1:
    Type: AWS::EC2::EIP
    Properties:
      Domain: vpc
      Tags:
        -
          Key: "elastic-ip-manager-pool"
          Value: bastion
```

## Create an auto scaling group
Create an auto scaling group and apply the tag `elastic-ip-manager-pool` to all the instances:
```
  AutoScalingGroup:
    Type: AWS::AutoScaling::AutoScalingGroup
    Properties:
      ...
      Tags:
        - Key: elastic-ip-manager-pool
          Value: bastion
          PropagateAtLaunch: true
```
The manager will automatically associate elastic ip addresses to instance tagged with `elastic-ip-manager-pool`. It does
this by subscribing to EC2 state change events. It will not do anything on instances without the
tag `elastic-ip-manager-pool`. The elastic IP manager also syncs the state every 5 minutes, to ensure that we are eventually
consistent in the face of errors.

## Adjust existing auto scaling group
If an auto scaling group with instances already exist, 

    aws autoscaling create-or-update-tags --tags ResourceId=elastic-ip-manager-demo,ResourceType=auto-scaling-group,Key=elastic-ip-manager-pool,Value=bastion,PropagateAtLaunch=true 

    instances=$(aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names elastic-ip-manager-demo | jq -r '..|.InstanceId?| select(. != null)' | tr '\n' ' ')

    aws ec2 create-tags --resources `echo $instances` --tags Key=elastic-ip-manager-pool,Value=bastion


That is all. If you want to see it all in action, deploy the demo.

## Deploy the demo

### Using CloudFormation Stack

Run these commands to deploy the demo using CloudFormation Stack:
```sh
export VPC_ID=$(aws ec2  --output text --query 'Vpcs[?IsDefault].VpcId' describe-vpcs)
export SUBNET_IDS=$(aws ec2 describe-subnets --output text \
  --filters Name=vpc-id,Values=$VPC_ID Name=default-for-az,Values=true --query 'Subnets[?MapPublicIpOnLaunch].SubnetId' \
  | tr '\t', '\,')

aws cloudformation create-stack --stack-name elastic-ip-manager-demo \
     --template-body file://./cloudformation/demo-stack.yaml \
     --parameters ParameterKey=VPC,ParameterValue=$VPC_ID ParameterKey=Subnets,ParameterValue=\"$SUBNET_IDS\"
```

### Using terraform

Make sure you have terraform 0.12+ installed and run these commands:
```sh
export VPC_ID=$(aws ec2  --output text --query 'Vpcs[?IsDefault].VpcId' describe-vpcs)
export SUBNET_LIST=$(aws ec2 describe-subnets --output json \
  --filters Name=vpc-id,Values=$VPC_ID Name=default-for-az,Values=true --query 'Subnets[?MapPublicIpOnLaunch].SubnetId' \
  | tr -d '\n ')

cd ./terraform/demo
terraform init
terraform apply -var="vpc_id=$VPC_ID" -var="subnets=$SUBNET_LIST"
```

## Alternatives
There are two alternative solutions to achieve the same functionality:
1. use a [network load balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/create-network-load-balancer.html) 
2. associate an address [on instance startup](https://stackoverflow.com/questions/53919530/aws-ec2-user-data-script-to-allocate-elastic-ip)
In my use case, I did not want to spent money on keeping an NLB running nor give the instance all the permissions to associate an EIP to itself.
