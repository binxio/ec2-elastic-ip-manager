# AWS Auto Scaling Group Elastic IP manager
The asg-elastic-ip-manager, manages the assignment of a pool of Elastic IP addresses to instances of an auto scaling group. When
the instance is terminated, the elastic ip address is removed. When an instance is added to the auto scaling group, an elastic ip
is assigned to it.

## Who does it work?
The manager will listen to all auto scaling group events. When an instance is launched in an auto scaling group tagged `asg-elastic-ip-manager-pool`, it
will assign a free elastic ip addresses with the same tag and tag value.

1. create a pool of Elastic IP addresses
2. tag the auto scaling group to be managed
3. deploy the asg-elastic-ip-manager

## Create a pool of Elastic IP addresses
Create a pool of elastic ip addresses, by apply the tag `asg-elastic-ip-manager` to them.
```
  EIPBastionPoolTags:
    Type: Custom::Tag
    Properties:
      ResourceARN:
        - !Sub 'arn:aws:ec2:${AWS::Region}:${AWS::AccountId}:eip/${EIP1.AllocationId}'
        - !Sub 'arn:aws:ec2:${AWS::Region}:${AWS::AccountId}:eip/${EIP2.AllocationId}'
      Tags:
        asg-elastic-ip-manager-pool: bastion

      ServiceToken: !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:function:cfn-tag-provider'
```

## Tag the auto scaling group
Apply the tag `asg-elastic-ip-manager-pool` with the name of the pool to the auto scaling group that
you want to assign the elastic ips to.
```
  AutoScalingGroup:
    Type: AWS::AutoScaling::AutoScalingGroup
    Properties:
      ...
      Tags:
        - Key: asg-elastic-ip-manager-pool
          Value: bastion
```
## deploy the asg-elastic-ip-manager
To deploy the provider, type:

```sh
aws cloudformation create-stack \
        --capabilities CAPABILITY_IAM \
        --stack-name asg-elastic-ip-manager \
        --template-body file://./cloudformation/asg-elastic-ip-manager.yaml

aws cloudformation wait stack-create-complete  --stack-name asg-elastic-ip-manager
```
The manager will automatically associate elastic ip addresses to any auto scaling group tagged with `asg-elastic-ip-manager-pool`. It does
this by subscribing to terminate and launch events of all auto scaling groups. It will not do anything on auto scaling groups without the
tag `asg-elastic-ip-manager-pool`.

That is all. If you want it all in action, deploy the demo.

### Deploy the demo
In order to deploy the demo, type:

```sh
aws cloudformation create-stack \
        --capabilities CAPABILITY_NAMED_IAM \
        --stack-name asg-elastic-ip-manager-demo \
        --template-body file://./cloudformation/demo-stack.yaml

aws cloudformation wait stack-create-complete  --stack-name asg-elastic-ip-manager-demo
```
