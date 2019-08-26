# AWS Elastic IP manager
The elastic-ip-manager, manages the assignment of a pool of Elastic IP addresses to instances. When
the instance is terminated, the elastic ip address is removed. When a new instance is started, an elastic ip
is assigned to it.

## Who does it work?
The manager will listen to all EC2 instance state change notifications. When an instance with the tag `elastic-ip-manager-pool` 
reaches the state running, it will assign a free elastic ip addresses with the same tag and tag value.

1. deploy the elastic-ip-manager
2. create a pool of Elastic IP addresses
3. create an auto scaling group

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

## Tag the auto scaling group
Apply the tag `elastic-ip-manager-pool` to all the instances in your auto scaling group that
you want to assign the elastic ips to.
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
## deploy the elastic-ip-manager
To deploy the provider, type:

```sh
aws cloudformation create-stack \
        --capabilities CAPABILITY_IAM \
        --stack-name elastic-ip-manager \
        --template-body file://./cloudformation/elastic-ip-manager.yaml

aws cloudformation wait stack-create-complete  --stack-name elastic-ip-manager
```
The manager will automatically associate elastic ip addresses to instance tagged with `elastic-ip-manager-pool`. It does
this by subscribing to EC2 state change events. It will not do anything on instances without the
tag `elastic-ip-manager-pool`. The elastic IP manager also syncs the state. So in cases of an error, the system will
be eventually consistent.

That is all. If you want it all in action, deploy the demo.

### Deploy the demo
In order to deploy the demo, type:

```sh
aws cloudformation create-stack \
        --capabilities CAPABILITY_NAMED_IAM \
        --stack-name elastic-ip-manager-demo \
        --template-body file://./cloudformation/demo-stack.yaml

aws cloudformation wait stack-create-complete  --stack-name elastic-ip-manager-demo
```
