import json
import logging
import uuid
import boto3
from botocore.exceptions import ClientError

def send_sqs_message(QueueName, msg_body):
    """

    :param sqs_queue_url: String URL of existing SQS queue
    :param msg_body: String message body
    :return: Dictionary containing information about the sent message. If
        error, returns None.
    """

    # Send the SQS message
    sqs_client = boto3.client('sqs')
    sqs_queue_url = sqs_client.get_queue_url(
        QueueName=QueueName
    )['QueueUrl']
    try:
        msg = sqs_client.send_message(QueueUrl=sqs_queue_url,
                                      MessageBody=json.dumps(msg_body))
    except ClientError as e:
        logging.error(e)
        return None
    return msg

def optimize(event, context, dynamodb=None):
    # pull the params out of the post body
    params = json.loads(event['body'])
    guid = uuid.uuid4().hex

    ## Save the initial plan to DynamoDB in pending status
    if not dynamodb:
        dynamodb = boto3.resource('dynamodb')

    table = dynamodb.Table('archimedes-optimizations')
    table.put_item(
       Item={
            'guid': guid,
            'status': 'pending',
            'symbol': params["symbol"],
            'dt_start': params["dt_start"],
            'dt_end': params["dt_end"],
            'interval': params["interval"],
            'startcash': params["startcash"],
            'strategies': params["strategies"]
        }
    )

    ## Notify the queue that we have some work to do
    send_sqs_message('archimedes-optimize-dev', {
                        "optimizer_guid": guid
                    })

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": guid
    }