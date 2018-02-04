include Makefile.mk

NAME=asg-elastic-ip-manager

AWS_REGION=eu-central-1
ALL_REGIONS=$(shell printf "import boto3\nprint '\\\n'.join(map(lambda r: r['RegionName'], boto3.client('ec2').describe_regions()['Regions']))\n" | python | grep -v '^$(AWS_REGION)$$')
S3_BUCKET=binxio-public-$(AWS_REGION)

help:
	@echo 'make                 - builds a zip file to target/.'
	@echo 'make release         - builds a zip file and deploys it to s3.'
	@echo 'make clean           - the workspace.'
	@echo 'make test            - execute the tests, requires a working AWS connection.'
	@echo 'make deploy-manager  - deploys the manager.'
	@echo 'make delete-manager  - deletes the provider.'
	@echo 'make demo            - deploys the provider and the demo cloudformation stack.'
	@echo 'make delete-demo     - deletes the demo cloudformation stack.'

deploy:
	aws s3 --region $(AWS_REGION) \
		cp target/$(NAME)-$(VERSION).zip \
		s3://$(S3_BUCKET)/lambdas/$(NAME)-$(VERSION).zip 
	aws s3 --region $(AWS_REGION) \
		cp \
		s3://$(S3_BUCKET)/lambdas/$(NAME)-$(VERSION).zip \
		s3://$(S3_BUCKET)/lambdas/$(NAME)-latest.zip 
	aws s3api --region $(AWS_REGION) \
		put-object-acl --bucket $(S3_BUCKET) \
		--acl public-read --key lambdas/$(NAME)-$(VERSION).zip 
	aws s3api --region $(AWS_REGION) \
		put-object-acl --bucket $(S3_BUCKET) \
		--acl public-read --key lambdas/$(NAME)-latest.zip 
	@for REGION in $(ALL_REGIONS); do \
		echo "copying to region $$REGION.." ; \
		aws s3 --region $(AWS_REGION) \
			cp  \
			s3://binxio-public-$(AWS_REGION)/lambdas/$(NAME)-$(VERSION).zip \
			s3://binxio-public-$$REGION/lambdas/$(NAME)-$(VERSION).zip; \
		aws s3 --region $$REGION \
			cp  \
			s3://binxio-public-$$REGION/lambdas/$(NAME)-$(VERSION).zip \
			s3://binxio-public-$$REGION/lambdas/$(NAME)-latest.zip; \
		aws s3api --region $$REGION \
			put-object-acl --bucket binxio-public-$$REGION \
			--acl public-read --key lambdas/$(NAME)-$(VERSION).zip; \
		aws s3api --region $$REGION \
			put-object-acl --bucket binxio-public-$$REGION \
			--acl public-read --key lambdas/$(NAME)-latest.zip; \
	done

do-push: deploy

do-build: local-build

local-build: src/*/*.py venv requirements.txt
	mkdir -p target/content 
	cp requirements.txt target/content
	docker run -v $(PWD)/target/content:/venv --workdir /venv python:2.7 pip install -t . -r requirements.txt
	docker run -v $(PWD)/target/content:/venv --workdir /venv python:2.7 python -m compileall -q -f .
	cp -r src/* target/content
	find target/content -type d | xargs  chmod ugo+rx
	find target/content -type f | xargs  chmod ugo+r 
	cd target/content && zip --quiet -9r ../../target/$(NAME)-$(VERSION).zip  *
	chmod ugo+r target/$(NAME)-$(VERSION).zip

venv: requirements.txt
	virtualenv -p python2 venv  && \
	. ./venv/bin/activate && \
	pip install --quiet --upgrade pip && \
	pip install --quiet virtualenv && \
	pip install --quiet -r requirements.txt 
	
clean:
	rm -rf venv target
	find . -name \*.pyc | xargs rm 

test: venv
	for i in $$PWD/cloudformation/*; do \
		aws cloudformation validate-template --template-body file://$$i > /dev/null || exit 1; \
	done
	. ./venv/bin/activate && \
	pip install --quiet -r requirements.txt -r test-requirements.txt && \
	cd src && \
        PYTHONPATH=$(PWD)/src pytest ../tests/test*.py

autopep:
	autopep8 --experimental --in-place --max-line-length 132 $(shell find src -name \*.py) $(shell find tests -name \*.py)

deploy-manager:
	@set -x ;if aws cloudformation get-template-summary --stack-name $(NAME) >/dev/null 2>&1 ; then \
		export CFN_COMMAND=update; \
	else \
		export CFN_COMMAND=create; \
	fi ;\
	aws cloudformation $$CFN_COMMAND-stack \
		--capabilities CAPABILITY_IAM \
		--stack-name $(NAME) \
		--template-body file://cloudformation/asg-elastic-ip-manager.yaml ; \
	aws cloudformation wait stack-$$CFN_COMMAND-complete --stack-name $(NAME) ;

delete-manager:
	aws cloudformation delete-stack --stack-name $(NAME)
	aws cloudformation wait stack-delete-complete  --stack-name $(NAME)

demo: 
	@if aws cloudformation get-template-summary --stack-name $(NAME)-demo >/dev/null 2>&1 ; then \
		export CFN_COMMAND=update; export CFN_TIMEOUT="" ;\
	else \
		export CFN_COMMAND=create; export CFN_TIMEOUT="--timeout-in-minutes 10" ;\
	fi ;\
	aws cloudformation $$CFN_COMMAND-stack --stack-name $(NAME)-demo \
		--template-body file://cloudformation/demo-stack.yaml  
		$$CFN_TIMEOUT  ; \
	aws cloudformation wait stack-$$CFN_COMMAND-complete --stack-name $(NAME)-demo ;

delete-demo:
	aws cloudformation delete-stack --stack-name $(NAME)-demo
	aws cloudformation wait stack-delete-complete  --stack-name $(NAME)-demo
