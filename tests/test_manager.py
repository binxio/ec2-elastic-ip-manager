import boto3
from asg_elastic_ip_manager import handler, Manager

event = {
          'detail-type': 'EC2 Instance Launch Successful',
          'source': 'aws.autoscaling',
          'detail': {
            'StatusCode': 'InProgress',
            'AutoScalingGroupName': 'asg-elastic-ip-manager-demo',
            'Details': {
              'Availability Zone': 'us-west-2b',
              'Subnet ID': 'subnet-12345678'
            },
            'EC2InstanceId': 'i-1234567890abcdef0'
          }
        }


ec2 = boto3.client('ec2')
autoscaling = boto3.client('autoscaling')
asg = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[event['detail']['AutoScalingGroupName']])['AutoScalingGroups'][0]

def is_available_address(a):
    return 'AssociationId' not in a

def is_unavailable_address(a):
    return 'AssociationId' in a

def get_addresses():
    response = ec2.describe_addresses(Filters=[{'Name': 'domain', 'Values': ['vpc']}, {'Name': 'tag:EIPPoolName', 'Values': ['eip-bastion-pool']}])
    addresses = response['Addresses']
    return addresses, list(filter(is_available_address, addresses)), list(filter(is_unavailable_address, addresses))

def return_all_ips_to_pool():
    for instance_id in map(lambda i: i['InstanceId'], asg['Instances']):
        event['detail-type'] = 'EC2 Instance Terminate Successful'
        event['detail']['EC2InstanceId'] = instance_id
        manager = Manager(event)
        manager.handle()

def test_add_and_remove():
    addresses, available, allocated = get_addresses()
    assert len(addresses) == 2

    return_all_ips_to_pool()

    addresses, available, _ = get_addresses()
    assert len(available) == 2

    event['detail-type'] = 'EC2 Instance Launch Successful'
    event['detail']['EC2InstanceId'] = asg['Instances'][0]['InstanceId']
    manager = Manager(event)
    manager.handle()

    addresses, available, allocated = get_addresses()
    assert len(available) == 0

    event['detail-type'] = 'EC2 Instance Terminate Successful'
    event['detail']['EC2InstanceId'] = allocated[0]['InstanceId']
    manager = Manager(event)
    manager.handle()

    addresses, available, _ = get_addresses()
    assert len(available) == 1



def test_remove_non_existing_instance():
    event['detail-type'] = 'EC2 Instance Terminate Successful'
    event['detail']['EC2InstanceId'] = 'i-0000000000000'
    manager = Manager(event)
    manager.handle()

def test_add_non_existing_instance_eip():
    return_all_ips_to_pool()
    event['detail-type'] = 'EC2 Instance Launch Successful'
    event['detail']['EC2InstanceId'] = 'i-0000000000000'
    manager = Manager(event)
    manager.handle()

