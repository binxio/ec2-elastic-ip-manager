## FiZZ related modifications

In order for the solution to suit FiZZ's needs, we introduced a number of modifications.

#### The artifacts bucket
`cloudformation/artifact-bucket.yaml` _(new)_

The upstream solution uses a default public artifact bucket that hosts the lambda's code. We opted to use bucket of our own to host the code.

#### The custom metric
`src/elastic_ip_manager/manager.py` _(modified)_

In order to monitor our usage of the elastic IP pool, we introduced a custom metric that would indicate the number of the elastic IPs left in the pool. This helps ud decide whether we need to allocate new IPs or not.

#### The custom metric cloudwatch alarm
`cloudformation/elastic-ip-manager.yaml` _(modified)_

We added a cloudwatch alarm to alert us when the elastic IP pool dedicated for FiZZ against is about run out if available IPs. This alarm is also helping assess the need for additional elastic IPs.


#### The lambda cloudwatch alarm
`cloudformation/elastic-ip-manager.yaml` _(modified)_

We added a cloudwatch alarm to alerts us when the lambda associating/disassociating elastic IPs with newly launched/terminated ec2 instances. This alarm is crucial to ensure that all launched agent EC2 instance have an elastic IP associated with them.

#### The Makefile
`Makefile` _(modified)_

The modification also included needed changes on the `Makefile` that allowed us to deploy the `artifact bucket, and pass the build number of the lambda for versioning.
