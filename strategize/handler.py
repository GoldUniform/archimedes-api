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

def strategize(event, context, dynamodb=None):

    if not dynamodb:
        dynamodb = boto3.resource('dynamodb')

    for record in event['Records']:
        q = json.loads(record["body"])
        optimizerGUID = q["optimizer_guid"]
       
        ## Get the Optimizer record from dynamodb by GUID
        table = dynamodb.Table('archimedes-optimizations')
        response = table.get_item(Key={'guid': optimizerGUID})

        # loop over strategies
        for strategy in response['Item']["strategies"]:
            strategy["backtests"] = []
            # loop over each rsiPeriod
            _p = int(strategy["params"]["rsiPeriod"]["start"])
            while _p <= int(strategy["params"]["rsiPeriod"]["end"]):
                # loop over each rsiLow
                _l = int(strategy["params"]["rsiLow"]["start"])
                while _l <= int(strategy["params"]["rsiLow"]["end"]):
                    # loop over each rsiHigh
                    _h = int(strategy["params"]["rsiHigh"]["start"])
                    while _h <= int(strategy["params"]["rsiHigh"]["end"]):
                        # generate a backtest object
                        backtestGUID = uuid.uuid4().hex
                        backtest = {
                            "guid": backtestGUID,
                            "optimizer_guid": optimizerGUID,
                            "symbol": response['Item']['symbol'],
                            "dt_start": response['Item']['dt_start'],
                            "dt_end": response['Item']['dt_end'],
                            "period": _p,
                            "rsi_low": _l,
                            "rsi_high": _h,
                            "interval": response['Item']['interval'],
                            "startcash": int(response['Item']['startcash'])
                        }

                        # add this backtest to the strategy record
                        strategy["backtests"].append(backtest)

                        #send this backtest to sqs
                        send_sqs_message('archimedes-backtest-dev', backtest)
                        _h += 1
                    _l += 1
                _p += 1

        #update this optimizer record in dynamo
        table.update_item(
            Key={
                'guid': optimizerGUID
            },
            UpdateExpression="set strategies=:s",
            ExpressionAttributeValues={
                ':s': response['Item']["strategies"]
            }
        )