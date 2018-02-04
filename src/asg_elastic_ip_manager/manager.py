"""
AWS Auto Scaling Elastic IP manager

Manages the ip addresses associated to an autoscaling group instance.

When a lifecycle terminating event occurs, the manager will remove all the elastic ip addresses that are associated
with the instance.

When a lifecycle launching event completed successfully, the manager will add a elastic ip address with the instance. If
no elastic ips are available, it will cancel the launch event.
"""
import os
import boto3
import logging

from botocore.exceptions import ClientError


logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
log = logging.getLogger('asg_elastic_ip_manager')

ec2 = boto3.client('ec2')


def addresses():
    response = ec2.describe_addresses(Filters=[{'Name': 'domain', 'Values': ['vpc']}])
    return response['Addresses']

def instance_id(event):
    return event['detail']['EC2InstanceId']

def instance_addresses(event):
    instance = instance_id(event)
    return filter(lambda a: 'InstanceId' in a and a['InstanceId'] == instance, addresses())


def available_addresses(event):
    instance_id = event['detail']['EC2InstanceId']
    return filter(lambda a: 'InstanceId' not in a, addresses())


def is_remove_address_event(event):
    type = event.get('detail-type', None)
    return type in [ 'EC2 Instance Terminate Successful', 'EC2 Instance Launch Unsuccessful']


def is_add_address_event(event):
    type = event.get('detail-type', None)
    return type in ['EC2 Instance Terminate Unsuccessful', 'EC2 Instance Launch Successful']

def add_address(event):
    try:
        log.info('add ip address to instance %s', instance_id(event))
        address = next(iter(available_addresses(event)), None)
        if address is not None:
            log.info('associating ip address %s with instance %s', address['AllocationId'],instance_id(event))
            ec2.associate_address(InstanceId=instance_id(event), AllocationId=address['AllocationId'])
        else:
            log.error('No elastic ip addresses are available to associate with instance')
    except ClientError as e:
        log.error('failed to add elastic ip address, %s', e)


def remove_address(event):
    log.info('removing ip addresses from instance %s', instance_id(event))
    for address in instance_addresses(event):
        try:
            log.info('removing ip address %s from instance %s', address['AllocationId'],instance_id(event))
            ec2.disassociate_address(AllocationId=address['AllocationId'])
        except ClientError as e:
            log.error('failed to remove elastic ip address, %s', e)


def handler(event, context):
    if 'source' in event and event['source'] == 'aws.autoscaling':
        if is_add_address_event(event):
            add_address(event)
        elif is_remove_address_event(event):
            remove_address(event)
        else:
            log.warning('ignoring event %s', event.get('detail-type', ''))
    else:
        log.error('unknown event received, %s', event)
