#!/usr/bin/env python
# -*- coding: utf-8 -*-
# https://stackoverflow.com/questions/40383470/can-i-force-cloudformation-to-delete-non-empty-s3-bucket
# @Author: foamdino
# @Email: foamdino@gmail.com
import json
import boto3
import botocore
from botocore.vendored import requests

s3 = boto3.resource('s3')

def can_access_bucket(bucket):
    """
    Check if the bucket exists and if it is accessible by this account
    returns:
      - True when bucket exists and is accessible
      - False when bucket doesn't exist or cannot be accessed
    """
    try:
        s3.meta.client.head_bucket(Bucket=bucket.name)
        return True
    except botocore.exceptions.ClientError as e:
        # If a client error is thrown, then check that it was a 404 error.
        # If it was a 404 error, then the bucket does not exist.
        error_code = int(e.response['Error']['Code'])
        if error_code == 403:
            print("Private Bucket. Forbidden Access!")
        elif error_code == 404:
            print("Bucket Does Not Exist!")

        return False

def lambda_handler(event, context):
    try:
        bucketName = event['ResourceProperties']['BucketName']

        bucket = s3.Bucket(bucketName)

        print("bucketName: " + bucketName)

        if bucket and can_access_bucket(bucket):
            if event['RequestType'] == 'Delete':
                for obj in bucket.objects.filter(Prefix='in/'):
                    s3.Object(bucket.name, obj.key).delete()
                for obj in bucket.objects.filter(Prefix='processing/'):
                    s3.Object(bucket.name, obj.key).delete()
                for obj in bucket.objects.filter(Prefix='done/'):
                    s3.Object(bucket.name, obj.key).delete()

        sendResponseCfn(event, context, "SUCCESS")
    except Exception as e:
        print(e)
        sendResponseCfn(event, context, "FAILED")

def sendResponseCfn(event, context, responseStatus):
    response_body = {'Status': responseStatus,
                     'Reason': 'Log stream name: ' + context.log_stream_name,
                     'PhysicalResourceId': context.log_stream_name,
                     'StackId': event['StackId'],
                     'RequestId': event['RequestId'],
                     'LogicalResourceId': event['LogicalResourceId'],
                     'Data': json.loads("{}")}

    requests.put(event['ResponseURL'], data=json.dumps(response_body).encode("utf8"))
