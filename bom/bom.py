import os
import pytz
import csv
import boto3
from pytz import timezone
from datetime import datetime

s3 = boto3.client('s3')

# input_bucket = 'bom-prod-2.input'
# processing_bucket = 'bom-prod-2.processing'
# done_bucket = 'bom-prod-2.done'
# bom_bucket = 'bom-prod-2.output'


def move_file(src_bucket, src_key, dst_bucket, dst_key):
    print("Copying [%s] from [%s]" % (src_key, src_bucket))

    s3.copy({'Bucket': src_bucket, 'Key': src_key}, dst_bucket, dst_key)
    s3.delete_object(Bucket=src_bucket, Key=src_key)


def copy_file(src_bucket, src_key, dst_bucket, dst_key):
    print("Copying [%s] to [%s]" % (src_key, dst_key))
    s3.copy({'Bucket': src_bucket, 'Key': src_key}, dst_bucket, dst_key)


def s3_key(input_date, input_time, filename):
    parts = input_date.split("-")
    tparts = input_time.split(":")
    key = "athena/year=%s/month=%s/day=%s/hour=%s/%s" % (parts[0], parts[1], parts[2], tparts[0], filename)
    return key


def process_file(filename):
    """
    1. Move to processing_bucket
    2. Find date in the first line and download and process file, then upload to correct key in bom_bucket
    3. Move to done_bucket
    """

    try:
        stack_name = os.environ['StackName']
        bom_bucket = os.environ['BucketName']

        input_key_fmt = "in/%s"
        processing_key_fmt = "processing/%s"
        done_key_fmt = "done/%s"

        input_key = input_key_fmt % (filename,)
        processing_key = processing_key_fmt % (filename,)

        # move to processing bucket
        move_file(bom_bucket, input_key, bom_bucket, processing_key)

        print("Get object: %s" % filename)
        obj = s3.get_object(Bucket=processing_bucket, Key=filename)
        data = obj['Body'].read().decode('utf-8', 'ignore')
        lines = data.splitlines()
        print("Lines: %d" % len(lines))

        csv_name, radiation_type, date_str, time_str = extract_datetime(filename)
        print("Extract filename: %s" % csv_name)

        athena_key = s3_key(date_str, time_str, csv_name + '.csv')
        print("Parition: %s" % athena_key)

        full_datetime_str = date_str + ' ' + time_str
        bytes_csv = extract_data(lines, radiation_type, csv_name, full_datetime_str)

        print("Upload file [%s] to [%s]" % (athena_key, bom_bucket))
        # upload formatted file to production bucket
        # s3.upload_file(formatted_csv, bom_bucket, dst_key)

        # put formatted file to production bucket
        s3.put_object(Bucket=bom_bucket, Key=athena_key, Body=bytes_csv)

        # move to done bucket
        done_key = done_key_fmt % (filename,)
        move_file(bom_bucket, done_key, bom_bucket, done_key)

    except Exception as e:
        print(e)
        # TODO move to a failed bucket


def handler(event, context):
    print("Object added to: [%s]" % (event['Records'][0]['s3']['bucket']['name'],))
    filename = event['Records'][0]['s3']['object']['key'].split('/')[-1]
    print("Processing: ", filename)
    process_file(filename)


def extract_datetime(fname):
    base = os.path.splitext(fname)[0]
    pieces = base.split('_')
    radiation = pieces[1]
    date_str = pieces[2]
    time_str = pieces[3]

    utc = pytz.utc
    datetime_str = date_str + ' ' + time_str[:2]
    date_obj = utc.localize(datetime.strptime(datetime_str, "%Y%m%d %H"))
    date_obj = date_obj.astimezone(timezone('Australia/Sydney'))
    date_str = date_obj.strftime('%Y-%m-%d')
    time_str = date_obj.strftime('%H:%M')
    return base, radiation, date_str, time_str


def extract_data(lines, radiation_type, csv_name, date_str):
    headers = ['Date', 'RadiationType', 'Longitude', 'Latitude', 'Radiation']
    data = [headers]

    line_number = 0
    ncols = 0
    nrows = 0
    xllcorner = 0
    yllcorner = 0
    cellsize = 0
    nodata_value = 0
    x = y = 0

    for line in lines:
        pieces = line.split(' ')
        if (line_number < 6):
            if line_number == 0:
                ncols = int(pieces[1])
            elif line_number == 1:
                nrows = int(pieces[1])
            elif line_number == 2:
                xllcorner = float(pieces[1])
            elif line_number == 3:
                yllcorner = float(pieces[1])
            elif line_number == 4:
                cellsize = float(pieces[1])
            elif line_number == 5:
                nodata_value = int(pieces[1])
                y = yllcorner + nrows * cellsize
                x = xllcorner
        else:
            x = xllcorner
            y = y - cellsize
            for point in pieces:
                radiation = int(point)
                if (radiation == nodata_value):
                    x = x + cellsize
                    continue
                data.append([date_str, radiation_type, str(x), str(y), str(radiation)])
                x = x + cellsize

        line_number = line_number + 1

    list_res = list(map(lambda line: ','.join(line), data))
    str_res = '\n'.join(list_res)
    bytes_res = str_res.encode()

    return bytes_res
