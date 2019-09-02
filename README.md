# AWS Elastic IP manager
The elastic-ip-manager, manages the assignment of a pool of Elastic IP addresses to instances. When
the instance is stopped or terminated, the elastic ip address is removed. When a new instance is started, an elastic 
ip is assigned to it.

## Who does it work?
The manager will listen to all EC2 instance state change notifications. When an instance with the tag `elastic-ip-manager-pool` 
reaches the state running, it will assign a free elastic ip addresses with the same tag and tag value.

## How do I use it?
You can start using the elastic IP manager, in three simple steps:

1. deploy the elastic-ip-manager
2. create a pool of tagged elastic IP addresses
3. create an auto scaling group of tagged instances

## deploy the elastic-ip-manager
To deploy the provider, type:

```sh
git clone https://github.com/binxio/ec2-elastic-ip-manager.git
cd ec2-elastic-ip-manager
aws cloudformation create-stack \
        --capabilities CAPABILITY_IAM \
        --stack-name elastic-ip-manager \
        --template-body file://./cloudformation/elastic-ip-manager.yaml

aws cloudformation wait stack-create-complete  --stack-name elastic-ip-manager
```
## Create a pool of Elastic IP addresses
Create a pool of elastic ip addresses, and tag them with an `elastic-ip-manager-pool` value:
```
  EIPBastionPoolTags:
    Type: Custom::Tag
    Properties:
      ResourceARN:
        - !Sub 'arn:aws:ec2:${AWS::Region}:${AWS::AccountId}:eip/${EIP1.AllocationId}'
        - !Sub 'arn:aws:ec2:${AWS::Region}:${AWS::AccountId}:eip/${EIP2.AllocationId}'
      Tags:
        elastic-ip-manager-pool: bastion

      ServiceToken: !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:cfn-tag-provider'
```
In this example we are using the [custom tag provider](https://github.com/binxio/cfn-tag-provider),
as the `AWS::EC2::EIP` does not (yet) support tags.

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

That is all. If you want to see it all in action, deploy the demo.

## Deploy the demo
In order to deploy the demo, type:

```sh
aws cloudformation create-stack \
        --capabilities CAPABILITY_NAMED_IAM \
        --stack-name elastic-ip-manager-demo \
        --template-body file://./cloudformation/demo-stack.yaml

aws cloudformation wait stack-create-complete  --stack-name elastic-ip-manager-demo
```

## Alternatives
There are two alternative solutions to achieve the same functionality:
1. use a [network load balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/network/create-network-load-balancer.html) 
2. associate an address [on instance startup](https://stackoverflow.com/questions/53919530/aws-ec2-user-data-script-to-allocate-elastic-ip)
In my use case, I did not want to spent money on keeping an NLB running nor give the instance all the permissions to associate an EIP to itself.
