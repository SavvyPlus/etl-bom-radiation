import boto3

def lambda_handler(event, context):
    bucket_name = 'bom-prod.log'

    client = boto3.client('athena')

    config = {
        'OutputLocation': 's3://' + bucket_name + '/',
        'EncryptionConfiguration': {'EncryptionOption': 'SSE_S3'}

    }

    # Query Execution Parameters
    sql = 'MSCK REPAIR TABLE bom_prod.solar_data'
    context = {'Database': 'bom_prod'}

    client.start_query_execution(QueryString = sql,
                                 QueryExecutionContext = context,
                                 ResultConfiguration = config)
