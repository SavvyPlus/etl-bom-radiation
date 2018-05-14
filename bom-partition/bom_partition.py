# @Author: foamdino
# @Email: foamdino@gmail.com
"""
This lambda handles both the initial MSCK command
and the ALTER TABLE ADD PARTITION command.
"""

import boto3
import botocore
import os
import re
from datetime import datetime, timedelta

def parse_filename(filename):
    """
    input: string file name e.g. NEMPriceSetter_2017103128100.csv
    output: datetime obj e.g. datetime(2017-10-31-03:25)
    """
    raw_date =re.search("\d{11}", filename).group(0)
    year = int(raw_date[:4])
    month = int(raw_date[4:6])
    date = int(raw_date[6:8])
    minute_id = int(raw_date[8:])

    parsed_time = datetime(year, month, date, 4, 0 ) + timedelta(minutes = minute_id * 5)
    return parsed_time


def check_msck_file(stack_name, from_bucket):
    """
    Check if the msck_file for this bucket already exists
    returns:
      - ('ok', True) when file exists
      - ('ok', False) when file doesn't exist
      - ('fail', None) when there is an error
    """
    s3 = boto3.client('s3')
    bucket_name = os.environ['BucketName']
    key = "%s-msck-completed" % (from_bucket,)
    try:
        s3.Object(bucket_name, key).load()
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            return ('ok',False)
        else:
            print (e)
            return ('fail',None)
    else:
        return ('ok',True)


def msck(stack_name, from_bucket):
    """
    Run MSCK command

    Args:
      stack_name (string): name of the cloud formation stack to differentiate between test and production
      from_bucket (string): name of the bucket which the input file originated from

    Returns:
      nothing
    """
    print ("MSCK starting...")
    print ("from_bucket: " + from_bucket)
    name = from_bucket.split(".")[0]
    bucket_name = name + '.log'
    print ("using: " + bucket_name)

    athena = boto3.client('athena', region_name='ap-southeast-2')

    config = {
        'OutputLocation': 's3://' + bucket_name + '/',
        'EncryptionConfiguration': {'EncryptionOption': 'SSE_S3'}
    }

    # Query Execution Parameters
    sql = 'MSCK REPAIR TABLE ' + name
    context = {'Database': name}

    client.start_query_execution(QueryString = sql,
                                 QueryExecutionContext = context,ResultConfiguration = config)

    # write msck file to main bucket
    try:
        s3 = boto3.client('s3')
        obj = s3.Object("tas-hydro-bucket.%s" % (stack_name,), "msck-completed-files/%s-msck-completed.txt" % (from_bucket,))
        obj.put(Body="MSCK completed for %s" % (from_bucket,))
    except:
        print ("Unable to write msck file - msck command will run again")


def partition(stack_name, database_name, from_bucket, parsed_time):
    """
    Run ALTER TABLE command

    Args:
      stack_name (string): name of the cloud formation stack to differentiate between test and production
      database_name (string): name of the athena database
      from_bucket (string): name of the bucket which the input file originated from
      parsed_time (datetime): datetime created by parsing the input filename, used in the partition command

    Returns:
      nothing
    """
    print ("Adding partition...")

    name = from_bucket.split(".")[0].replace('-', '_')
    bucket_name = name + '.log'
    print("using: " + bucket_name)

    #TODO work out how to get these...
    year=parsed_time.year
    month=parsed_time.month
    day=parsed_time.day
    hour=parsed_time.hour
    minute=parsed_time.minute

    athena = boto3.client('athena', region_name='ap-southeast-2')

    config = {
        'OutputLocation': 's3://' + bucket_name + '/',
        'EncryptionConfiguration': {'EncryptionOption': 'SSE_S3'}
    }

    # Query Execution Parameters
    sql = "ALTER TABLE tas_hydro_%s_data_add ADD PARTITION (year=%s,month=%s,date=%s,hour=%s,minute=%s)" % (name, year, month, day, hour, minute)
    context = {'Database': database_name+"_staging"}

    client.start_query_execution(QueryString = sql,
                                 QueryExecutionContext = context,
                                 ResultConfiguration = config)


def handler(event, context):
    """
    Standard aws lambda handler function

    Args:
      event (dict): the aws event that triggered the lambda
      context (dict): the aws context the lambda runs under
    """

    stack_name = os.environ['StackName']
    database_name = os.environ['DatabaseName'].replace('-', '_')
    print ("stack_name: %s" % (stack_name),)
    from_bucket = event['Records'][0]['s3']['bucket']['name']
    print ("from_bucket: %s" % (from_bucket,))
    filename = event['Records'][0]['s3']['object']['key'].split('/')[-1]
    print("filename: %s" %(filename,))
    parsed_time = parse_filename(filename)

    msck_result = check_msck_file(stack_name, from_bucket)
    if msck_result[0] == 'ok' and not msck_result[1]:
        #msck file doesn't exist
        msck()
    elif msck_result[0] == 'ok' and msck_result[1]:
        #msck file already present, just do partitioning
        if parsed_time:
            partition(stack_name, database_name, from_bucket, parsed_time)
        else:
            print("unable to parse filename: [%s] not adding partition" % (filename,))
    elif msck_result[0] == 'fail':
        print ("unable to msck/partition due to error checking if msck file exists")
