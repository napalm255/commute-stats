#!/usr/bin/env python
"""Commute Traffic Stats Processor."""
# pylint: disable=broad-except

from __future__ import print_function
import sys
import json
import datetime
import logging
import pymysql
from pymysql.cursors import DictCursor
import yaml
import boto3


# logging configuration
logging.getLogger().setLevel(logging.DEBUG)

# global
DATABASE_SCHEMA = 'schema.yml'

try:
    SSM = boto3.client('ssm')

    PREFIX = '/commute/database'
    PARAMS = SSM.get_parameters_by_path(Path=PREFIX, Recursive=True,
                                        WithDecryption=True)
    logging.debug('ssm: parameters(%s)', PARAMS)

    DATABASE = dict()
    for param in PARAMS['Parameters']:
        key = param['Name'].replace('%s/' % PREFIX, '')
        DATABASE.update({key: param['Value']})
    logging.debug('ssm: database(%s)', DATABASE)

    logging.info('ssm: successfully gathered parameters')
except Exception as ex:
    logging.error('ssm: could not connect to SSM. (%s)', ex)
    sys.exit()


try:
    CONNECTION = pymysql.connect(host=DATABASE['host'],
                                 user=DATABASE['user'],
                                 password=DATABASE['pass'],
                                 autocommit=True,
                                 cursorclass=DictCursor)
    logging.info('database: successfully connected to mysql')
# pylint: disable=broad-except
except Exception as ex:
    logging.error('database: could not connect to mysql (%s)', ex)
    sys.exit()


def database_setup(schema):
    """Database setup."""
    logging.info('database: setup')
    print(schema['databases'].values())
    for dbkey, dbval in schema['databases'].items():
        # TODO: validate database exists
        for tblkey, tblval in dbval['tables'].items():
            # TODO: validate table properties
            print(tblkey)
    return


def handler(event, context):
    """Lambda handler."""
    # pylint: disable=unused-argument
    logging.info('event %s', event)

    with open(DATABASE_SCHEMA) as schema_file:
        schema = yaml.load(schema_file)

    # database setup
    database_setup(schema)

    data = {
        'output': 'Hello World',
        'timestamp': datetime.datetime.utcnow().isoformat()
    }
    return {'statusCode': 200,
            'body': json.dumps(data),
            'headers': {'Content-Type': 'application/json'}}


if __name__ == '__main__':
    print(handler({"trigger": "cli"}, None))
