#!/usr/bin/env python
# -*- coding: utf-8 -*-
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

def sendResponseCfn(event, context, responseStatus):
    """
    Send the correctly formatted response_data for cloudformation to know that this lambda has succeeded or failed.

    Args:
      event (dict): the aws event that triggered the lambda
      context (dict): the aws context the lambda runs under
      responseStatus (string): SUCCESS or FAILED
    Returns:
      nothing
    """
    response_body = {'Status': responseStatus,
                     'Reason': 'Log stream name: ' + context.log_stream_name,
                     'PhysicalResourceId': context.log_stream_name,
                     'StackId': event['StackId'],
                     'RequestId': event['RequestId'],
                     'LogicalResourceId': event['LogicalResourceId'],
                     'Data': json.loads("{}")}

    requests.put(event['ResponseURL'], data=json.dumps(response_body).encode("utf8"))

def handler(event, context):
    """
    This handler:
      1. Checks the S3 bucket name
      2. If s3 bucket already exists, logs + returns quickly
         Else Creates the S3 bucket with the correct configuration

    Args:
      event (dict): the aws event that triggered the lambda
      context (dict): the aws context the lambda runs under
    """
    try:
        bucketName = event['ResourceProperties']['BucketName']

        bucket = s3.Bucket(bucketName)
        print("bucketName: " + bucketName)

        if bucket and can_access_bucket(bucket):
            print("Bucket %s already exists, skipping creation" % (bucketName,))
            sendResponseCfn(event, context, "SUCCESS")
            return

        # create bucket
        s3.create_bucket(Bucket=bucketName, CreateBucketConfiguration={'LocationConstraint': 'ap-southeast-2'})

        # set lambda NotificationConfiguration
        config = {
            'LambdaFunctionConfigurations': [
                {
                    'LambdaFunctionArn': event['ResourceProperties']['InputFn'],
                    'Events': [
                        's3:ObjectCreated:*',
                    ],
                    'Filter': {
                        'Key': {
                            'FilterRules': [
                                {
                                    'Name': 'prefix',
                                    'Value': 'in/'
                                },
                            ]
                        }
                    }
                },
                {
                    'LambdaFunctionArn': event['ResourceProperties']['DoneFn'],
                    'Events': [
                        's3:ObjectCreated:*',
                    ],
                    'Filter': {
                        'Key': {
                            'FilterRules': [
                                {
                                    'Name': 'prefix',
                                    'Value': 'done/'
                                },
                            ]
                        }
                    }
                }
            ]
        }

        client = boto3.client('s3')
        client.put_bucket_notification_configuration(Bucket=bucketName,NotificationConfiguration=config)

        # create folders
        client.put_object(Bucket=bucketName, Key='in/')
        client.put_object(Bucket=bucketName, Key='processing/')
        client.put_object(Bucket=bucketName, Key='done/')
        client.put_object(Bucket=bucketName, Key='athena/')

        sendResponseCfn(event, context, "SUCCESS")
    except Exception as e:
        print(e)
        sendResponseCfn(event, context, "FAILED")
