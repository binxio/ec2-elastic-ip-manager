"""
AWS Auto Scaling Elastic IP manager

Manages the ip addresses associated to an autoscaling group instance.

When a lifecycle terminating event occurs, the manager will remove all the elastic ip addresses that are associated
with the instance.

When a lifecycle launching event completed successfully, the manager will add a elastic ip address with the instance. If
no elastic ips are available, it will cancel the launch event.
"""
import boto3
import logging
from botocore.exceptions import ClientError

log = logging.getLogger('asg_elastic_ip_manager')

ec2 = boto3.client('ec2')


def addresses():
    response = ec2.describe_addresses(Filters=[{'Name': 'domain', 'Values': ['vpc']}])
    return response['Addresses']

def instance_id(event):
    return event['details']['EC2InstanceId']

def instance_addresses(event):
    instance = instance_id(event)
    return filter(lambda a: 'InstanceId' in a and a['InstanceId'] == instance, addresses())


def available_addresses(event):
    instance_id = event['details']['EC2InstanceId']
    return filter(lambda a: 'InstanceId' not in a, addresses())


def is_remove_address_event(event):
    type = event.get('detail-type', None)
    return type in [ 'EC2 Instance-terminate Lifecycle Action', 'EC2 Instance Launch Unsuccessful']


def is_add_address_event(event):
    type = event.get('detail-type', None)
    detail = event.get('detail', None)
    status_code = detail.get('StatusCode', None)
    return type == 'EC2 Instance Terminate Unsuccessful' or (
        type == 'EC2 Instance Launch Successful' and status_code != 'InProgress'
    )

def add_address(event):
    try:
        address = next(available_addresses(event), None)
        if address is not None:
            ec2.associate_address(InstanceId=instance_id(event), AllocationId=address['AllocationId'])
        else:
            log.error('No elastic ip addresses are available')
    except ClientError as e:
        log.error('failed to add elastic ip address, {}', e)


def remove_address(event):
    for address in instance_addresses(event):
        try:
            ec2.disassociate_address(AllocationId=address['AllocationId'])
        except ClientError as e:
            log.error('failed to remove elastic ip address, {}', e)


def handler(event, context):
    if 'source' in event and event['source'] == 'aws.autoscaling':
        if is_add_address_event(event):
            add_address(event)
        elif is_remove_address_event(event):
            remove_address(event)
        else:
            log.warning('ignoring event {}, {}', event.get('detail-type', ''), event.get('detail').get('StatusCode', ''))
    else:
        log.error('unknown event received, {}', event)
